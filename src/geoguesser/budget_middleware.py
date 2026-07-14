from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from time import perf_counter
from typing import Any

from langchain.agents.middleware.types import AgentMiddleware, ModelRequest, ToolCallRequest
from langchain_core.messages import ToolMessage

from geoguesser.runtime_budget import RuntimeBudget
from geoguesser.specialist_cache import SpecialistCache


CONTEXT_KEY = "geo_budget"


def _budget(runtime: Any) -> RuntimeBudget:
    context = getattr(runtime, "context", None)
    value = context.get(CONTEXT_KEY) if isinstance(context, Mapping) else getattr(context, CONTEXT_KEY, None)
    if not isinstance(value, RuntimeBudget):
        raise RuntimeError(f"per-run runtime context must contain {CONTEXT_KEY!r}")
    return value


def _continues_after_todo(request: Any) -> bool:
    """TodoMiddleware requires a model continuation after ``write_todos``.

    That continuation is planning bookkeeping, not a second geographic decision turn.
    """
    messages = getattr(request, "messages", []) or []
    if not messages:
        return False
    last = messages[-1]
    tool_call_id = getattr(last, "tool_call_id", None)
    if not tool_call_id:
        return False
    for message in reversed(messages[:-1]):
        for tool_call in getattr(message, "tool_calls", []) or []:
            if tool_call.get("id") == tool_call_id:
                return tool_call.get("name") == "write_todos"
    return False


def _request_trace(request: Any) -> dict[str, Any]:
    messages = getattr(request, "messages", []) or []
    last = messages[-1] if messages else None
    return {
        "message_count": len(messages),
        "last_type": type(last).__name__ if last is not None else None,
        "last_name": getattr(last, "name", None),
        "last_tool_call_id": getattr(last, "tool_call_id", None),
        "last_tool_calls": [
            call.get("name") for call in (getattr(last, "tool_calls", None) or [])
        ],
        "continues_after_todo": _continues_after_todo(request),
    }


class BudgetMiddleware(AgentMiddleware[Any, Any, Any]):
    """Enforce MAS hard caps from the current invocation's runtime context."""

    def __init__(
        self,
        *,
        max_output_tokens: int = 400,
        component: str = "orchestrator",
        specialist_cache: SpecialistCache | None = None,
    ) -> None:
        self.max_output_tokens = max_output_tokens
        self.component = component
        self.specialist_cache = specialist_cache or SpecialistCache()

    def wrap_model_call(self, request: ModelRequest[Any], handler: Callable[..., Any]) -> Any:
        budget = _budget(request.runtime)
        budget.check_capacity()
        if not _continues_after_todo(request):
            try:
                budget.consume_orchestrator_turn()
            except Exception as exc:
                raise type(exc)(f"{exc}; request_trace={_request_trace(request)}") from exc
        settings = dict(getattr(request, "model_settings", None) or {})
        model_object = getattr(request, "model", None)
        model_name = str(getattr(model_object, "model", model_object or "")).lower()
        provider_limit_key = "max_output_tokens" if "gemini" in model_name else "max_tokens"
        current_limit = settings.get(provider_limit_key) or settings.get("max_tokens")
        settings[provider_limit_key] = (
            min(current_limit, self.max_output_tokens)
            if current_limit
            else self.max_output_tokens
        )
        if provider_limit_key != "max_tokens":
            settings.pop("max_tokens", None)
        started = perf_counter()
        bounded_request = request.override(model_settings=settings) if hasattr(request, "override") else request
        response = handler(bounded_request)
        usage = getattr(getattr(response, "result", None), "usage_metadata", None)
        if isinstance(usage, Mapping):
            budget.record_usage(
                component=self.component,
                model=str(getattr(request.model, "model", request.model)),
                input_tokens=int(usage.get("input_tokens", 0) or 0),
                output_tokens=int(usage.get("output_tokens", 0) or 0),
                latency_ms=round((perf_counter() - started) * 1000),
            )
        return response

    def wrap_tool_call(self, request: ToolCallRequest, handler: Callable[..., Any]) -> Any:
        name = request.tool_call.get("name")
        budget = _budget(request.runtime)
        budget.check_capacity()
        if name == "task":
            args = request.tool_call.get("args") or {}
            specialist = (
                args.get("subagent_type")
                or args.get("specialist")
                or args.get("name")
                or "unknown-specialist"
            ) if isinstance(args, Mapping) else "unknown-specialist"
            cached, cache_error = self.specialist_cache.get(str(specialist))
            if cache_error:
                budget.capacity_warning = cache_error
                return ToolMessage(
                    content=f"WARNING: {cache_error}; stop all specialist calls and finalize.",
                    tool_call_id=request.tool_call.get("id", ""),
                )
            if cached is not None:
                budget.consume_specialist_task(str(specialist))
                return ToolMessage(
                    content=cached if isinstance(cached, str) else json.dumps(cached, ensure_ascii=False),
                    tool_call_id=request.tool_call.get("id", ""),
                )
            if budget.specialist_tasks >= budget.max_specialist_tasks:
                return ToolMessage(
                    content="Specialist delegation cap reached; continue with existing specialist results.",
                    tool_call_id=request.tool_call.get("id", ""),
                )
            budget.consume_specialist_task(str(specialist))
            self.specialist_cache.mark_attempted(str(specialist))
            result = handler(request)
            content = getattr(result, "content", result)
            self.specialist_cache.put(str(specialist), content)
            return result
        elif name == "reexamine_region":
            if budget.reexaminations >= budget.max_reexaminations:
                return ToolMessage(
                    content="Re-examination cap reached; do not request another crop and finalize.",
                    tool_call_id=request.tool_call.get("id", ""),
                )
            budget.consume_reexamination()
        return handler(request)
