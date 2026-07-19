from types import SimpleNamespace

from langchain_core.messages import AIMessage

from geoguesser.budget_middleware import (
    BudgetMiddleware,
    MAS_INITIAL_TODOS,
    MAS_TODO_CONTENTS,
)
from geoguesser.runtime_budget import RuntimeBudget


def runtime(budget: RuntimeBudget) -> SimpleNamespace:
    return SimpleNamespace(context={"geo_budget": budget})


def tool_request(name: str, budget: RuntimeBudget, specialist: str | None = None) -> SimpleNamespace:
    args = {"subagent_type": specialist} if specialist else {}
    request = SimpleNamespace(
        tool_call={"id": f"{name}-call", "name": name, "args": args},
        runtime=runtime(budget),
    )
    request.override = lambda **kwargs: SimpleNamespace(**{**vars(request), **kwargs})
    return request


SPECIALIST_JSON = '{"candidates":["France"],"evidence":["road"],"contradictions":[],"confidence":80}'


def test_model_and_tool_caps_use_per_run_context(tmp_path) -> None:
    budget = RuntimeBudget(opus_cost_usd=1.0)
    middleware = BudgetMiddleware()
    request = SimpleNamespace(runtime=runtime(budget))
    middleware.wrap_model_call(request, lambda value: "model-ok")
    middleware.wrap_tool_call(
        tool_request("task", budget, "human-clue-specialist"), lambda value: SPECIALIST_JSON
    )
    middleware.wrap_tool_call(tool_request("reexamine_region", budget), lambda value: "crop-ok")

    assert budget.orchestrator_turns == 1
    assert budget.specialist_tasks == 1
    assert budget.reexaminations == 1


def test_third_task_returns_feedback_from_middleware(tmp_path) -> None:
    budget = RuntimeBudget(opus_cost_usd=1.0)
    middleware = BudgetMiddleware()
    middleware.wrap_tool_call(
        tool_request("task", budget, "human-clue-specialist"), lambda value: SPECIALIST_JSON
    )
    middleware.wrap_tool_call(
        tool_request("task", budget, "environmental-specialist"), lambda value: SPECIALIST_JSON
    )
    result = middleware.wrap_tool_call(
        tool_request("task", budget, "third-specialist"), lambda value: "unreachable"
    )
    assert "specialist delegation limit reached" in result.content


def test_duplicate_specialist_task_returns_feedback_without_calling_handler() -> None:
    budget = RuntimeBudget(opus_cost_usd=1.0)
    middleware = BudgetMiddleware()
    middleware.wrap_tool_call(
        tool_request("task", budget, "rural-specialist"), lambda value: SPECIALIST_JSON
    )
    called = []
    result = middleware.wrap_tool_call(
        tool_request("task", budget, "rural-specialist"),
        lambda value: called.append(value) or "unreachable",
    )

    assert "may only be called once" in result.content
    assert called == []


def test_task_receives_verbatim_authorized_extraction_objects() -> None:
    budget = RuntimeBudget(opus_cost_usd=1.0)
    middleware = BudgetMiddleware()
    request = tool_request("task", budget, "rural-specialist")
    request.runtime.context.update({
        "scan_objects": {"road_markings": {"solid white outer shoulder lines and double yellow center line"}},
    })
    captured = {}

    def handler(value):
        captured["request"] = value
        return SPECIALIST_JSON

    middleware.wrap_tool_call(request, handler)

    description = captured["request"].tool_call["args"]["description"]
    assert "solid white outer shoulder lines and double yellow center line" in description


def test_model_request_receives_output_token_cap_and_usage_is_recorded() -> None:
    from types import SimpleNamespace

    budget = RuntimeBudget(opus_cost_usd=1.0)
    middleware = BudgetMiddleware(max_output_tokens=400)
    request = SimpleNamespace(
        runtime=runtime(budget),
        model_settings={"max_tokens": 900},
        model=SimpleNamespace(model="test-model"),
        override=lambda **kwargs: SimpleNamespace(**{**vars(request), **kwargs}),
    )
    response = SimpleNamespace(result=SimpleNamespace(usage_metadata={"input_tokens": 100, "output_tokens": 20}))
    captured = {}

    def handler(value):
        captured["request"] = value
        return response

    middleware.wrap_model_call(request, handler)
    assert captured["request"].model_settings["max_tokens"] == 400
    assert budget.usage_events[0]["output_tokens"] == 20


def test_gemini_request_uses_google_output_token_setting() -> None:
    budget = RuntimeBudget(opus_cost_usd=1.0)
    middleware = BudgetMiddleware(max_output_tokens=400)
    request = SimpleNamespace(
        runtime=runtime(budget),
        model_settings={"max_tokens": 900},
        model=SimpleNamespace(model="google_genai:gemini-3-flash-preview"),
        override=lambda **kwargs: SimpleNamespace(**{**vars(request), **kwargs}),
    )
    captured = {}

    def handler(value):
        captured["request"] = value
        return SimpleNamespace(result=SimpleNamespace(usage_metadata={}))

    middleware.wrap_model_call(request, handler)
    assert captured["request"].model_settings == {
        "max_output_tokens": 400,
        "max_retries": 1,
        "timeout": 30.0,
        "thinking_budget": 0,
    }


def test_active_orchestrator_requires_a_tool_call() -> None:
    budget = RuntimeBudget(opus_cost_usd=1.0)
    middleware = BudgetMiddleware()
    request = SimpleNamespace(
        runtime=runtime(budget),
        model_settings={},
        model=SimpleNamespace(model="google_genai:gemini-3-flash-preview"),
        override=lambda **kwargs: SimpleNamespace(**{**vars(request), **kwargs}),
    )
    captured = {}

    def handler(value):
        captured["request"] = value
        return SimpleNamespace(result=SimpleNamespace(usage_metadata={}))

    middleware.wrap_model_call(request, handler)
    assert captured["request"].tool_choice == "any"


def test_initial_todo_phase_binds_exact_todo_tool() -> None:
    budget = RuntimeBudget(opus_cost_usd=1.0)
    middleware = BudgetMiddleware()
    request = SimpleNamespace(
        runtime=SimpleNamespace(
            context={"orchestration_phase": "todo", "geo_budget": budget}
        ),
        messages=[SimpleNamespace(tool_calls=[])],
        model_settings={},
        model=SimpleNamespace(model="google_genai:gemini-3-flash-preview"),
        override=lambda **kwargs: SimpleNamespace(**{**vars(request), **kwargs}),
    )
    captured = {}

    def handler(value):
        captured["request"] = value
        return SimpleNamespace(result=SimpleNamespace(usage_metadata={}))

    middleware.wrap_model_call(request, handler)

    assert captured["request"].tool_choice == "write_todos"


def test_terminal_phase_stops_before_another_model_call() -> None:
    middleware = BudgetMiddleware()
    runtime_context = SimpleNamespace(
        context={
            "orchestration_phase": "failed",
            "geo_budget": RuntimeBudget(opus_cost_usd=1.0),
        }
    )

    assert middleware.before_model({}, runtime_context) == {"jump_to": "end"}


def test_parallel_initial_todos_are_serialized_before_tool_execution() -> None:
    middleware = BudgetMiddleware()
    runtime_context = SimpleNamespace(
        context={
            "orchestration_phase": "todo",
            "geo_budget": RuntimeBudget(opus_cost_usd=1.0),
        }
    )
    message = AIMessage(
        content="",
        id="model-1",
        tool_calls=[
            {"id": "todo-1", "name": "write_todos", "args": {}},
            {"id": "todo-2", "name": "write_todos", "args": {}},
        ],
    )

    result = middleware.after_model({"messages": [message]}, runtime_context)

    assert len(result["messages"][0].tool_calls) == 1
    assert result["messages"][0].tool_calls[0]["id"] == "todo-1"


def test_status_update_is_serialized_before_specialist_task() -> None:
    middleware = BudgetMiddleware()
    runtime_context = SimpleNamespace(
        context={
            "orchestration_phase": "specialist",
            "geo_budget": RuntimeBudget(opus_cost_usd=1.0),
            "todo_plan": [dict(item) for item in MAS_INITIAL_TODOS],
        }
    )
    message = AIMessage(
        content="",
        id="model-2",
        tool_calls=[
            {"id": "todo-1", "name": "write_todos", "args": {}},
            {
                "id": "task-1",
                "name": "task",
                "args": {"subagent_type": "rural-specialist"},
            },
        ],
    )

    result = middleware.after_model({"messages": [message]}, runtime_context)

    assert [call["name"] for call in result["messages"][0].tool_calls] == ["write_todos"]


def test_two_distinct_specialist_tasks_may_share_the_specialist_phase() -> None:
    middleware = BudgetMiddleware()
    budget = RuntimeBudget(opus_cost_usd=1.0)
    runtime_context = SimpleNamespace(
        context={
            "orchestration_phase": "specialist",
            "geo_budget": budget,
            "todo_plan": [
                {**MAS_INITIAL_TODOS[0], "status": "completed"},
                {**MAS_INITIAL_TODOS[1], "status": "in_progress"},
                *[dict(item) for item in MAS_INITIAL_TODOS[2:]],
            ],
        }
    )
    message = AIMessage(
        content="",
        id="model-3",
        tool_calls=[
            {"id": "task-1", "name": "task", "args": {"subagent_type": "urban-specialist"}},
            {"id": "task-2", "name": "task", "args": {"subagent_type": "rural-specialist"}},
        ],
    )

    result = middleware.after_model({"messages": [message]}, runtime_context)

    assert "messages" not in result
    assert result["decision_log"][0]["executed_tools"] == ["task", "task"]


def test_task_is_hidden_after_successful_delegation() -> None:
    budget = RuntimeBudget(opus_cost_usd=1.0)
    budget.consume_specialist_task("rural-specialist")
    middleware = BudgetMiddleware()
    request = SimpleNamespace(
        runtime=SimpleNamespace(
            context={"orchestration_phase": "specialist", "geo_budget": budget}
        ),
        messages=[],
        tools=[
            SimpleNamespace(name="task"),
            {"type": "function", "function": {"name": "write_todos"}},
            SimpleNamespace(name="reexamine_region"),
            SimpleNamespace(name="emit_prediction"),
        ],
        model_settings={},
        model=SimpleNamespace(model="google_genai:gemini-3-flash-preview"),
        override=lambda **kwargs: SimpleNamespace(**{**vars(request), **kwargs}),
    )
    captured = {}

    def handler(value):
        captured["request"] = value
        return SimpleNamespace(result=SimpleNamespace(usage_metadata={}))

    middleware.wrap_model_call(request, handler)

    visible_names = [
        tool.get("function", {}).get("name")
        if isinstance(tool, dict)
        else tool.name
        for tool in captured["request"].tools
    ]
    assert visible_names == ["write_todos", "reexamine_region", "emit_prediction"]


def test_extraction_phase_binds_exact_extraction_tool() -> None:
    budget = RuntimeBudget(opus_cost_usd=1.0)
    middleware = BudgetMiddleware()
    request = SimpleNamespace(
        runtime=SimpleNamespace(
            context={"orchestration_phase": "extraction", "geo_budget": budget}
        ),
        model_settings={},
        model=SimpleNamespace(model="google_genai:gemini-3-flash-preview"),
        override=lambda **kwargs: SimpleNamespace(**{**vars(request), **kwargs}),
    )
    captured = {}

    def handler(value):
        captured["request"] = value
        return SimpleNamespace(result=SimpleNamespace(usage_metadata={}))

    middleware.wrap_model_call(request, handler)

    assert captured["request"].tool_choice == "extract_visual_evidence"


def test_supervisor_can_update_todos_during_active_run() -> None:
    budget = RuntimeBudget(opus_cost_usd=1.0)
    middleware = BudgetMiddleware()
    request = tool_request("write_todos", budget)
    request.runtime.context["orchestration_phase"] = "specialist"
    request.runtime.context["todo_plan"] = [
        {"content": "Analyze", "status": "in_progress"},
        {"content": "Emit prediction", "status": "pending"},
    ]
    request.tool_call["args"] = {
        "todos": [
            {"content": "Analyze", "status": "completed"},
            {"content": "Emit prediction", "status": "pending"},
        ]
    }
    called = []

    result = middleware.wrap_tool_call(
        request, lambda value: called.append(value) or "todos-updated"
    )

    assert result == "todos-updated"
    assert called == [request]


def test_initial_todo_plan_advances_to_extraction_phase() -> None:
    budget = RuntimeBudget(opus_cost_usd=1.0)
    middleware = BudgetMiddleware()
    request = tool_request("write_todos", budget)
    request.runtime.context["orchestration_phase"] = "todo"
    request.tool_call["args"] = {
        "todos": [
            {"content": MAS_TODO_CONTENTS[0], "status": "in_progress"},
            {"content": MAS_TODO_CONTENTS[1], "status": "pending"},
            {"content": MAS_TODO_CONTENTS[2], "status": "pending"},
            {"content": MAS_TODO_CONTENTS[3], "status": "pending"},
        ]
    }

    middleware.wrap_tool_call(request, lambda value: "todos-created")

    assert request.runtime.context["orchestration_phase"] == "extraction"


def test_initial_todo_plan_is_replaced_with_canonical_extraction_first_plan() -> None:
    budget = RuntimeBudget(opus_cost_usd=1.0)
    middleware = BudgetMiddleware()
    request = tool_request("write_todos", budget)
    request.runtime.context["orchestration_phase"] = "todo"
    request.tool_call["args"] = {
        "todos": [
            {"content": "Analyze scene", "status": "in_progress"},
            {"content": "Emit prediction", "status": "pending"},
        ]
    }

    called = []
    result = middleware.wrap_tool_call(
        request, lambda value: called.append(value) or "created"
    )

    assert result == "created"
    assert called[0].tool_call["args"]["todos"] == MAS_INITIAL_TODOS


def test_initial_todo_plan_requires_exact_tool_order_and_wording() -> None:
    budget = RuntimeBudget(opus_cost_usd=1.0)
    middleware = BudgetMiddleware()
    request = tool_request("write_todos", budget)
    request.runtime.context["orchestration_phase"] = "todo"
    request.tool_call["args"] = {
        "todos": [
            {"content": "Extract visual evidence with extract_visual_evidence", "status": "in_progress"},
            {"content": "Delegate to urban-specialist or rural-specialist with task", "status": "pending"},
            {"content": "Optionally reexamine_region only for two close country signals", "status": "pending"},
            {"content": "Emit final country prediction with emit_prediction", "status": "pending"},
        ]
    }

    assert middleware.wrap_tool_call(request, lambda value: "accepted") == "accepted"


def test_invalid_initial_todo_plan_is_canonicalized_without_retry() -> None:
    budget = RuntimeBudget(opus_cost_usd=1.0)
    middleware = BudgetMiddleware()
    request = tool_request("write_todos", budget)
    request.runtime.context["orchestration_phase"] = "todo"
    request.tool_call["args"] = {
        "todos": [
            {"content": MAS_TODO_CONTENTS[0], "status": "in_progress"},
            {"content": MAS_TODO_CONTENTS[1], "status": "pending"},
            {"content": MAS_TODO_CONTENTS[2], "status": "pending"},
            {"content": MAS_TODO_CONTENTS[3], "status": "completed"},
        ]
    }
    called = []

    result = middleware.wrap_tool_call(
        request, lambda value: called.append(value) or "created"
    )

    assert result == "created"
    assert called[0].tool_call["args"]["todos"] == MAS_INITIAL_TODOS
    assert request.runtime.context["todo_plan"] == MAS_INITIAL_TODOS
    assert request.runtime.context["orchestration_phase"] == "extraction"


def test_todo_updates_are_forward_only_and_keep_final_step_pending() -> None:
    budget = RuntimeBudget(opus_cost_usd=1.0)
    middleware = BudgetMiddleware()
    request = tool_request("write_todos", budget)
    request.runtime.context["orchestration_phase"] = "todo"
    request.tool_call["args"] = {
        "todos": [
            {"content": MAS_TODO_CONTENTS[0], "status": "in_progress"},
            {"content": MAS_TODO_CONTENTS[1], "status": "pending"},
            {"content": MAS_TODO_CONTENTS[2], "status": "pending"},
            {"content": MAS_TODO_CONTENTS[3], "status": "pending"},
        ]
    }
    middleware.wrap_tool_call(request, lambda value: "created")
    request.runtime.context["orchestration_phase"] = "specialist"
    request.tool_call["args"]["todos"][0]["status"] = "completed"
    request.tool_call["args"]["todos"][1]["status"] = "in_progress"

    assert middleware.wrap_tool_call(request, lambda value: "updated") == "updated"


def test_plain_supervisor_response_is_continued_instead_of_terminating() -> None:
    middleware = BudgetMiddleware()
    runtime_context = SimpleNamespace(
        context={
            "orchestration_phase": "specialist",
            "geo_budget": RuntimeBudget(opus_cost_usd=1.0),
        }
    )
    result = middleware.after_model(
        {"messages": [SimpleNamespace(tool_calls=[])]}, runtime_context
    )

    assert result["jump_to"] == "model"
    assert "task to delegate" in result["messages"][0].content


def test_todo_continuation_does_not_consume_decision_turn() -> None:
    budget = RuntimeBudget(opus_cost_usd=1.0)
    middleware = BudgetMiddleware()
    request = SimpleNamespace(
        runtime=runtime(budget),
        messages=[
            SimpleNamespace(tool_calls=[{"id": "todo-1", "name": "write_todos"}]),
            SimpleNamespace(tool_call_id="todo-1"),
        ],
        model_settings={},
        model=SimpleNamespace(model="gemini-3-flash-preview"),
        override=lambda **kwargs: SimpleNamespace(**{**vars(request), **kwargs}),
    )
    middleware.wrap_model_call(
        request,
        lambda value: SimpleNamespace(result=SimpleNamespace(usage_metadata={})),
    )
    assert budget.orchestrator_turns == 0


def test_extraction_continuation_consumes_orchestrator_turn() -> None:
    budget = RuntimeBudget(opus_cost_usd=1.0)
    middleware = BudgetMiddleware()
    request = SimpleNamespace(
        runtime=SimpleNamespace(
            context={"orchestration_phase": "extraction", "geo_budget": budget}
        ),
        messages=[
            SimpleNamespace(tool_calls=[{"id": "todo-1", "name": "write_todos"}]),
            SimpleNamespace(tool_call_id="todo-1"),
        ],
        model_settings={},
        model=SimpleNamespace(model="gemini-3-flash-preview"),
        override=lambda **kwargs: SimpleNamespace(**{**vars(request), **kwargs}),
    )

    middleware.wrap_model_call(
        request,
        lambda value: SimpleNamespace(result=SimpleNamespace(usage_metadata={})),
    )

    assert budget.orchestrator_turns == 1


def test_initial_todo_model_call_does_not_consume_decision_turn() -> None:
    budget = RuntimeBudget(opus_cost_usd=1.0)
    middleware = BudgetMiddleware()
    request = SimpleNamespace(
        runtime=SimpleNamespace(
            context={"orchestration_phase": "todo", "geo_budget": budget}
        ),
        messages=[SimpleNamespace(tool_calls=[])],
        model_settings={},
        model=SimpleNamespace(model="gemini-3-flash-preview"),
        override=lambda **kwargs: SimpleNamespace(**{**vars(request), **kwargs}),
    )

    middleware.wrap_model_call(
        request,
        lambda value: SimpleNamespace(result=SimpleNamespace(usage_metadata={})),
    )

    assert budget.orchestrator_turns == 0
