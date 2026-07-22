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
# Production MAS traces use the explicit redacting tracer and synchronous flush.
os.environ["LANGSMITH_TRACING"] = "false"
os.environ["LANGCHAIN_TRACING_V2"] = "false"
os.environ["LANGCHAIN_CALLBACKS_BACKGROUND"] = "false"
sys.path.insert(0, str(ROOT / "src"))

from geoguesser.agent_factory import create_geoguesser_agent  # noqa: E402
from geoguesser.anthropic_client import create_anthropic_client  # noqa: E402
from geoguesser.baselines import (  # noqa: E402
    CLAUDE_OPUS_MODEL,
    run_claude_opus_baseline,
)
from geoguesser.comparison import comparison_summary  # noqa: E402
from geoguesser.cost_model import CLAUDE_OPUS, Pricing  # noqa: E402
from geoguesser.gemini_client import create_gemini_client  # noqa: E402
from geoguesser.langsmith_tracing import (  # noqa: E402
    create_langsmith_tracer,
    flush_langsmith_traces,
)
from geoguesser.mas_runner import run_mas_row  # noqa: E402
from geoguesser.reference_data import load_reference_snapshot, lookup_references  # noqa: E402


class SnapshotRepository:
    """Read-only adapter over the versioned local reference snapshot."""

    def __init__(self, snapshot: dict[str, Any]) -> None:
        self.snapshot = snapshot

    def lookup_references(
        self, *, version: str, category: str, country: str | None = None
    ) -> list[dict[str, Any]]:
        if version != self.snapshot["version"]:
            raise ValueError(f"reference version {version} is unavailable")
        return lookup_references(self.snapshot, category=category, country=country)


def _path(value: Path) -> Path:
    return value if value.is_absolute() else ROOT / value


def _views(row: dict[str, str]) -> dict[int, Path]:
    return {
        heading: _path(Path(row[f"view_h{heading:03d}_path"]))
        for heading in (0, 90, 180, 270)
    }


def _error(exc: Exception) -> dict[str, Any]:
    return {"status": "error", "error": f"{type(exc).__name__}: {exc}"}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compare direct Claude Opus with the production GeoGuessr MAS"
    )
    parser.add_argument("--dataset", type=Path, default=Path("data/datasets/dev_v1.csv"))
    parser.add_argument("--limit", type=int, default=1, help="rows to run; 0 means all")
    parser.add_argument(
        "--output", type=Path, default=Path(".artifacts/claude-opus-vs-mas.jsonl")
    )
    parser.add_argument(
        "--summary", type=Path, default=Path(".artifacts/claude-opus-vs-mas-summary.json")
    )
    parser.add_argument(
        "--snapshot", type=Path, default=Path("data/reference_tables/reference_v2.json")
    )
    parser.add_argument(
        "--opus-model", default=os.environ.get("OPUS_MODEL", CLAUDE_OPUS_MODEL)
    )
    parser.add_argument(
        "--opus-input-price",
        type=float,
        default=CLAUDE_OPUS.input_per_million,
        help="USD per million input tokens",
    )
    parser.add_argument(
        "--opus-output-price",
        type=float,
        default=CLAUDE_OPUS.output_per_million,
        help="USD per million output tokens",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    dataset_path = _path(args.dataset)
    rows = list(csv.DictReader(dataset_path.open(newline="", encoding="utf-8")))
    if args.limit > 0:
        rows = rows[: args.limit]
    if not rows:
        raise SystemExit("dataset contains no rows")
    if args.opus_input_price < 0 or args.opus_output_price < 0:
        raise SystemExit("Opus token prices cannot be negative")

    snapshot = load_reference_snapshot(_path(args.snapshot))
    repository = SnapshotRepository(snapshot)
    anthropic_client = create_anthropic_client()
    gemini_client = create_gemini_client()
    tracer = create_langsmith_tracer()
    agent = create_geoguesser_agent()
    pricing = Pricing(args.opus_input_price, args.opus_output_price)
    output_path = _path(args.output)
    summary_path = _path(args.summary)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    completed: list[dict[str, Any]] = []

    try:
        with output_path.open("w", encoding="utf-8") as handle:
            for index, row in enumerate(rows, start=1):
                image_id = row.get("mapillary_image_id")
                print(f"[{index}/{len(rows)}] {image_id}: Claude Opus", flush=True)
                try:
                    baseline = run_claude_opus_baseline(
                        anthropic_client,
                        _views(row),
                        model=args.opus_model,
                        pricing=pricing,
                    )
                    claude_result = {
                        "status": "ok",
                        "model": args.opus_model,
                        "prediction": baseline.prediction.model_dump(),
                        "usage": [baseline.usage],
                    }
                except Exception as exc:
                    claude_result = _error(exc)

                print(f"[{index}/{len(rows)}] {image_id}: production MAS", flush=True)
                try:
                    raw_mas = run_mas_row(
                        row,
                        gemini_client=gemini_client,
                        reference_repository=repository,
                        reference_version=snapshot["version"],
                        agent=agent,
                        root=ROOT,
                        progress=lambda message, current=index: print(
                            f"[MAS {current}/{len(rows)}] {message}", flush=True
                        ),
                        trace_callbacks=[tracer],
                    )
                    if raw_mas.get("prediction") is None:
                        mas_result = {
                            "status": "capacity",
                            "warning": raw_mas.get("warning"),
                            "usage": raw_mas.get("usage", []),
                        }
                    else:
                        mas_result = {
                            "status": "ok",
                            "prediction": raw_mas["prediction"],
                            "usage": raw_mas.get("usage", []),
                            "specialists_used": raw_mas.get("specialists_used", []),
                            "reexaminations": len(raw_mas.get("reexamine_results", [])),
                        }
                except Exception as exc:
                    mas_result = _error(exc)

                record = {
                    "dataset_version": row.get("dataset_version"),
                    "split": row.get("split"),
                    "image_id": image_id,
                    "ground_truth": row.get("country"),
                    "claude": claude_result,
                    "mas": mas_result,
                }
                completed.append(record)
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
                handle.flush()
    finally:
        print("[LangSmith] flushing mandatory MAS traces", flush=True)
        flush_langsmith_traces(tracer=tracer)

    summary = {
        "dataset": str(dataset_path),
        "opus_model": args.opus_model,
        "opus_pricing_usd_per_million_tokens": {
            "input": args.opus_input_price,
            "output": args.opus_output_price,
        },
        **comparison_summary(completed),
    }
    summary_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"raw results: {output_path}")
    print(f"summary: {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
