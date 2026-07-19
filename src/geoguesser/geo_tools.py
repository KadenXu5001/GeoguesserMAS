from __future__ import annotations

import json
from collections.abc import Mapping
from time import perf_counter
from typing import Any

from langchain.tools import ToolRuntime, tool
from langgraph.graph import END
from langgraph.types import Command
from langchain_core.messages import ToolMessage
from PIL import Image
from google.genai import types

from geoguesser.bbox import crop_normalized_bbox
from geoguesser.agent_runtime import apply_extraction_context
from geoguesser.extraction_runner import extract_cardinal_views
from geoguesser.model_payload import assert_model_payload_safe
from geoguesser.prediction import CountryPrediction
from geoguesser.runtime_state import GeoContext, GeoState


REEXAMINATION_MAX_SCORE_GAP = 10


def _extraction_metrics(extraction: Any, response: Any, latency_ms: int) -> dict[str, Any]:
    metadata = getattr(response, "usage_metadata", None) or getattr(response, "usage", None)

    def value(*names: str) -> int:
        for name in names:
            candidate = getattr(metadata, name, None) if metadata is not None else None
            if candidate is None and isinstance(metadata, Mapping):
                candidate = metadata.get(name)
            if candidate is not None:
                return int(candidate)
        return 0

    objects = 0
    present_categories = 0
    for category in extraction.model_dump().values():
        if not isinstance(category, dict):
            continue
        objects += len(category.get("objects", []))
        if category.get("status") in {"present", "present_but_illegible"}:
            present_categories += 1
    return {
        "status": "succeeded",
        "model": "gemini-3-flash-preview",
        "input_tokens": value("prompt_token_count", "input_tokens"),
        "output_tokens": value("candidates_token_count", "output_tokens"),
        "image_tokens": value("image_tokens"),
        "latency_ms": latency_ms,
        "present_categories": present_categories,
        "object_count": objects,
    }


@tool
def extract_visual_evidence(runtime: ToolRuntime[GeoContext, GeoState]) -> Command:
    """Extract structured visual evidence exactly once before MAS reasoning begins."""
    context = runtime.context
    budget = _budget_from_runtime(runtime)
    if context.get("extraction_attempted"):
        raise RuntimeError("visual extraction is single-use and has already been attempted")
    context["extraction_attempted"] = True
    budget.check_capacity()
    paths = context.get("heading_paths", {})
    client = context.get("gemini_client")
    if client is None or set(paths) != {0, 90, 180, 270}:
        raise RuntimeError("four heading paths and gemini_client are required for extraction")
    started = perf_counter()
    try:
        progress = context.get("progress")
        if callable(progress):
            progress("extract_visual_evidence: Gemini request started")
        response_holder: dict[str, Any] = {}

        def record(response: Any, latency_ms: int) -> None:
            response_holder["response"] = response
            response_holder["latency_ms"] = latency_ms

        extraction = extract_cardinal_views(
            client,
            paths,
            max_attempts=1,
            usage_callback=record,
            before_attempt=budget.check_capacity,
        )
        response = response_holder.get("response")
        metrics = _extraction_metrics(extraction, response, response_holder.get("latency_ms", round((perf_counter() - started) * 1000)))
        payload = extraction.model_dump()
        assert_model_payload_safe(payload)
        apply_extraction_context(context, payload)
        budget.record_usage(
            component="extraction",
            model=metrics["model"],
            input_tokens=metrics["input_tokens"],
            output_tokens=metrics["output_tokens"],
            image_tokens=metrics["image_tokens"],
            latency_ms=metrics["latency_ms"],
        )
        if callable(progress):
            progress(
                "extract_visual_evidence: Gemini request completed "
                f"({metrics['latency_ms']} ms; {metrics['object_count']} objects)"
            )
        context["orchestration_phase"] = "specialist"
        content = json.dumps({"status": "succeeded", "metrics": metrics, "extraction": payload}, ensure_ascii=False)
        return Command(
            update={
                "extraction": payload,
                "extraction_status": "succeeded",
                "extraction_metrics": metrics,
                "messages": [ToolMessage(content, tool_call_id=runtime.tool_call_id or "")],
            }
        )
    except Exception as exc:
        context["orchestration_phase"] = "failed"
        progress = context.get("progress")
        if callable(progress):
            progress(f"extract_visual_evidence: Gemini request failed ({exc})")
        metrics = {"status": "failed", "model": "gemini-3-flash-preview", "latency_ms": round((perf_counter() - started) * 1000), "error": str(exc)}
        return Command(
            goto=END,
            update={
                "extraction_status": "failed",
                "extraction_metrics": metrics,
                "messages": [ToolMessage(json.dumps(metrics), tool_call_id=runtime.tool_call_id or "")],
            },
        )


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
    return [extract_visual_evidence, emit_prediction, reexamine_region]
