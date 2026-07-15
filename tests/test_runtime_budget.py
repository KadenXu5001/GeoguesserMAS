import pytest

from geoguesser.runtime_budget import BudgetExceeded, RuntimeBudget


def test_enforces_call_caps() -> None:
    budget = RuntimeBudget(opus_cost_usd=1.0)
    budget.consume_orchestrator_turn()
    budget.consume_orchestrator_turn()
    budget.consume_orchestrator_turn()
    budget.consume_specialist_task()
    budget.consume_specialist_task()
    budget.consume_reexamination()

    with pytest.raises(BudgetExceeded):
        budget.consume_orchestrator_turn()
    with pytest.raises(BudgetExceeded):
        budget.consume_specialist_task()
    with pytest.raises(BudgetExceeded):
        budget.consume_reexamination()


def test_rejects_repeated_named_specialist() -> None:
    budget = RuntimeBudget(opus_cost_usd=1.0)
    budget.consume_specialist_task("rural-specialist")
    with pytest.raises(BudgetExceeded, match="only be called once"):
        budget.consume_specialist_task("rural-specialist")


def test_enforces_ninety_percent_cost_cutoff() -> None:
    budget = RuntimeBudget(opus_cost_usd=1.0)
    budget.record_cost(0.89)
    with pytest.raises(BudgetExceeded, match="90%"):
        budget.record_cost(0.02)


def test_records_usage_and_cost() -> None:
    budget = RuntimeBudget(opus_cost_usd=1.0)
    cost = budget.record_usage(
        component="orchestrator",
        model="gemini-3-flash-preview",
        input_tokens=1000,
        output_tokens=100,
        image_tokens=500,
    )

    assert cost == pytest.approx(0.0008)
    assert budget.usage_events[0]["image_tokens"] == 500
