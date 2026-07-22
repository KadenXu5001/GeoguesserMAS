from __future__ import annotations

import base64
import json
import mimetypes
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Protocol

from google.genai import types
from PIL import Image

from geoguesser.cost_model import CLAUDE_OPUS, Pricing, token_cost
from geoguesser.prediction import CountryPrediction


CARDINAL_HEADINGS = (0, 90, 180, 270)
GEMINI_FLASH_MODEL = "gemini-3-flash-preview"
GEMINI_PRO_MODEL = "gemini-3.1-pro-preview"
CLAUDE_OPUS_MODEL = "claude-opus-4-8"
BASELINE_PROMPT = """Identify the country shown in these four cardinal street-scene views.
Return one worldwide country prediction, up to three alternatives, concise visible
evidence, and confidence from 0 to 100. Use only what is visible in the images; do not
infer or mention filenames, image IDs, coordinates, timestamps, or hidden metadata."""


class GeminiClient(Protocol):
    models: Any


class AnthropicClient(Protocol):
    def create_message(self, payload: Mapping[str, Any]) -> Mapping[str, Any]: ...


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
        "reasoning_tokens": value("thoughts_token_count", "reasoning_tokens"),
        "image_tokens": 0,
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


def run_claude_opus_baseline(
    client: AnthropicClient,
    view_paths: Mapping[int, Path],
    *,
    model: str = CLAUDE_OPUS_MODEL,
    pricing: Pricing = CLAUDE_OPUS,
    max_output_tokens: int = 1200,
) -> BaselineRun:
    """Run one direct, single-call Claude baseline over the canonical four views."""
    if set(view_paths) != set(CARDINAL_HEADINGS):
        raise ValueError("exactly four cardinal views are required")
    content: list[dict[str, Any]] = []
    for heading in CARDINAL_HEADINGS:
        path = view_paths[heading]
        media_type = mimetypes.guess_type(path.name)[0] or "image/jpeg"
        content.extend(
            [
                {"type": "text", "text": f"Cardinal view heading: {heading} degrees."},
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": media_type,
                        "data": base64.b64encode(path.read_bytes()).decode("ascii"),
                    },
                },
            ]
        )
    content.append({"type": "text", "text": BASELINE_PROMPT})
    payload = {
        "model": model,
        "max_tokens": max_output_tokens,
        "messages": [{"role": "user", "content": content}],
        "output_config": {
            "format": {
                "type": "json_schema",
                "schema": CountryPrediction.model_json_schema(),
            }
        },
    }
    started = time.perf_counter()
    response = client.create_message(payload)
    prediction_text = next(
        (
            block.get("text")
            for block in response.get("content", [])
            if isinstance(block, Mapping)
            and block.get("type") == "text"
            and isinstance(block.get("text"), str)
        ),
        None,
    )
    if prediction_text is None:
        raise RuntimeError("Claude response did not contain a structured text result")
    prediction = CountryPrediction.model_validate_json(prediction_text)
    raw_usage = response.get("usage") or {}
    input_tokens = int(raw_usage.get("input_tokens", 0))
    output_tokens = int(raw_usage.get("output_tokens", 0))
    usage = {
        "component": "direct-baseline",
        "model": response.get("model") or model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "image_tokens": 0,
        "input_tokens_include_images": True,
        "cost_usd": token_cost(pricing, input_tokens, output_tokens),
        "latency_ms": round((time.perf_counter() - started) * 1000),
    }
    return BaselineRun(prediction, usage)
