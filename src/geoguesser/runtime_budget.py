from __future__ import annotations

from dataclasses import dataclass


class BudgetExceeded(RuntimeError):
    """Raised when a hard MAS call or cost limit would be exceeded."""


@dataclass
class RuntimeBudget:
    opus_cost_usd: float
    max_orchestrator_turns: int = 2
    max_specialist_tasks: int = 1
    max_reexaminations: int = 1
    cutoff_fraction: float = 0.90
    orchestrator_turns: int = 0
    specialist_tasks: int = 0
    reexaminations: int = 0
    spent_usd: float = 0.0

    @property
    def cutoff_usd(self) -> float:
        return self.opus_cost_usd * self.cutoff_fraction

    def record_cost(self, amount_usd: float) -> None:
        if amount_usd < 0:
            raise ValueError("cost cannot be negative")
        if self.spent_usd + amount_usd > self.cutoff_usd:
            raise BudgetExceeded("90%-of-Opus cost cutoff reached")
        self.spent_usd += amount_usd

    def consume_orchestrator_turn(self) -> None:
        if self.orchestrator_turns >= self.max_orchestrator_turns:
            raise BudgetExceeded("orchestrator turn limit reached")
        self.orchestrator_turns += 1

    def consume_specialist_task(self) -> None:
        if self.specialist_tasks >= self.max_specialist_tasks:
            raise BudgetExceeded("specialist delegation limit reached")
        self.specialist_tasks += 1

    def consume_reexamination(self) -> None:
        if self.reexaminations >= self.max_reexaminations:
            raise BudgetExceeded("re-examination limit reached")
        self.reexaminations += 1

