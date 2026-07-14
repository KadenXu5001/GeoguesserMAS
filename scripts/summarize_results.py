from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from geoguesser.evaluation import country_accuracy, summarize_runs  # noqa: E402


def _evaluation_rows(path: Path) -> list[dict[str, Any]]:
    rows = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        record = json.loads(line)
        if record.get("status") != "ok":
            continue
        prediction = record.get("prediction") or {}
        usage = record.get("usage", [])
        if isinstance(usage, dict):
            usage = [usage]
        rows.append(
            {
                **record,
                "prediction": prediction.get("country") if isinstance(prediction, dict) else prediction,
                "ground_truth": record.get("ground_truth"),
                "usage": usage,
            }
        )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize GeoGuessr MAS JSONL results")
    parser.add_argument("results", type=Path)
    args = parser.parse_args()
    rows = _evaluation_rows(args.results)
    summary = summarize_runs(rows)
    summary["accuracy"] = country_accuracy(rows)
    summary["successful_rows"] = len(rows)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
