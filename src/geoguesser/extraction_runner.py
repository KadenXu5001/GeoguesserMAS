from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
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


def _parse_response(response: Any) -> ExtractionOutput:
    parsed = getattr(response, "parsed", None)
    if isinstance(parsed, ExtractionOutput):
        return parsed
    if parsed is not None:
        return ExtractionOutput.model_validate(parsed)

    text = (getattr(response, "text", "") or "").strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    return ExtractionOutput.model_validate(json.loads(text))


def extract_cardinal_views(
    client: genai.Client,
    view_paths: Mapping[int, Path],
    *,
    model: str = "gemini-3-flash-preview",
    max_attempts: int = 2,
) -> ExtractionOutput:
    if set(view_paths) != {0, 90, 180, 270}:
        raise ValueError("exactly four cardinal views are required")

    with Image.open(view_paths[0]) as h000, Image.open(view_paths[90]) as h090:
        with Image.open(view_paths[180]) as h180, Image.open(view_paths[270]) as h270:
            views = [h000.copy(), h090.copy(), h180.copy(), h270.copy()]

    prompt = EXTRACTION_PROMPT
    for attempt in range(max_attempts):
        response = client.models.generate_content(
            model=model,
            contents=[*views, prompt],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=ExtractionOutput,
                max_output_tokens=3200,
                thinking_config=types.ThinkingConfig(thinking_budget=0),
            ),
        )
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

