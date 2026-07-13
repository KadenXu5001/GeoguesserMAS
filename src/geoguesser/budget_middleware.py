from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from langchain.agents.middleware.types import AgentMiddleware, ModelRequest, ToolCallRequest

from geoguesser.runtime_budget import RuntimeBudget


CONTEXT_KEY = "geo_budget"


def _budget(runtime: Any) -> RuntimeBudget:
    context = getattr(runtime, "context", None)
    value = context.get(CONTEXT_KEY) if isinstance(context, Mapping) else getattr(context, CONTEXT_KEY, None)
    if not isinstance(value, RuntimeBudget):
        raise RuntimeError(f"per-run runtime context must contain {CONTEXT_KEY!r}")
    return value


class BudgetMiddleware(AgentMiddleware[Any, Any, Any]):
    """Enforce MAS hard caps from the current invocation's runtime context."""

    def wrap_model_call(self, request: ModelRequest[Any], handler: Callable[..., Any]) -> Any:
        _budget(request.runtime).consume_orchestrator_turn()
        return handler(request)

    def wrap_tool_call(self, request: ToolCallRequest, handler: Callable[..., Any]) -> Any:
        name = request.tool_call.get("name")
        budget = _budget(request.runtime)
        if name == "task":
            budget.consume_specialist_task()
        elif name == "reexamine_region":
            budget.consume_reexamination()
        return handler(request)

