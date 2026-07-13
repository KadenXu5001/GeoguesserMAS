import pytest

from geoguesser.runtime_budget import BudgetExceeded, RuntimeBudget


def test_enforces_call_caps() -> None:
    budget = RuntimeBudget(opus_cost_usd=1.0)
    budget.consume_orchestrator_turn()
    budget.consume_orchestrator_turn()
    budget.consume_specialist_task()
    budget.consume_reexamination()

    with pytest.raises(BudgetExceeded):
        budget.consume_orchestrator_turn()
    with pytest.raises(BudgetExceeded):
        budget.consume_specialist_task()
    with pytest.raises(BudgetExceeded):
        budget.consume_reexamination()


def test_enforces_ninety_percent_cost_cutoff() -> None:
    budget = RuntimeBudget(opus_cost_usd=1.0)
    budget.record_cost(0.89)
    with pytest.raises(BudgetExceeded, match="90%"):
        budget.record_cost(0.02)

