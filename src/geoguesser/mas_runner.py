from __future__ import annotations

import base64
import json
import mimetypes
from pathlib import Path
from typing import Any, Mapping

from geoguesser.agent_factory import create_geoguesser_agent
from geoguesser.agent_runtime import build_runtime_context
from geoguesser.cost_model import OPUS_BASELINE
from geoguesser.extraction import ExtractionOutput
from geoguesser.extraction_runner import extract_cardinal_views
from geoguesser.model_payload import assert_model_payload_safe
from geoguesser.runtime_budget import BudgetExceeded, RuntimeBudget


def _record_extraction_usage(budget: RuntimeBudget, response: Any, latency_ms: int) -> None:
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

    budget.record_usage(
        component="extraction",
        model="gemini-3-flash-preview",
        input_tokens=value("prompt_token_count", "input_tokens"),
        output_tokens=value("candidates_token_count", "output_tokens"),
        image_tokens=value("image_tokens"),
        latency_ms=latency_ms,
    )


def build_agent_input(
    extraction: ExtractionOutput,
    views: Mapping[int, Path] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Build the multimodal supervisor input.

    The supervisor receives the extracted description plus the four images. Dataset metadata
    and image paths are never serialized into the model-facing payload.
    """
    payload = {
        "extraction_description": extraction.model_dump(),
        "instruction": (
            "Use this description as a first pass, then scan all four images yourself. "
            "Correct unsupported description claims and use only visible evidence."
        ),
    }
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


def _capacity_result(row: Mapping[str, str], warning: str) -> dict[str, Any]:
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
    }


def run_mas_row(
    row: Mapping[str, str],
    *,
    gemini_client: Any,
    reference_repository: Any,
    reference_version: str,
    agent: Any | None = None,
    root: Path = Path("."),
) -> dict[str, Any]:
    views = {
        0: root / row["view_h000_path"],
        90: root / row["view_h090_path"],
        180: root / row["view_h180_path"],
        270: root / row["view_h270_path"],
    }
    budget = RuntimeBudget(opus_cost_usd=OPUS_BASELINE)
    try:
        budget.check_capacity()
        extraction = extract_cardinal_views(
            gemini_client,
            views,
            usage_callback=lambda response, latency: _record_extraction_usage(
                budget, response, latency
            ),
            before_attempt=budget.check_capacity,
        )
        budget.check_capacity()
        context = build_runtime_context(
            budget=budget,
            reference_repository=reference_repository,
            reference_version=reference_version,
            heading_paths=views,
            gemini_client=gemini_client,
        )
        compiled_agent = agent or create_geoguesser_agent()
        result = compiled_agent.invoke(build_agent_input(extraction, views), context=context)
    except BudgetExceeded as exc:
        return _capacity_result(row, str(exc))
    prediction = result.get("final_prediction") or result.get("structured_response")
    if prediction is None:
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
    return {
        "dataset_version": row.get("dataset_version"),
        "split": row.get("split"),
        "image_id": row.get("mapillary_image_id"),
        "ground_truth": row.get("country"),
        "prediction": _as_document(prediction),
        "usage": budget.usage_events or [],
        "specialists_used": sorted(budget.specialists_used),
        "specialist_used": result.get("specialist_used") or (sorted(budget.specialists_used)[0] if budget.specialists_used else None),
        "reexamine_results": result.get("reexamine_results", []),
    }
