import pytest

from geoguesser.evaluation import centroid_haversine_loss, country_accuracy, summarize_runs


def rows() -> list[dict]:
    return [
        {
            "prediction": "France",
            "ground_truth": "France",
            "location": (48.8, 2.3),
            "usage": [{"cost_usd": 0.01, "image_tokens": 100, "latency_ms": 100}],
            "specialist_used": "human-clue-specialist",
            "reexamine_results": [],
        },
        {
            "prediction": "Thailand",
            "ground_truth": "Brazil",
            "location": (13.7, 100.5),
            "usage": [{"cost_usd": 0.02, "image_tokens": 200, "latency_ms": 300}],
            "specialist_used": None,
            "reexamine_results": [{"answer": "visible"}],
        },
    ]


def test_accuracy_and_centroid_loss() -> None:
    assert country_accuracy(rows()) == 0.5
    loss = centroid_haversine_loss(rows(), {"France": (46.2, 2.2), "Thailand": (15.8, 100.9)})
    assert loss > 0


def test_summarizes_complete_cost_and_operational_metrics() -> None:
    summary = summarize_runs(rows())
    assert summary["complete_cost_usd"] == pytest.approx(0.03)
    assert summary["image_tokens"] == 300
    assert summary["call_count"] == 2
    assert summary["specialist_rate"] == 0.5
    assert summary["reexamination_rate"] == 0.5
