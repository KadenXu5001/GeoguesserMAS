import pytest

from geoguesser.comparison import comparison_summary, countries_match


def test_country_matching_normalizes_common_names() -> None:
    assert countries_match("USA", "United States")
    assert countries_match("united-kingdom", "United Kingdom")
    assert not countries_match("France", "Belgium")


def test_comparison_summary_counts_failures_as_incorrect_and_reports_tokens() -> None:
    rows = [
        {
            "ground_truth": "France",
            "claude": {
                "status": "ok",
                "prediction": {"country": "France"},
                "usage": [
                    {
                        "input_tokens": 100,
                        "output_tokens": 10,
                        "reasoning_tokens": 5,
                        "cost_usd": 0.01,
                    }
                ],
            },
            "mas": {
                "status": "ok",
                "prediction": {"country": "Belgium"},
                "usage": [{"input_tokens": 50, "output_tokens": 5, "cost_usd": 0.002}],
            },
        },
        {
            "ground_truth": "Brazil",
            "claude": {"status": "error", "error": "nope"},
            "mas": {
                "status": "ok",
                "prediction": {"country": "Brazil"},
                "usage": [{"input_tokens": 60, "output_tokens": 6, "cost_usd": 0.003}],
            },
        },
    ]

    summary = comparison_summary(rows)

    assert summary["claude_opus"]["accuracy"] == 0.5
    assert summary["claude_opus"]["success_rate"] == 0.5
    assert summary["claude_opus"]["input_tokens"] == 100
    assert summary["claude_opus"]["reasoning_tokens"] == 5
    assert summary["claude_opus"]["total_tokens"] == 115
    assert summary["mas"]["accuracy"] == 0.5
    assert summary["mas"]["cost_usd"] == pytest.approx(0.005)
    assert summary["paired"]["count"] == 1
    assert summary["paired"]["mas_accuracy_delta_points"] == -100.0
    assert summary["cost_comparison"]["mas_vs_claude_ratio"] == pytest.approx(0.5)
