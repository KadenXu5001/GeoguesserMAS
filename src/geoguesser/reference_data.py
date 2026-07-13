from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_reference_snapshot(path: Path) -> dict[str, Any]:
    snapshot = json.loads(path.read_text(encoding="utf-8"))
    if snapshot.get("scope") != "worldwide":
        raise ValueError("reference snapshot must be worldwide")
    if not snapshot.get("version") or not snapshot.get("sources"):
        raise ValueError("reference snapshot must include versioned sources")
    return snapshot


def lookup_references(
    snapshot: dict[str, Any],
    *,
    category: str,
    country: str | None = None,
) -> list[dict[str, Any]]:
    rows = [row for row in snapshot.get("rows", []) if row.get("category") == category]
    if country is not None:
        rows = [row for row in rows if row.get("country", "").casefold() == country.casefold()]
    return rows

