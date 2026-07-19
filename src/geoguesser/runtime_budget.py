from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock
from time import monotonic
from typing import Any


class BudgetExceeded(RuntimeError):
    """Raised when a hard MAS call or cost limit would be exceeded."""


class CapacityExceeded(BudgetExceeded):
    """Raised when the global runtime or dollar capacity is exhausted."""


@dataclass
class RuntimeBudget:
    opus_cost_usd: float
    # Extraction adds one bounded perception call before the three meaningful decision calls:
    # choose delegation, decide whether to re-examine, then finalize.
    max_orchestrator_turns: int = 4
    # The MAS requires at least one specialist and has two configured specialists total.
    max_specialist_tasks: int = 2
    max_reexaminations: int = 1
    cutoff_fraction: float = 0.90
    max_runtime_seconds: float = 180.0
    max_program_cost_usd: float = 0.50
    orchestrator_turns: int = 0
    specialist_tasks: int = 0
    reexaminations: int = 0
    spent_usd: float = 0.0
    usage_events: list[dict[str, Any]] | None = None
    specialists_used: set[str] = field(default_factory=set)
    # Opaque runtime-only synchronization; it must not become part of the agent schema.
    _specialist_lock: Any = field(default_factory=Lock, repr=False)
    started_at: float = field(default_factory=monotonic)
    capacity_warning: str | None = None

    @property
    def cutoff_usd(self) -> float:
        return self.opus_cost_usd * self.cutoff_fraction

    def record_cost(self, amount_usd: float) -> None:
        if amount_usd < 0:
            raise ValueError("cost cannot be negative")
        if self.spent_usd + amount_usd > self.cutoff_usd:
            raise BudgetExceeded("90%-of-Opus cost cutoff reached")
        self.spent_usd += amount_usd
        self.check_capacity()

    def check_capacity(self) -> None:
        if self.capacity_warning:
            raise CapacityExceeded(self.capacity_warning)
        if monotonic() - self.started_at >= self.max_runtime_seconds:
            self.capacity_warning = "maximum MAS runtime capacity reached (3 minutes)"
        elif self.spent_usd > self.max_program_cost_usd:
            self.capacity_warning = "maximum MAS cost capacity reached ($0.50)"
        if self.capacity_warning:
            raise CapacityExceeded(self.capacity_warning)

    def record_usage(
        self,
        *,
        component: str,
        model: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        image_tokens: int = 0,
        latency_ms: int | None = None,
    ) -> float:
        if min(input_tokens, output_tokens, image_tokens) < 0:
            raise ValueError("usage token counts cannot be negative")
        cost = (input_tokens * 0.50 + output_tokens * 3.00) / 1_000_000
        self.record_cost(cost)
        if self.usage_events is None:
            self.usage_events = []
        event: dict[str, Any] = {
            "component": component,
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "image_tokens": image_tokens,
            "cost_usd": cost,
        }
        if latency_ms is not None:
            event["latency_ms"] = latency_ms
        self.usage_events.append(event)
        return cost

    def consume_orchestrator_turn(self) -> None:
        if self.orchestrator_turns >= self.max_orchestrator_turns:
            raise BudgetExceeded("orchestrator turn limit reached")
        self.orchestrator_turns += 1

    def consume_specialist_task(self, specialist: str | None = None) -> bool:
        with self._specialist_lock:
            if specialist is not None and specialist in self.specialists_used:
                raise BudgetExceeded(f"specialist {specialist!r} may only be called once per run")
            if self.specialist_tasks >= self.max_specialist_tasks:
                raise BudgetExceeded("specialist delegation limit reached")
            self.specialist_tasks += 1
            if specialist is not None:
                self.specialists_used.add(specialist)
            return True

    def consume_reexamination(self) -> None:
        if self.reexaminations >= self.max_reexaminations:
            raise BudgetExceeded("re-examination limit reached")
        self.reexaminations += 1
