from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from pathlib import Path
from time import perf_counter
from typing import Any

from google import genai
from google.genai import types
from PIL import Image

from geoguesser.extraction import ExtractionOutput


EXTRACTION_PROMPT = """Inspect all four street-scene views together and extract only visible visual evidence.
Preserve multiple objects per category. For each category provide a status of
not_present, not_detected, present_but_illegible, or present, plus a concise consolidated
signal. Use bbox coordinates as integer [ymin, xmin, ymax, xmax] normalized to 0-1000.
Do not infer or mention image IDs, filenames, coordinates, timestamps, country labels, or
any metadata that is not visible in the images."""


def _normalize_provider_payload(value: Any) -> Any:
    """Normalize only known harmless provider aliases before strict validation."""
    if isinstance(value, dict):
        normalized = {
            key: _normalize_provider_payload(child) for key, child in value.items()
        }
        if normalized.get("schema_version") in {"1.0", "1.0.0"}:
            normalized["schema_version"] = "extraction-v1"
        if normalized.get("legibility") == "legible":
            normalized["legibility"] = "clear"
        return normalized
    if isinstance(value, list):
        return [_normalize_provider_payload(child) for child in value]
    return value


def _gemini_extraction_schema() -> dict:
    """Return a minimal schema from Gemini's supported JSON Schema subset."""
    object_schema = {
        "type": "object",
        "properties": {
            "heading": {"type": "integer"},
            "bbox": {
                "type": "object",
                "properties": {
                    "ymin": {"type": "integer"}, "xmin": {"type": "integer"},
                    "ymax": {"type": "integer"}, "xmax": {"type": "integer"},
                },
                "required": ["ymin", "xmin", "ymax", "xmax"],
            },
            "observation": {"type": "string"},
            "confidence": {"type": "integer"},
            "legibility": {"type": "string"},
            "transcription": {"type": "string"},
        },
        "required": ["heading", "observation", "confidence", "legibility"],
    }
    category_schema = {
        "type": "object",
        "properties": {
            "status": {"type": "string"},
            "objects": {"type": "array", "items": object_schema},
            "signal": {"type": "string"},
        },
        "required": ["status", "objects", "signal"],
    }
    categories = {
        name: category_schema
        for name in (
            "driving_side_and_markings", "signs_and_language", "vehicles_and_plates",
            "infrastructure", "terrain_vegetation_and_climate", "architecture_and_settlement",
        )
    }
    return {
        "type": "object",
        "properties": {"schema_version": {"type": "string"}, **categories},
        "required": ["schema_version", *categories],
    }


def _parse_response(response: Any) -> ExtractionOutput:
    parsed = getattr(response, "parsed", None)
    if isinstance(parsed, ExtractionOutput):
        return parsed
    if parsed is not None:
        return ExtractionOutput.model_validate(_normalize_provider_payload(parsed))

    text = (getattr(response, "text", "") or "").strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    return ExtractionOutput.model_validate(_normalize_provider_payload(json.loads(text)))


def extract_cardinal_views(
    client: genai.Client,
    view_paths: Mapping[int, Path],
    *,
    model: str = "gemini-3-flash-preview",
    max_attempts: int = 2,
    usage_callback: Callable[[Any, int], None] | None = None,
    before_attempt: Callable[[], None] | None = None,
) -> ExtractionOutput:
    if set(view_paths) != {0, 90, 180, 270}:
        raise ValueError("exactly four cardinal views are required")

    with Image.open(view_paths[0]) as h000, Image.open(view_paths[90]) as h090:
        with Image.open(view_paths[180]) as h180, Image.open(view_paths[270]) as h270:
            views = [h000.copy(), h090.copy(), h180.copy(), h270.copy()]

    labeled_contents: list[Any] = []
    for heading, view in zip((0, 90, 180, 270), views):
        labeled_contents.extend(
            [
                f"The next image is the cardinal view at heading {heading} degrees. "
                "Any bounding boxes found in that image must use this heading.",
                view,
            ]
        )

    prompt = EXTRACTION_PROMPT
    for attempt in range(max_attempts):
        if before_attempt is not None:
            before_attempt()
        started = perf_counter()
        try:
            response = client.models.generate_content(
                model=model,
                contents=[*labeled_contents, prompt],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=_gemini_extraction_schema(),
                    max_output_tokens=3200,
                    thinking_config=types.ThinkingConfig(thinking_budget=0),
                ),
            )
        except Exception as exc:
            if "INVALID_ARGUMENT" not in str(exc) and getattr(exc, "status_code", None) != 400:
                raise
            try:
                response = client.models.generate_content(
                    model=model,
                    contents=[
                        *labeled_contents,
                        prompt + "\nReturn only valid JSON; it will be validated against the extraction schema locally.",
                    ],
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        max_output_tokens=3200,
                        thinking_config=types.ThinkingConfig(thinking_budget=0),
                    ),
                )
            except Exception as fallback_exc:
                raise RuntimeError(
                    "Gemini extraction failed in both modes: "
                    f"structured_schema={exc}; json_only={fallback_exc}"
                ) from fallback_exc
        if usage_callback is not None:
            usage_callback(response, round((perf_counter() - started) * 1000))
        try:
            return _parse_response(response)
        except Exception:
            if attempt == max_attempts - 1:
                raise
            prompt = (
                EXTRACTION_PROMPT
                + "\nYour previous response was invalid. Return only a complete object matching the schema."
            )
    raise RuntimeError("extraction retry loop exhausted")
