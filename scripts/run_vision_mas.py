"""Run the production MAS for the browser Vision Agent Guide."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
os.environ["LANGSMITH_TRACING"] = "false"
os.environ["LANGCHAIN_TRACING_V2"] = "false"
os.environ["LANGCHAIN_CALLBACKS_BACKGROUND"] = "false"
sys.path.insert(0, str(ROOT / "src"))

from geoguesser.gemini_client import create_gemini_client  # noqa: E402
from geoguesser.langsmith_tracing import create_langsmith_tracer  # noqa: E402
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


def flush_langsmith() -> None:
    from langchain_core.tracers.langchain import wait_for_all_tracers

    wait_for_all_tracers()


def main() -> None:
    request = json.load(sys.stdin)
    paths = request.get("paths")
    if not isinstance(paths, list) or len(paths) != 4:
        raise ValueError("Vision MAS requires four cardinal view paths")
    snapshot = load_reference_snapshot(ROOT / "data" / "reference_tables" / "reference_v1.json")
    row = {
        "view_h000_path": str(Path(paths[0]).resolve()),
        "view_h090_path": str(Path(paths[1]).resolve()),
        "view_h180_path": str(Path(paths[2]).resolve()),
        "view_h270_path": str(Path(paths[3]).resolve()),
    }
    tracer = create_langsmith_tracer()
    try:
        result = run_mas_row(
            row,
            gemini_client=create_gemini_client(),
            reference_repository=SnapshotRepository(snapshot),
            reference_version=snapshot["version"],
            root=ROOT,
            trace_callbacks=[tracer],
        )
        if result.get("warning"):
            raise RuntimeError(result["warning"])
        print(json.dumps({
            "analysis": result["extraction"],
            "informedEvidence": result["informed_evidence"],
        }, ensure_ascii=False))
    finally:
        flush_langsmith()


if __name__ == "__main__":
    main()
