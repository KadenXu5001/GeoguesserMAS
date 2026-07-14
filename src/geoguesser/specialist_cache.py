from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


MAX_CACHE_READS = 3


def _cache_path() -> Path:
    root = Path(os.environ.get("DEEPAGENTS_CACHE_DIR", ".deepagents"))
    root.mkdir(parents=True, exist_ok=True)
    return root / "specialist_cache.json"


class SpecialistCache:
    """Persistent one-execution cache for named specialists."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or _cache_path()

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return value if isinstance(value, dict) else {}

    def _save(self, value: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        temporary.replace(self.path)

    def get(self, specialist: str) -> tuple[str | list[Any] | dict[str, Any] | None, str | None]:
        data = self._load()
        entry = data.get(specialist)
        if not isinstance(entry, dict):
            return None, None
        if "content" not in entry:
            if entry.get("attempted"):
                return None, "specialist execution already attempted; retries are forbidden"
            return None, None
        reads = int(entry.get("reads", 0))
        if reads >= MAX_CACHE_READS:
            return None, "specialist cache read capacity reached"
        entry["reads"] = reads + 1
        self._save(data)
        return entry["content"], None

    def mark_attempted(self, specialist: str) -> None:
        data = self._load()
        if specialist in data:
            return
        data[specialist] = {"attempted": True, "reads": 0}
        self._save(data)

    def put(self, specialist: str, content: Any) -> None:
        data = self._load()
        entry = data.get(specialist)
        if isinstance(entry, dict) and "content" in entry:
            return
        data[specialist] = {"attempted": True, "content": content, "reads": 0}
        self._save(data)
