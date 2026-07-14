from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

from dotenv import load_dotenv
from google import genai

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from geoguesser.mas_runner import run_mas_row  # noqa: E402
from geoguesser.reference_data import load_reference_snapshot  # noqa: E402
from geoguesser.storage import MongoRepository, connect_database  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the GeoGuessr Deep Agents MAS")
    parser.add_argument("--dataset", type=Path, default=ROOT / "data/datasets/dev_v1.csv")
    parser.add_argument("--limit", type=int, default=1, help="rows to run; 0 means all")
    parser.add_argument("--output", type=Path, default=ROOT / ".artifacts/mas-results.jsonl")
    parser.add_argument(
        "--snapshot", type=Path, default=ROOT / "data/reference_tables/reference_v1.json"
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    load_dotenv(ROOT / ".env")
    dataset = args.dataset if args.dataset.is_absolute() else ROOT / args.dataset
    rows = list(csv.DictReader(dataset.open(newline="", encoding="utf-8")))
    if args.limit > 0:
        rows = rows[: args.limit]
    if not rows:
        raise SystemExit("dataset contains no rows")

    snapshot = load_reference_snapshot(args.snapshot)
    client, database = connect_database()
    try:
        client.admin.command("ping")
        repository = MongoRepository(database)
        repository.initialize()
        if not database.reference_rows.find_one({"version": snapshot["version"]}):
            raise SystemExit(
                f"reference version {snapshot['version']} is not seeded; run "
                "python main.py seed-references first"
            )
        gemini_client = genai.Client()
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("w", encoding="utf-8") as handle:
            for index, row in enumerate(rows, start=1):
                try:
                    result = run_mas_row(
                        row,
                        gemini_client=gemini_client,
                        reference_repository=repository,
                        reference_version=snapshot["version"],
                        root=ROOT,
                    )
                    result["status"] = "ok"
                except Exception as exc:
                    result = {
                        "status": "error",
                        "image_id": row.get("mapillary_image_id"),
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                handle.write(json.dumps(result, ensure_ascii=False) + "\n")
                print(json.dumps({"index": index, **result}, ensure_ascii=False))
        print(f"wrote {len(rows)} results to {args.output}")
        return 0
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
