from types import SimpleNamespace

import pytest

from geoguesser.budget_middleware import BudgetMiddleware
from geoguesser.runtime_budget import BudgetExceeded, RuntimeBudget


def runtime(budget: RuntimeBudget) -> SimpleNamespace:
    return SimpleNamespace(context={"geo_budget": budget})


def tool_request(name: str, budget: RuntimeBudget, specialist: str | None = None) -> SimpleNamespace:
    args = {"subagent_type": specialist} if specialist else {}
    return SimpleNamespace(tool_call={"name": name, "args": args}, runtime=runtime(budget))


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
    assert "cap reached" in result.content


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
    assert captured["request"].model_settings == {"max_output_tokens": 400}


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
