from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
import json
from pathlib import Path
from typing import Any, Iterable, Mapping


@dataclass(frozen=True)
class TuningConfig:
    """All behavior choices that must be frozen before evaluation."""

    config_id: str
    extraction_prompt_version: str
    orchestrator_prompt_version: str
    specialist_policy_version: str
    reexamination_policy_version: str
    model_version: str
    reference_version: str
    budget_policy_version: str


@dataclass(frozen=True)
class DevelopmentExperiment:
    config: TuningConfig
    dataset_version: str
    split: str
    accuracy: float
    centroid_loss_km: float
    complete_cost_usd: float
    image_tokens: int
    latency_ms: float
    call_count: int
    specialist_rate: float
    reexamination_rate: float
    created_at: str = date.today().isoformat()

    def as_record(self) -> dict[str, Any]:
        return {"config": asdict(self.config), **asdict(self)}


def validate_tuning_record(record: Mapping[str, Any]) -> None:
    if record.get("split") != "development":
        raise ValueError("tuning records may only use the development split")
    if record.get("dataset_version") != "dev_v1":
        raise ValueError("tuning records must use dev_v1")
    config = record.get("config")
    if not isinstance(config, Mapping) or not config.get("config_id"):
        raise ValueError("tuning record must include a versioned config")


def append_experiment(path: Path, experiment: DevelopmentExperiment) -> None:
    record = experiment.as_record()
    validate_tuning_record(record)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def select_best_development_config(
    experiments: Iterable[DevelopmentExperiment],
    *,
    max_cost_usd: float | None = None,
) -> DevelopmentExperiment:
    candidates = [item for item in experiments if item.split == "development" and item.dataset_version == "dev_v1"]
    if max_cost_usd is not None:
        candidates = [item for item in candidates if item.complete_cost_usd <= max_cost_usd]
    if not candidates:
        raise ValueError("no eligible development experiment")
    return min(
        candidates,
        key=lambda item: (-item.accuracy, item.centroid_loss_km, item.complete_cost_usd),
    )

