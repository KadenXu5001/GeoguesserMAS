from __future__ import annotations

from typing import Any, Annotated, TypedDict
from operator import add


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
    agent_todolist: dict[str, Any]
    specialist_used: str | None
    specialist_result: dict[str, Any] | None
    reexamine_results: Annotated[list[dict[str, Any]], add]
    final_prediction: dict[str, Any]
    usage: Annotated[list[UsageEvent], add]

