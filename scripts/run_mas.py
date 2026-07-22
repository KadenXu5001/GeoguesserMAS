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
# Enable LangSmith while debugging the MAS. The upload is synchronous so the
# process does not exit with a live background uploader waiting on a large
# multimodal multipart request.
# Use the explicit redacting LangChainTracer below instead of the automatic tracer.
os.environ["LANGSMITH_TRACING"] = "false"
os.environ["LANGCHAIN_TRACING_V2"] = "false"
os.environ["LANGCHAIN_CALLBACKS_BACKGROUND"] = "false"
os.environ["LANGSMITH_HIDE_INPUTS"] = "false"
os.environ["LANGSMITH_HIDE_OUTPUTS"] = "false"
sys.path.insert(0, str(ROOT / "src"))

from geoguesser.mas_runner import run_mas_row  # noqa: E402
from geoguesser.agent_factory import create_geoguesser_agent  # noqa: E402
from geoguesser.reference_data import load_reference_snapshot, lookup_references  # noqa: E402
from geoguesser.gemini_client import create_gemini_client  # noqa: E402
from geoguesser.langsmith_tracing import (  # noqa: E402
    create_langsmith_tracer,
    flush_langsmith_traces,
)


class SnapshotRepository:
    """Read-only local adapter over a versioned reference snapshot."""

    def __init__(self, snapshot: dict[str, Any]) -> None:
        self.snapshot = snapshot

    def lookup_references(
        self, *, version: str, category: str, country: str | None = None
    ) -> list[dict[str, Any]]:
        if version != self.snapshot["version"]:
            raise ValueError(f"reference version {version} is unavailable")
        return lookup_references(self.snapshot, category=category, country=country)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the GeoGuessr Deep Agents MAS")
    parser.add_argument("--dataset", type=Path, default=ROOT / "data/datasets/dev_v1.csv")
    parser.add_argument("--limit", type=int, default=1, help="rows to run; 0 means all")
    parser.add_argument("--output", type=Path, default=ROOT / ".artifacts/mas-results.jsonl")
    parser.add_argument(
        "--snapshot", type=Path, default=ROOT / "data/reference_tables/reference_v2.json"
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    dataset = args.dataset if args.dataset.is_absolute() else ROOT / args.dataset
    rows = list(csv.DictReader(dataset.open(newline="", encoding="utf-8")))
    if args.limit > 0:
        rows = rows[: args.limit]
    if not rows:
        raise SystemExit("dataset contains no rows")

    snapshot_path = args.snapshot if args.snapshot.is_absolute() else ROOT / args.snapshot
    snapshot = load_reference_snapshot(snapshot_path)
    repository = SnapshotRepository(snapshot)
    gemini_client = create_gemini_client()
    langsmith_tracer = create_langsmith_tracer()
    # Compile the graph once; per-row RuntimeBudget measures inference only.
    supervisor_agent = create_geoguesser_agent()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with args.output.open("w", encoding="utf-8") as handle:
            for index, row in enumerate(rows, start=1):
                print(f"[MAS {index}/{len(rows)}] starting image {row.get('mapillary_image_id')}", flush=True)
                try:
                    result = run_mas_row(
                        row,
                        gemini_client=gemini_client,
                        reference_repository=repository,
                        reference_version=snapshot["version"],
                        agent=supervisor_agent,
                        root=ROOT,
                        progress=lambda message, current=index: print(
                            f"[MAS {current}/{len(rows)}] {message}", flush=True
                        ),
                        trace_callbacks=[langsmith_tracer],
                    )
                    result["status"] = "ok"
                except Exception as exc:
                    result = {
                        "status": "error",
                        "image_id": row.get("mapillary_image_id"),
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                if result.get("prediction"):
                    prediction = result["prediction"]
                    print(
                        "RESULT "
                        f"image_id={result.get('image_id')} "
                        f"country={prediction.get('country')} "
                        f"confidence={prediction.get('confidence')} "
                        f"alternatives={prediction.get('alternatives', [])} "
                        f"specialists={result.get('specialists_used', [])} "
                        f"reexaminations={len(result.get('reexamine_results', []))}"
                    )
                elif result.get("warning"):
                    print(result["warning"])
                    print(f"SUGGESTION: {result.get('suggestion', 'retry later')}")
                elif result.get("error"):
                    print(f"ERROR image_id={result.get('image_id')}: {result['error']}")
                handle.write(json.dumps(result, ensure_ascii=False) + "\n")
                print(json.dumps({"index": index, **result}, ensure_ascii=False))
        print(f"wrote {len(rows)} results to {args.output}")
        return 0
    finally:
        print("[LangSmith] flushing mandatory trace uploads", flush=True)
        flush_langsmith_traces(tracer=langsmith_tracer)
        print("[LangSmith] trace upload flush completed", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
