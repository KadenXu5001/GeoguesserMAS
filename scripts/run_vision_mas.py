"""Run the production MAS for the browser Vision Agent Guide."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
os.environ["LANGSMITH_TRACING"] = "false"
os.environ["LANGCHAIN_TRACING_V2"] = "false"
os.environ["LANGCHAIN_CALLBACKS_BACKGROUND"] = "false"
sys.path.insert(0, str(ROOT / "src"))

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


def build_mas_row(request: dict[str, Any]) -> dict[str, str]:
    """Preserve object-store identity while adapting the website request to a MAS row."""
    paths = request.get("paths")
    if not isinstance(paths, list) or len(paths) != 4:
        raise ValueError("Vision MAS requires four cardinal view paths")
    row = {
        f"view_h{heading:03d}_path": str(Path(path_value).resolve())
        for heading, path_value in zip((0, 90, 180, 270), paths)
    }
    image_id = request.get("imageId")
    dataset_version = request.get("datasetVersion")
    if isinstance(image_id, str) and image_id.strip():
        row["mapillary_image_id"] = image_id.strip()
    if isinstance(dataset_version, str) and dataset_version.strip():
        row["dataset_version"] = dataset_version.strip()
    hashes = request.get("viewHashes")
    if isinstance(hashes, list) and len(hashes) == 4:
        for heading, digest in zip((0, 90, 180, 270), hashes):
            if isinstance(digest, str) and digest.strip():
                row[f"view_h{heading:03d}_sha256"] = digest.strip()
    return row


def main() -> None:
    request = json.load(sys.stdin)
    snapshot = load_reference_snapshot(ROOT / "data" / "reference_tables" / "reference_v2.json")
    row = build_mas_row(request)
    tracer = create_langsmith_tracer()
    try:
        result = run_mas_row(
            row,
            gemini_client=create_gemini_client(),
            reference_repository=SnapshotRepository(snapshot),
            reference_version=snapshot["version"],
            root=ROOT,
            progress=lambda message: print(
                f"[vision-mas] {message}", file=sys.stderr, flush=True
            ),
            trace_callbacks=[tracer],
        )
        if result.get("warning"):
            raise RuntimeError(result["warning"])
        print(json.dumps({
            "analysis": result["extraction"],
            "informedEvidence": result["informed_evidence"],
            "predictedCountry": result["prediction"]["country"],
            "alternativeCountries": result["prediction"]["alternatives"][:3],
        }, ensure_ascii=False))
    finally:
        print("[vision-mas] flushing mandatory LangSmith traces", file=sys.stderr, flush=True)
        try:
            flush_langsmith_traces(tracer=tracer)
        except Exception as exc:
            print(f"[vision-mas] {exc}", file=sys.stderr, flush=True)
            raise
        print("[vision-mas] LangSmith trace flush completed", file=sys.stderr, flush=True)


if __name__ == "__main__":
    main()
