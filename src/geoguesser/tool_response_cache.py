from __future__ import annotations

import json
import os
import threading
import uuid
from pathlib import Path
from typing import Any


MAX_CACHE_READS = 3


class ToolResponseCache:
    """Persistent cache for deterministic reference-tool responses only."""

    def __init__(self, path: Path | None = None) -> None:
        root = Path(os.environ.get("DEEPAGENTS_CACHE_DIR", ".deepagents"))
        self.path = path or root / "tool_response_cache.json"
        self._lock = threading.Lock()
        # The cache contents persist across runs, but read capacity is scoped to this
        # cache instance, which is created for one MAS runtime context/run.
        self._reads: dict[str, int] = {}

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
        temporary = self.path.with_name(f"{self.path.name}.{uuid.uuid4().hex}.tmp")
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self.path)

    def get(self, key: str) -> tuple[Any | None, str | None]:
        with self._lock:
            data = self._load()
            entry = data.get(key)
            if not isinstance(entry, dict) or "response" not in entry:
                return None, None
            reads = self._reads.get(key, 0)
            if reads >= MAX_CACHE_READS:
                return None, "tool response cache read capacity reached"
            self._reads[key] = reads + 1
            return entry["response"], None

    def put(self, key: str, response: Any) -> None:
        with self._lock:
            data = self._load()
            if key in data:
                return
            data[key] = {"response": response}
            self._save(data)
