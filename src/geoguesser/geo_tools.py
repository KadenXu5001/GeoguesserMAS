from __future__ import annotations

import json
from typing import Any

from langchain.tools import ToolRuntime, tool
from langgraph.graph import END
from langgraph.types import Command
from langchain_core.messages import ToolMessage
from PIL import Image
from google.genai import types

from geoguesser.bbox import crop_normalized_bbox
from geoguesser.prediction import CountryPrediction
from geoguesser.runtime_state import GeoContext, GeoState


REEXAMINATION_MAX_SCORE_GAP = 10


def _budget_from_runtime(runtime: ToolRuntime[GeoContext, GeoState]) -> Any:
    context = runtime.context
    budget = context.get("geo_budget") if isinstance(context, dict) else getattr(context, "geo_budget", None)
    if budget is None:
        raise RuntimeError("geo_budget is required in per-run runtime context")
    return budget


@tool
def emit_prediction(
    country: str,
    confidence: int,
    alternatives: list[str],
    evidence: list[str],
    runtime: ToolRuntime[GeoContext, GeoState],
) -> Command:
    """Emit one worldwide country prediction and terminate the supervisor run."""
    prediction = CountryPrediction(
        country=country,
        confidence=confidence,
        alternatives=alternatives,
        evidence=evidence,
    )
    budget = _budget_from_runtime(runtime)
    if runtime.context.get("require_specialist", False) and budget.specialist_tasks < 1:
        raise RuntimeError("MAS requires at least one specialist delegation before prediction")
    content = prediction.model_dump_json()
    return Command(
        goto=END,
        update={
            "final_prediction": prediction.model_dump(),
            "messages": [ToolMessage(content, tool_call_id=runtime.tool_call_id or "")],
        },
    )


@tool
def reexamine_region(
    heading: int,
    bbox: list[int],
    question: str,
    signal_a: str,
    score_a: int,
    signal_b: str,
    score_b: int,
    runtime: ToolRuntime[GeoContext, GeoState],
) -> Command:
    """Inspect one padded region only when two distinct close signals compete."""
    if heading not in {0, 90, 180, 270}:
        raise ValueError("heading must be one of 0, 90, 180, or 270")
    if len(bbox) != 4:
        raise ValueError("bbox must contain [ymin, xmin, ymax, xmax]")
    if not question.strip():
        raise ValueError("question must not be empty")
    if (
        not signal_a.strip()
        or not signal_b.strip()
        or signal_a.strip().lower() == signal_b.strip().lower()
    ):
        raise ValueError("re-examination requires two distinct competing signals")
    if not 0 <= score_a <= 100 or not 0 <= score_b <= 100:
        raise ValueError("signal scores must be between 0 and 100")
    if abs(score_a - score_b) > REEXAMINATION_MAX_SCORE_GAP:
        raise ValueError("re-examination requires competing signals within 10 confidence points")

    budget = _budget_from_runtime(runtime)
    paths = runtime.context.get("heading_paths", {})
    path = paths.get(heading) or paths.get(str(heading))
    client = runtime.context.get("gemini_client")
    model = runtime.context.get("reexamine_model", "gemini-3-flash-preview")
    if path is None or client is None:
        raise RuntimeError("heading_paths and gemini_client are required in runtime context")

    with Image.open(path) as view:
        crop = crop_normalized_bbox(view, bbox, padding_fraction=0.25)
        response = client.models.generate_content(
            model=model,
            contents=[crop, question.strip()],
            config=types.GenerateContentConfig(
                response_mime_type="text/plain",
                max_output_tokens=350,
                thinking_config=types.ThinkingConfig(thinking_budget=0),
            ),
        )
    result = {
        "heading": heading,
        "question": question.strip(),
        "signal_a": signal_a.strip(),
        "score_a": score_a,
        "signal_b": signal_b.strip(),
        "score_b": score_b,
        "answer": response.text.strip(),
    }
    content = json.dumps(result, ensure_ascii=False)
    return Command(
        update={
            "reexamine_results": [result],
            "messages": [ToolMessage(content, tool_call_id=runtime.tool_call_id or "")],
        }
    )


def geoguesser_tools() -> list[Any]:
    return [emit_prediction, reexamine_region]
