from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Protocol

from google.genai import types
from PIL import Image

from geoguesser.prediction import CountryPrediction


CARDINAL_HEADINGS = (0, 90, 180, 270)
GEMINI_FLASH_MODEL = "gemini-3-flash-preview"
GEMINI_PRO_MODEL = "gemini-3.1-pro-preview"
BASELINE_PROMPT = """Identify the country shown in these four cardinal street-scene views.
Return one worldwide country prediction, up to three alternatives, concise visible
evidence, and confidence from 0 to 100. Use only what is visible in the images; do not
infer or mention filenames, image IDs, coordinates, timestamps, or hidden metadata."""


class GeminiClient(Protocol):
    models: Any


@dataclass(frozen=True)
class BaselineRun:
    prediction: CountryPrediction
    usage: dict[str, Any]


def _load_views(view_paths: Mapping[int, Path]) -> list[Image.Image]:
    if set(view_paths) != set(CARDINAL_HEADINGS):
        raise ValueError("exactly four cardinal views are required")
    return [Image.open(view_paths[heading]).convert("RGB") for heading in CARDINAL_HEADINGS]


def _parse_prediction(response: Any) -> CountryPrediction:
    parsed = getattr(response, "parsed", None)
    if isinstance(parsed, CountryPrediction):
        return parsed
    if parsed is not None:
        return CountryPrediction.model_validate(parsed)
    text = (getattr(response, "text", "") or "").strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    return CountryPrediction.model_validate(json.loads(text))


def _usage_event(response: Any, *, model: str, latency_ms: int) -> dict[str, Any]:
    metadata = getattr(response, "usage_metadata", None)
    if metadata is None:
        metadata = getattr(response, "usage", None)

    def value(*names: str) -> int:
        for name in names:
            candidate = getattr(metadata, name, None) if metadata is not None else None
            if candidate is None and isinstance(metadata, Mapping):
                candidate = metadata.get(name)
            if candidate is not None:
                return int(candidate)
        return 0

    return {
        "component": "direct-baseline",
        "model": model,
        "input_tokens": value("prompt_token_count", "input_tokens"),
        "output_tokens": value("candidates_token_count", "output_tokens"),
        "image_tokens": value("thoughts_token_count", "image_tokens"),
        "latency_ms": latency_ms,
    }


def run_gemini_baseline(
    client: GeminiClient,
    view_paths: Mapping[int, Path],
    *,
    model: str,
    max_output_tokens: int = 1200,
    max_attempts: int = 2,
) -> BaselineRun:
    """Run one direct Gemini baseline over the canonical four-view input."""
    views = _load_views(view_paths)
    started = time.perf_counter()
    try:
        prompt = BASELINE_PROMPT
        for attempt in range(max_attempts):
            response = client.models.generate_content(
                model=model,
                contents=[*views, prompt],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=CountryPrediction,
                    max_output_tokens=max_output_tokens,
                ),
            )
            try:
                prediction = _parse_prediction(response)
                break
            except (json.JSONDecodeError, ValueError, TypeError) as exc:
                if attempt == max_attempts - 1:
                    raise RuntimeError(
                        "Gemini returned invalid or truncated baseline JSON after "
                        f"{max_attempts} attempts"
                    ) from exc
                prompt = (
                    BASELINE_PROMPT
                    + "\nYour previous response was incomplete. Return only a compact, complete JSON object."
                )
        else:
            raise RuntimeError("baseline retry loop exhausted")
    finally:
        for image in views:
            image.close()
    usage = _usage_event(response, model=model, latency_ms=round((time.perf_counter() - started) * 1000))
    return BaselineRun(prediction, usage)


def run_gemini_flash_baseline(client: GeminiClient, view_paths: Mapping[int, Path]) -> BaselineRun:
    return run_gemini_baseline(client, view_paths, model=GEMINI_FLASH_MODEL)


def run_gemini_pro_baseline(client: GeminiClient, view_paths: Mapping[int, Path]) -> BaselineRun:
    """Run the direct Gemini Pro baseline using the same payload as Flash."""
    return run_gemini_baseline(client, view_paths, model=GEMINI_PRO_MODEL)
