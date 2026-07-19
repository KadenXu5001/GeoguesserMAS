from __future__ import annotations

import base64
import json
import mimetypes
import re
from pathlib import Path
from typing import Any, Callable, Mapping

from geoguesser.agent_factory import create_geoguesser_agent
from geoguesser.agent_runtime import build_runtime_context
from geoguesser.cost_model import OPUS_BASELINE
from geoguesser.decision_log import record_decision, snapshot_decision_log
from geoguesser.model_payload import assert_model_payload_safe
from geoguesser.runtime_budget import BudgetExceeded, RuntimeBudget


def build_agent_input(
    extraction: Any | None = None,
    views: Mapping[int, Path] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Build the multimodal supervisor input.

    The supervisor receives the extracted description plus the four images. Dataset metadata
    and image paths are never serialized into the model-facing payload.
    """
    payload = {
        "instruction": (
            "Call extract_visual_evidence first. Then use its result as a first pass and scan all "
            "four images yourself. Correct unsupported extraction claims and use only visible evidence."
        ),
    }
    if extraction is not None:
        payload["extraction_description"] = extraction.model_dump()
    assert_model_payload_safe(payload)
    description = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    content: list[dict[str, Any]] = [{"type": "text", "text": description}]
    if views is not None:
        if set(views) != {0, 90, 180, 270}:
            raise ValueError("exactly four cardinal views are required")
        for heading in (0, 90, 180, 270):
            path = views[heading]
            mime_type = mimetypes.guess_type(path.name)[0] or "image/jpeg"
            encoded = base64.b64encode(path.read_bytes()).decode("ascii")
            content.append(
                {"type": "text", "text": f"Cardinal view heading: {heading} degrees."}
            )
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime_type};base64,{encoded}"},
                }
            )
    return {
        "messages": [
            {
                "role": "user",
                "content": content if views is not None else description,
            }
        ]
    }


def _as_document(value: Any) -> Any:
    return value.model_dump() if hasattr(value, "model_dump") else value


def _evidence_tokens(value: str) -> set[str]:
    return {
        token for token in re.findall(r"[a-z0-9]+", value.casefold())
        if len(token) > 2 and token not in {"and", "the", "this", "that", "with", "from"}
    }


def build_informed_evidence(
    prediction: Mapping[str, Any],
    extraction: Mapping[str, Any],
    lookups: list[Mapping[str, str]],
) -> list[dict[str, Any]]:
    """Associate final evidence text with exact bounded objects used by successful lookups."""
    objects_by_observation: dict[str, dict[str, Any]] = {}
    for category, category_data in extraction.items():
        if not isinstance(category_data, Mapping):
            continue
        for item in category_data.get("objects", []):
            if (
                isinstance(item, Mapping)
                and isinstance(item.get("observation"), str)
                and isinstance(item.get("bbox"), Mapping)
            ):
                objects_by_observation[item["observation"]] = {
                    "category": category,
                    "heading": item.get("heading"),
                    "bbox": dict(item["bbox"]),
                    "observation": item["observation"],
                }

    remaining = [text for text in prediction.get("evidence", []) if isinstance(text, str) and text.strip()]
    informed: list[dict[str, Any]] = []
    for lookup in lookups:
        if not remaining or len(informed) >= 3:
            break
        observation = lookup.get("object_observation", "")
        bounded = objects_by_observation.get(observation)
        if not bounded:
            continue
        observation_tokens = _evidence_tokens(observation)
        best_index, best_score = -1, 0
        for index, evidence in enumerate(remaining):
            evidence_tokens = _evidence_tokens(evidence)
            score = len(observation_tokens & evidence_tokens)
            if score > best_score:
                best_index, best_score = index, score
        if best_index < 0:
            continue
        description = remaining.pop(best_index)
        informed.append({
            "id": f"informed-{len(informed) + 1}",
            "description": description,
            "tool": lookup.get("tool"),
            "lookupCategory": lookup.get("category"),
            **bounded,
        })
    return informed


def _capacity_result(
    row: Mapping[str, str], warning: str, decision_log: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    return {
        "dataset_version": row.get("dataset_version"),
        "split": row.get("split"),
        "image_id": row.get("mapillary_image_id"),
        "ground_truth": row.get("country"),
        "prediction": None,
        "suggestion": "MAS capacity reached; stop inference and retry later with a fresh run.",
        "warning": f"WARNING: maximum MAS capacity reached ({warning}); no further API calls will be made.",
        "usage": [],
        "specialists_used": [],
        "specialist_used": None,
        "reexamine_results": [],
        "decision_log": decision_log or [],
    }


def run_mas_row(
    row: Mapping[str, str],
    *,
    gemini_client: Any,
    reference_repository: Any,
    reference_version: str,
    agent: Any | None = None,
    root: Path = Path("."),
    progress: Callable[[str], None] | None = None,
    trace_callbacks: list[Any] | None = None,
) -> dict[str, Any]:
    report = progress or (lambda message: None)
    views = {
        0: root / row["view_h000_path"],
        90: root / row["view_h090_path"],
        180: root / row["view_h180_path"],
        270: root / row["view_h270_path"],
    }
    # Graph construction is one-time setup, not per-panorama model/tool inference. Keep it
    # outside the hard inference budget; callers running batches should pass a shared agent.
    compiled_agent = agent or create_geoguesser_agent()
    budget = RuntimeBudget(opus_cost_usd=OPUS_BASELINE)
    context = None
    try:
        report("starting supervisor; extraction is the required first tool call")
        budget.check_capacity()
        context = build_runtime_context(
            budget=budget,
            reference_repository=reference_repository,
            reference_version=reference_version,
            heading_paths=views,
            gemini_client=gemini_client,
            extraction=None,
            progress=report,
        )
        record_decision(
            context,
            "run_started",
            "MAS invocation started with the canonical todo phase.",
            required_first_tool="write_todos",
            reason_code="production_protocol",
        )
        report("supervisor running; selecting specialist and tools")
        invoke_config = {"callbacks": trace_callbacks} if trace_callbacks else None
        result = compiled_agent.invoke(
            build_agent_input(None, views), context=context, config=invoke_config
        )
        report("supervisor graph completed; validating prediction")
    except BudgetExceeded as exc:
        record_decision(
            context,
            "capacity_terminated",
            "Runtime capacity stopped the MAS before another API call.",
            warning=str(exc),
            reason_code="hard_runtime_or_cost_limit",
        )
        return _capacity_result(row, str(exc), snapshot_decision_log(context))
    prediction = (
        result.get("final_prediction")
        or result.get("structured_response")
        or context.get("final_prediction")
    )
    if prediction is None:
        extraction_metrics = result.get("extraction_metrics")
        if result.get("extraction_status") == "failed":
            detail = (
                extraction_metrics.get("error")
                if isinstance(extraction_metrics, Mapping)
                else None
            )
            raise RuntimeError(
                "MAS visual extraction failed before specialist delegation or prediction"
                + (f": {detail}" if detail else ".")
            )
        message_summary = []
        for message in result.get("messages", [])[-3:]:
            content = getattr(message, "content", None)
            content_blocks = []
            if isinstance(content, list):
                content_blocks = [
                    block.get("type") if isinstance(block, dict) else type(block).__name__
                    for block in content
                ]
            message_summary.append(
                {
                    "type": type(message).__name__,
                    "name": getattr(message, "name", None),
                    "tool_calls": [call.get("name") for call in (getattr(message, "tool_calls", None) or [])],
                    "content_type": type(getattr(message, "content", None)).__name__,
                    "content_blocks": content_blocks,
                }
            )
        raise RuntimeError(
            "MAS completed without final_prediction or structured_response; "
            f"state_keys={sorted(result)} message_tail={message_summary}"
        )
    prediction_document = _as_document(prediction)
    extraction_document = result.get("extraction") or {}
    return {
        "dataset_version": row.get("dataset_version"),
        "split": row.get("split"),
        "image_id": row.get("mapillary_image_id"),
        "ground_truth": row.get("country"),
        "prediction": prediction_document,
        "extraction": extraction_document,
        "informed_evidence": build_informed_evidence(
            prediction_document,
            extraction_document,
            context.get("reference_lookup_details", []),
        ),
        "usage": budget.usage_events or [],
        "specialists_used": sorted(budget.specialists_used),
        "specialist_used": result.get("specialist_used") or (sorted(budget.specialists_used)[0] if budget.specialists_used else None),
        "reexamine_results": result.get("reexamine_results", []),
        "todos": result.get("todos", context.get("todo_plan", [])),
        "decision_log": snapshot_decision_log(context),
    }
