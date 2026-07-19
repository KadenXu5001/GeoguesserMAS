from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path
from time import monotonic
from typing import Any

from geoguesser.runtime_budget import RuntimeBudget


_DATA_IMAGE = re.compile(r"data:image/[^;]+;base64,[A-Za-z0-9+/=]+")
_REDACTED_KEYS = {
    "coordinates",
    "filename",
    "ground_truth",
    "heading_paths",
    "image_id",
    "latitude",
    "longitude",
    "mapillary_image_id",
    "path",
    "paths",
}


def _safe_value(value: Any) -> Any:
    """Make decision details JSON-safe without leaking image bytes or dataset metadata."""
    if isinstance(value, Path):
        return "<path redacted>"
    if isinstance(value, Mapping):
        return {
            str(key): _safe_value(item)
            for key, item in value.items()
            if str(key).casefold() not in _REDACTED_KEYS
        }
    if isinstance(value, (list, tuple)):
        return [_safe_value(item) for item in value]
    if isinstance(value, set):
        return sorted(_safe_value(item) for item in value)
    if isinstance(value, str):
        redacted = _DATA_IMAGE.sub("<image redacted>", value)
        return redacted if len(redacted) <= 4_000 else redacted[:4_000] + "…"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)


def budget_snapshot(budget: Any) -> dict[str, Any]:
    if not isinstance(budget, RuntimeBudget):
        return {}
    return {
        "orchestrator_turns": budget.orchestrator_turns,
        "specialist_tasks": budget.specialist_tasks,
        "reexaminations": budget.reexaminations,
        "spent_usd": round(budget.spent_usd, 6),
    }


def record_decision(
    context: Mapping[str, Any] | None,
    event: str,
    summary: str,
    **details: Any,
) -> dict[str, Any]:
    """Append one observable, evidence-oriented decision event to the current run."""
    if context is None:
        return {"event": event, "summary": summary}
    log = context.get("decision_log")
    if not isinstance(log, list) and isinstance(context, dict):
        log = []
        context["decision_log"] = log
    if not isinstance(log, list):
        return {"event": event, "summary": summary}
    lock = context.get("decision_log_lock")

    def append() -> dict[str, Any]:
        budget = context.get("geo_budget")
        elapsed_ms = (
            round((monotonic() - budget.started_at) * 1_000)
            if isinstance(budget, RuntimeBudget)
            else 0
        )
        item = {
            "sequence": len(log) + 1,
            "elapsed_ms": elapsed_ms,
            "event": event,
            "phase": str(context.get("orchestration_phase", "unknown")),
            "summary": summary,
            "budget": budget_snapshot(budget),
            **{
                key: _safe_value(value)
                for key, value in details.items()
                if key.casefold() not in _REDACTED_KEYS
            },
        }
        log.append(item)
        return item

    if lock is None:
        return append()
    with lock:
        return append()


def snapshot_decision_log(context: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    if context is None or not isinstance(context.get("decision_log"), list):
        return []
    lock = context.get("decision_log_lock")
    if lock is None:
        return [dict(item) for item in context["decision_log"]]
    with lock:
        return [dict(item) for item in context["decision_log"]]
