from __future__ import annotations

from typing import Any, Annotated, Callable
from typing_extensions import TypedDict
from operator import add
from pathlib import Path

from geoguesser.runtime_budget import RuntimeBudget
from geoguesser.tool_response_cache import ToolResponseCache


def merge_decision_logs(
    left: list[dict[str, Any]], right: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Merge append-only decision events without duplicating final snapshots."""
    merged = {item.get("sequence"): item for item in [*left, *right]}
    return [merged[key] for key in sorted(merged) if key is not None]


class UsageEvent(TypedDict, total=False):
    component: str
    model: str
    input_tokens: int
    output_tokens: int
    image_tokens: int
    cost_usd: float
    latency_ms: int


class GeoState(TypedDict, total=False):
    extraction: dict[str, Any]
    extraction_status: str
    extraction_metrics: dict[str, Any]
    agent_todolist: dict[str, Any]
    specialists_used: list[str]
    specialist_results: list[dict[str, Any]]
    reexamine_results: Annotated[list[dict[str, Any]], add]
    final_prediction: dict[str, Any]
    # Retained for framework compatibility; production finalization is performed by
    # the constitutionally required emit_prediction tool.
    structured_response: dict[str, Any]
    usage: Annotated[list[UsageEvent], add]
    decision_log: Annotated[list[dict[str, Any]], merge_decision_logs]


class GeoContext(TypedDict):
    geo_budget: RuntimeBudget
    reference_repository: Any
    reference_version: str
    heading_paths: dict[int, Path]
    gemini_client: Any
    reexamine_model: str
    require_specialist: bool
    reference_lookup_categories: set[str]
    reference_lookup_details: list[dict[str, str]]
    scan_allowed_categories: set[str]
    scan_objects: dict[str, set[str]]
    active_specialist: str | None
    specialist_tool_calls: dict[str, int]
    todo_plan: list[dict[str, str]]
    tool_response_cache: ToolResponseCache
    progress: Callable[[str], None]
    orchestration_phase: str
    extraction_attempted: bool
    final_prediction: dict[str, Any] | None
    decision_log: list[dict[str, Any]]
    decision_log_lock: Any
