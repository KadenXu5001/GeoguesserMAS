import json
from pathlib import Path

from scripts.summarize_results import _evaluation_rows


def test_result_loader_flattens_structured_country_prediction(tmp_path: Path) -> None:
    path = tmp_path / "results.jsonl"
    path.write_text(
        json.dumps(
            {
                "status": "ok",
                "prediction": {"country": "France", "confidence": 80},
                "ground_truth": "France",
                "usage": {"cost_usd": 0.01},
            }
        )
        + "\n"
        + json.dumps({"status": "error", "error": "failed"})
        + "\n",
        encoding="utf-8",
    )
    rows = _evaluation_rows(path)
    assert rows == [
        {
            "status": "ok",
            "prediction": "France",
            "ground_truth": "France",
            "usage": [{"cost_usd": 0.01}],
        }
    ]
