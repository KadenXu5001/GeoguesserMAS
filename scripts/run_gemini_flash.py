from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
# This is a direct baseline, not a production MAS run. Keep evaluation data local
# except for the four images and prompt sent to the configured Gemini API.
os.environ["LANGSMITH_TRACING"] = "false"
os.environ["LANGCHAIN_TRACING_V2"] = "false"
os.environ["LANGCHAIN_CALLBACKS_BACKGROUND"] = "false"
sys.path.insert(0, str(ROOT / "src"))

from geoguesser.baselines import GEMINI_FLASH_MODEL, run_gemini_baseline  # noqa: E402
from geoguesser.comparison import summarize_system  # noqa: E402
from geoguesser.cost_model import GEMINI_FLASH, token_cost  # noqa: E402
from geoguesser.gemini_client import create_gemini_client  # noqa: E402
from geoguesser.mas_assets import resolve_mas_view_paths  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the direct Gemini 3 Flash country-prediction baseline"
    )
    parser.add_argument("--dataset", type=Path, default=ROOT / "data/datasets/eval_c1.csv")
    parser.add_argument("--limit", type=int, default=0, help="rows to run; 0 means all")
    parser.add_argument(
        "--output", type=Path, default=ROOT / ".artifacts/gemini-3-flash-eval.jsonl"
    )
    parser.add_argument(
        "--summary",
        type=Path,
        default=ROOT / ".artifacts/gemini-3-flash-eval-summary.json",
    )
    return parser


def _error(row: dict[str, str], exc: Exception) -> dict[str, Any]:
    return {
        "status": "error",
        "dataset_version": row.get("dataset_version"),
        "split": row.get("split"),
        "image_id": row.get("mapillary_image_id"),
        "ground_truth": row.get("country"),
        "error": f"{type(exc).__name__}: {exc}",
    }


def main() -> int:
    args = build_parser().parse_args()
    dataset = args.dataset if args.dataset.is_absolute() else ROOT / args.dataset
    output = args.output if args.output.is_absolute() else ROOT / args.output
    summary_path = args.summary if args.summary.is_absolute() else ROOT / args.summary
    rows = list(csv.DictReader(dataset.open(newline="", encoding="utf-8")))
    if args.limit > 0:
        rows = rows[: args.limit]
    if not rows:
        raise SystemExit("dataset contains no rows")

    client = create_gemini_client()
    output.parent.mkdir(parents=True, exist_ok=True)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []
    with output.open("w", encoding="utf-8") as handle:
        for index, row in enumerate(rows, start=1):
            image_id = row.get("mapillary_image_id")
            print(f"[Gemini Flash {index}/{len(rows)}] {image_id}", flush=True)
            try:
                views = resolve_mas_view_paths(row, root=ROOT)
                baseline = run_gemini_baseline(
                    client,
                    views,
                    model=GEMINI_FLASH_MODEL,
                    max_attempts=1,
                )
                usage = {
                    **baseline.usage,
                    "cost_usd": token_cost(
                        GEMINI_FLASH,
                        baseline.usage["input_tokens"],
                        baseline.usage["output_tokens"]
                        + baseline.usage["reasoning_tokens"],
                    ),
                }
                record = {
                    "status": "ok",
                    "dataset_version": row.get("dataset_version"),
                    "split": row.get("split"),
                    "image_id": image_id,
                    "ground_truth": row.get("country"),
                    "model": GEMINI_FLASH_MODEL,
                    "prediction": baseline.prediction.model_dump(),
                    "usage": [usage],
                }
                print(
                    f"  predicted={baseline.prediction.country} "
                    f"confidence={baseline.prediction.confidence}",
                    flush=True,
                )
            except Exception as exc:
                record = _error(row, exc)
                print(f"  ERROR {record['error']}", flush=True)
            records.append(record)
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            handle.flush()

    summary = {
        "dataset": str(dataset),
        "model": GEMINI_FLASH_MODEL,
        **summarize_system(records),
    }
    summary_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"raw results: {output}")
    print(f"summary: {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
