from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from langsmith import traceable


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from geoguesser.baselines import GEMINI_PRO_MODEL, run_gemini_pro_baseline  # noqa: E402
from geoguesser.gemini_client import create_gemini_client  # noqa: E402


def _path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


@traceable(name="gemini-pro-baseline", run_type="chain")
def run_traced(client: Any, row: dict[str, str]) -> dict[str, Any]:
    views = {
        0: _path(row["view_h000_path"]),
        90: _path(row["view_h090_path"]),
        180: _path(row["view_h180_path"]),
        270: _path(row["view_h270_path"]),
    }
    result = run_gemini_pro_baseline(client, views)
    return {
        "dataset_version": row.get("dataset_version"),
        "split": row.get("split"),
        "image_id": row.get("mapillary_image_id"),
        "ground_truth": row.get("country"),
        "model": GEMINI_PRO_MODEL,
        "prediction": result.prediction.model_dump(),
        "usage": result.usage,
        "view_paths": {str(heading): str(path.relative_to(ROOT)) for heading, path in views.items()},
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the direct Gemini Pro GeoGuessr baseline")
    parser.add_argument("--dataset", type=Path, default=ROOT / "data/datasets/dev_v1.csv")
    parser.add_argument("--limit", type=int, default=1, help="number of rows to run; 0 means all")
    parser.add_argument("--output", type=Path, default=ROOT / ".artifacts/gemini-pro-results.jsonl")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    load_dotenv(ROOT / ".env")
    dataset = _path(str(args.dataset))
    rows = list(csv.DictReader(dataset.open(newline="", encoding="utf-8")))
    if args.limit > 0:
        rows = rows[: args.limit]
    if not rows:
        raise SystemExit("dataset contains no rows")

    client = create_gemini_client()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as handle:
        for index, row in enumerate(rows, start=1):
            try:
                result = run_traced(client, row)
                result["status"] = "ok"
            except Exception as exc:  # keep later rows runnable after one failure
                result = {
                    "status": "error",
                    "image_id": row.get("mapillary_image_id"),
                    "error": f"{type(exc).__name__}: {exc}",
                }
            handle.write(json.dumps(result, ensure_ascii=False) + "\n")
            print(json.dumps({"index": index, **result}, ensure_ascii=False))
    print(f"wrote {len(rows)} results to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
