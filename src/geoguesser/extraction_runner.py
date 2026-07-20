from __future__ import annotations

import json
import mimetypes
from collections.abc import Callable, Mapping
from pathlib import Path
from time import perf_counter
from typing import Any

from google import genai
from google.genai import types

from geoguesser.extraction import ExtractionOutput


EXTRACTION_PROMPT = """Inspect all four street-scene views together and extract only visible visual evidence.
Preserve multiple objects per category. For each category provide a status of
not_present, not_detected, present_but_illegible, or present, plus a concise consolidated
signal. Use bbox coordinates as integer [ymin, xmin, ymax, xmax] normalized to 0-1000.
For each object, legibility must be exactly clear, partial, illegible, or not_applicable.
Category status and object legibility are separate fields: never use present_but_illegible
as an object's legibility value.
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
        if normalized.get("legibility") == "present_but_illegible":
            normalized["legibility"] = "illegible"
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
            "legibility": {
                "type": "string",
                "format": "enum",
                "enum": ["clear", "partial", "illegible", "not_applicable"],
            },
            "transcription": {"type": "string"},
        },
        "required": ["heading", "observation", "confidence", "legibility"],
    }
    category_schema = {
        "type": "object",
        "properties": {
            "status": {
                "type": "string",
                "format": "enum",
                "enum": [
                    "not_present",
                    "not_detected",
                    "present_but_illegible",
                    "present",
                ],
            },
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
    max_attempts: int = 1,
    usage_callback: Callable[[Any, int], None] | None = None,
    before_attempt: Callable[[], None] | None = None,
) -> ExtractionOutput:
    if set(view_paths) != {0, 90, 180, 270}:
        raise ValueError("exactly four cardinal views are required")
    if max_attempts != 1:
        raise ValueError("extraction is single-call and max_attempts must be 1")

    labeled_contents: list[Any] = []
    for heading in (0, 90, 180, 270):
        path = view_paths[heading]
        mime_type = mimetypes.guess_type(path.name)[0] or "image/jpeg"
        if not mime_type.startswith("image/"):
            raise ValueError(f"cardinal view at heading {heading} is not an image")
        view = types.Part.from_bytes(data=path.read_bytes(), mime_type=mime_type)
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
                    http_options=types.HttpOptions(
                        timeout=30_000,
                        retry_options=types.HttpRetryOptions(attempts=1),
                    ),
                ),
            )
        except Exception:
            raise
        if usage_callback is not None:
            usage_callback(response, round((perf_counter() - started) * 1000))
        try:
            return _parse_response(response)
        except Exception:
            raise
    raise RuntimeError("extraction retry loop exhausted")
