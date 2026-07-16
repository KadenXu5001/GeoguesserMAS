"""CLI adapter for the localhost vision inspector."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from geoguesser.extraction_runner import extract_cardinal_views
from geoguesser.gemini_client import create_gemini_client


ROOT = Path(__file__).resolve().parents[1]


def load_local_env() -> None:
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and value:
            os.environ.setdefault(key, value)


def main() -> None:
    load_local_env()
    request = json.load(sys.stdin)
    paths = request["paths"]
    views = {heading: Path(path) for heading, path in zip((0, 90, 180, 270), paths)}
    result = extract_cardinal_views(
        create_gemini_client(), views, model=request.get("model", "gemini-3-flash-preview")
    )
    print(json.dumps(result.model_dump()))


if __name__ == "__main__":
    main()
