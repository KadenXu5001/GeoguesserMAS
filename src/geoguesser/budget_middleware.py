from __future__ import annotations

from collections.abc import Callable, Mapping
from time import perf_counter
from typing import Any

from langchain.agents.middleware.types import AgentMiddleware, ModelRequest, ToolCallRequest, hook_config
from langchain_core.messages import HumanMessage, ToolMessage

from geoguesser.runtime_budget import BudgetExceeded, RuntimeBudget
from geoguesser.specialist_result import normalize_specialist_result


CONTEXT_KEY = "geo_budget"


_SPECIALIST_CATEGORIES = {
    "urban-specialist": {
        "driving_side", "license_plates", "road_markings", "language_script",
        "country_domains", "bollards", "chevrons_guardrails", "vehicles",
        "urban_architecture", "urban_utility_poles", "urban_signage",
        "street_names_addresses", "businesses_domains", "sidewalks_curbs", "public_transit",
    },
    "rural-specialist": {
        "driving_side", "license_plates", "road_markings", "language_script",
        "country_domains", "bollards", "chevrons_guardrails", "vehicles",
        "soil_geology", "vegetation_biomes", "terrain_scenery", "climate",
        "agriculture_land_use", "rural_architecture", "rural_utility_poles",
        "rural_roadside_features",
    },
}

_TODO_STATUSES = {"pending", "in_progress", "completed"}

MAS_TODO_CONTENTS = (
    "Extract visual evidence with extract_visual_evidence",
    "Delegate to urban-specialist or rural-specialist with task",
    "Optionally reexamine_region only for two close country signals",
    "Emit final country prediction with emit_prediction",
)


def _todo_validation_error(request: ToolCallRequest, context: Mapping[str, Any]) -> str | None:
    """Enforce the MAS's single, forward-only todo plan before the tool runs."""
    args = request.tool_call.get("args") or {}
    todos = args.get("todos") if isinstance(args, Mapping) else None
    if not isinstance(todos, list) or not todos:
        return "write_todos requires a non-empty todo list"

    normalized: list[dict[str, str]] = []
    for item in todos:
        if not isinstance(item, Mapping):
            return "each todo must be an object with content and status"
        content = item.get("content")
        status = item.get("status")
        if not isinstance(content, str) or not content.strip():
            return "each todo requires non-empty content"
        if status not in _TODO_STATUSES:
            return "each todo status must be pending, in_progress, or completed"
        normalized.append({"content": content, "status": status})

    previous = context.get("todo_plan")
    if not previous:
        if tuple(item["content"] for item in normalized) != MAS_TODO_CONTENTS:
            return (
                "the initial todo plan must use this exact order and wording: "
                + " | ".join(MAS_TODO_CONTENTS)
            )
        if normalized[0]["status"] != "in_progress":
            return "the first todo must be in_progress in the initial plan"
        if normalized[-1]["status"] == "completed":
            return "the final prediction todo cannot be completed before emit_prediction"
        if any(item["status"] != "pending" for item in normalized[1:]):
            return "future todos must be pending in the initial plan"
        return None

    if len(previous) != len(normalized) or any(
        old["content"] != new["content"]
        for old, new in zip(previous, normalized)
    ):
        return "todo updates may only update statuses on the existing plan"

    allowed_transitions = {
        "pending": {"pending", "in_progress"},
        "in_progress": {"in_progress", "completed"},
        "completed": {"completed"},
    }
    for old, new in zip(previous, normalized):
        if new["status"] not in allowed_transitions[old["status"]]:
            return "todo statuses must progress pending -> in_progress -> completed"
    if normalized[-1]["status"] == "completed":
        return "the final prediction todo cannot be completed before emit_prediction"
    return None


def _with_authorized_objects(
    request: ToolCallRequest,
    specialist: str,
    context: Mapping[str, Any] | None,
) -> ToolCallRequest:
    if context is None or not isinstance(request.tool_call.get("args"), Mapping):
        return request
    objects = context.get("scan_objects", {})
    categories = _SPECIALIST_CATEGORIES.get(specialist, set())
    lines = [
        f"- {category}: {observation}"
        for category in sorted(categories)
        for observation in sorted(objects.get(category, set()))
    ]
    if not lines:
        return request
    args = request.tool_call["args"]
    description = str(args.get("description", ""))
    authorized = (
        "\n\nAUTHORIZED EXTRACTION OBJECTS (copy observation text verbatim; "
        "use only a category/object pair listed here):\n" + "\n".join(lines)
    )
    modified_call = {
        **request.tool_call,
        "args": {**args, "description": description + authorized},
    }
    return request.override(tool_call=modified_call)


def _budget(runtime: Any) -> RuntimeBudget:
    context = getattr(runtime, "context", None)
    value = context.get(CONTEXT_KEY) if isinstance(context, Mapping) else getattr(context, CONTEXT_KEY, None)
    if not isinstance(value, RuntimeBudget):
        raise RuntimeError(f"per-run runtime context must contain {CONTEXT_KEY!r}")
    return value


def _context(runtime: Any) -> Mapping[str, Any] | None:
    value = getattr(runtime, "context", None)
    return value if isinstance(value, Mapping) else None


def _model_tool_name(tool: Any) -> str | None:
    """Return a model-visible tool name for BaseTool and provider-dict forms."""
    if isinstance(tool, Mapping):
        function = tool.get("function")
        if isinstance(function, Mapping):
            return function.get("name")
        return tool.get("name")
    return getattr(tool, "name", None)


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


def _is_initial_todo_call(request: Any, context: Mapping[str, Any] | None) -> bool:
    """The initial planning model call is bookkeeping, not a geographic decision turn."""
    if context is None or context.get("orchestration_phase") != "todo":
        return False
    if context.get("todo_plan"):
        return False
    messages = getattr(request, "messages", []) or []
    return not any(getattr(message, "tool_calls", None) for message in messages)


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
    ) -> None:
        self.max_output_tokens = max_output_tokens
        self.component = component

    @hook_config(can_jump_to=["model"])
    def after_model(self, state: Any, runtime: Any) -> dict[str, Any] | None:
        """Do not let a plain supervisor response terminate an active MAS phase."""
        context = getattr(runtime, "context", None)
        phase = context.get("orchestration_phase") if isinstance(context, Mapping) else None
        if phase not in {"todo", "extraction", "specialist"}:
            return None
        budget = context.get(CONTEXT_KEY) if isinstance(context, Mapping) else None
        messages = state.get("messages", []) if isinstance(state, Mapping) else []
        if not messages or getattr(messages[-1], "tool_calls", None):
            return None
        if phase == "todo":
            next_action = "write_todos"
        elif phase == "extraction":
            next_action = "extract_visual_evidence"
        elif isinstance(budget, RuntimeBudget) and budget.specialist_tasks == 0:
            next_action = "task to delegate to a configured specialist"
        else:
            next_action = "the next required MAS tool"
        return {
            "messages": [
                HumanMessage(
                    content=f"Continue the required MAS workflow. Call {next_action} now; do not return plain text."
                )
            ],
            "jump_to": "model",
        }

    def wrap_model_call(self, request: ModelRequest[Any], handler: Callable[..., Any]) -> Any:
        budget = _budget(request.runtime)
        budget.check_capacity()
        context = _context(request.runtime)
        continues_after_todo = _continues_after_todo(request)
        extraction_selection = (
            continues_after_todo
            and context is not None
            and context.get("orchestration_phase") == "extraction"
        )
        if (
            not _is_initial_todo_call(request, context)
            and (not continues_after_todo or extraction_selection)
        ):
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
        # The production contract is tool-driven: while the orchestration is active, the
        # supervisor must choose a tool rather than terminate with an ordinary text message.
        # ``emit_prediction`` is the only valid terminal path; wrap_tool_call enforces the
        # phase-specific ordering when the model makes its choice.
        overrides = {"model_settings": settings}
        tools = getattr(request, "tools", None)
        if tools is not None and budget.specialist_tasks > 0:
            # A mixed-scene decision may issue both specialist calls together. Once that
            # decision has executed, later model turns must not see ``task`` again.
            overrides["tools"] = [tool for tool in tools if _model_tool_name(tool) != "task"]
        if context := _context(request.runtime):
            if context.get("orchestration_phase") != "done":
                # The first substantive supervisor call must not deliberate among all tools.
                # Bind it to the exact extraction tool; later phases may choose among tools.
                overrides["tool_choice"] = (
                    "extract_visual_evidence"
                    if context.get("orchestration_phase") == "extraction"
                    else "any"
                )
        bounded_request = request.override(**overrides) if hasattr(request, "override") else request
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
        if context is not None and context.get("orchestration_phase") == "extraction":
            progress = context.get("progress")
            if callable(progress):
                progress(
                    "supervisor extraction-tool selection completed "
                    f"({round((perf_counter() - started) * 1000)} ms)"
                )
        return response

    def wrap_tool_call(self, request: ToolCallRequest, handler: Callable[..., Any]) -> Any:
        name = request.tool_call.get("name")
        budget = _budget(request.runtime)
        budget.check_capacity()
        context = _context(request.runtime)
        phase = context.get("orchestration_phase") if context is not None else None
        if phase is not None and name == "write_todos" and phase not in {"todo", "specialist"}:
            return ToolMessage(
                content="Todo updates are closed after finalization; continue with the required next tool.",
                tool_call_id=request.tool_call.get("id", ""),
            )
        if phase is not None and name == "task" and phase != "specialist":
            return ToolMessage(
                content="Specialist delegation is only allowed after the initial todo plan and before reexamination.",
                tool_call_id=request.tool_call.get("id", ""),
            )
        if phase is not None and name == "extract_visual_evidence" and phase != "extraction":
            return ToolMessage(
                content="Visual extraction is only allowed once immediately after the initial todo plan.",
                tool_call_id=request.tool_call.get("id", ""),
            )
        if phase is not None and name == "reexamine_region" and phase != "specialist":
            return ToolMessage(
                content="Reexamination is only allowed after specialist evidence and may occur once.",
                tool_call_id=request.tool_call.get("id", ""),
            )
        if name == "reexamine_region" and budget.specialist_tasks < 1:
            return ToolMessage(
                content="Reexamination requires at least one completed specialist task first.",
                tool_call_id=request.tool_call.get("id", ""),
            )
        if phase is not None and name == "emit_prediction" and phase not in {"specialist", "finalizing"}:
            return ToolMessage(
                content="Prediction is only allowed after specialist evidence.",
                tool_call_id=request.tool_call.get("id", ""),
            )
        if name == "write_todos":
            if context is not None:
                todo_error = _todo_validation_error(request, context)
                if todo_error:
                    return ToolMessage(
                        content=f"Invalid MAS todo plan: {todo_error}",
                        tool_call_id=request.tool_call.get("id", ""),
                    )
            result = handler(request)
            if context is not None:
                args = request.tool_call.get("args") or {}
                context["todo_plan"] = [
                    {"content": item["content"], "status": item["status"]}
                    for item in args["todos"]
                ]
            if context is not None and context.get("orchestration_phase") == "todo":
                context["orchestration_phase"] = "extraction"
            return result
        if name == "extract_visual_evidence":
            if context is not None and context.get("extraction_attempted"):
                return ToolMessage(
                    content="Visual extraction has already been attempted; do not call it again.",
                    tool_call_id=request.tool_call.get("id", ""),
                )
            return handler(request)
        if name == "task":
            args = request.tool_call.get("args") or {}
            specialist = (
                args.get("subagent_type")
                or args.get("specialist")
                or args.get("name")
                or "unknown-specialist"
            ) if isinstance(args, Mapping) else "unknown-specialist"
            progress = getattr(request.runtime, "context", {}).get("progress")
            try:
                budget.consume_specialist_task(str(specialist))
            except BudgetExceeded as exc:
                return ToolMessage(
                    content=f"{exc}; do not call this specialist again; continue with the next required tool.",
                    tool_call_id=request.tool_call.get("id", ""),
                )
            if callable(progress):
                progress(f"delegating to {specialist}")
            request = _with_authorized_objects(request, str(specialist), context)
            previous_specialist = context.get("active_specialist") if context is not None else None
            if context is not None:
                context["active_specialist"] = str(specialist)
            try:
                result = handler(request)
            finally:
                if context is not None:
                    context["active_specialist"] = previous_specialist
            normalized, _ = normalize_specialist_result(
                str(specialist),
                result,
                tool_call_id=request.tool_call.get("id", ""),
                tool_name="task",
            )
            if callable(progress):
                progress(f"{specialist} returned standardized JSON result")
            return normalized
        elif name == "reexamine_region":
            if budget.reexaminations >= budget.max_reexaminations:
                return ToolMessage(
                    content="Re-examination cap reached; do not request another crop and finalize.",
                    tool_call_id=request.tool_call.get("id", ""),
                )
            budget.consume_reexamination()
            if context is not None:
                context["orchestration_phase"] = "finalizing"
        elif name == "emit_prediction" and context is not None:
            context["orchestration_phase"] = "done"
        return handler(request)
