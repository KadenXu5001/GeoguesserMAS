from pathlib import Path
import json

import pytest

from geoguesser.tuning import (
    DevelopmentExperiment,
    TuningConfig,
    append_experiment,
    select_best_development_config,
    validate_tuning_record,
)


def config(config_id: str) -> TuningConfig:
    return TuningConfig(config_id, "extract-1", "orch-1", "specialist-1", "reexam-1", "flash-1", "reference-v1", "budget-1")


def experiment(config_id: str, accuracy: float, cost: float) -> DevelopmentExperiment:
    return DevelopmentExperiment(config(config_id), "dev_v1", "development", accuracy, 100, cost, 10, 20, 2, 0.5, 0.1)


def test_selects_highest_accuracy_under_cost_constraint() -> None:
    result = select_best_development_config(
        [experiment("cheap", 0.70, 0.01), experiment("accurate", 0.80, 0.02), experiment("too-expensive", 0.99, 0.10)],
        max_cost_usd=0.03,
    )
    assert result.config.config_id == "accurate"


def test_rejects_eval_records_for_tuning() -> None:
    record = experiment("eval", 0.8, 0.01).as_record()
    record["split"] = "evaluation"
    with pytest.raises(ValueError, match="development"):
        validate_tuning_record(record)


def test_appends_versioned_jsonl_record(tmp_path: Path) -> None:
    output = tmp_path / "experiments.jsonl"
    append_experiment(output, experiment("v1", 0.7, 0.01))
    record = json.loads(output.read_text(encoding="utf-8"))
    assert record["config"]["config_id"] == "v1"
