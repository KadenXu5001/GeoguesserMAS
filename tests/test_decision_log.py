from pathlib import Path

from geoguesser.decision_log import record_decision, snapshot_decision_log
from geoguesser.runtime_budget import RuntimeBudget
from geoguesser.runtime_state import merge_decision_logs


def test_decision_log_is_sequenced_and_redacts_sensitive_values() -> None:
    context = {
        "geo_budget": RuntimeBudget(opus_cost_usd=1.0),
        "orchestration_phase": "specialist",
        "decision_log": [],
    }

    first = record_decision(
        context,
        "model_tool_proposal",
        "Supervisor proposed a tool.",
        path=Path("secret.jpg"),
        payload="data:image/jpeg;base64,AAAA",
        evidence=["double yellow center line"],
    )
    second = record_decision(
        context,
        "runtime_route",
        "Runtime selected the next tool.",
        required_tool="task",
    )

    assert first["sequence"] == 1
    assert second["sequence"] == 2
    assert "path" not in first
    assert first["payload"] == "<image redacted>"
    assert snapshot_decision_log(context)[0]["evidence"] == ["double yellow center line"]


def test_decision_log_merge_deduplicates_full_snapshots() -> None:
    first = {"sequence": 1, "event": "run_started"}
    second = {"sequence": 2, "event": "prediction_finalized"}

    assert merge_decision_logs([first], [first, second]) == [first, second]
