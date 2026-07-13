from types import SimpleNamespace

import pytest

from geoguesser.budget_middleware import BudgetMiddleware
from geoguesser.runtime_budget import BudgetExceeded, RuntimeBudget


def runtime(budget: RuntimeBudget) -> SimpleNamespace:
    return SimpleNamespace(context={"geo_budget": budget})


def tool_request(name: str, budget: RuntimeBudget) -> SimpleNamespace:
    return SimpleNamespace(tool_call={"name": name}, runtime=runtime(budget))


def test_model_and_tool_caps_use_per_run_context() -> None:
    budget = RuntimeBudget(opus_cost_usd=1.0)
    middleware = BudgetMiddleware()
    request = SimpleNamespace(runtime=runtime(budget))
    middleware.wrap_model_call(request, lambda value: "model-ok")
    middleware.wrap_tool_call(tool_request("task", budget), lambda value: "task-ok")
    middleware.wrap_tool_call(tool_request("reexamine_region", budget), lambda value: "crop-ok")

    assert budget.orchestrator_turns == 1
    assert budget.specialist_tasks == 1
    assert budget.reexaminations == 1


def test_second_task_is_rejected_by_middleware() -> None:
    budget = RuntimeBudget(opus_cost_usd=1.0)
    middleware = BudgetMiddleware()
    request = tool_request("task", budget)
    middleware.wrap_tool_call(request, lambda value: "ok")
    with pytest.raises(BudgetExceeded):
        middleware.wrap_tool_call(request, lambda value: "unreachable")

