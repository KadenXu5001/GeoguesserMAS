from __future__ import annotations

import json
import hashlib
import os
from pathlib import Path
from typing import Mapping

from geoguesser.object_store import LocalObjectStore, RUNTIME_PRIVATE


CARDINAL_HEADINGS = (0, 90, 180, 270)
DEFAULT_PILOT_MIGRATION_REPORT = Path("data/migrations/pilot_v1_object_store.json")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _object_store(root: Path) -> LocalObjectStore:
    configured = os.environ.get("LOCAL_OBJECT_STORE_ROOT")
    store_root = Path(configured) if configured else root / ".local-data"
    if not store_root.is_absolute():
        store_root = root / store_root
    return LocalObjectStore(store_root)


def _legacy_paths(row: Mapping[str, str], root: Path) -> dict[int, Path]:
    paths = {
        heading: root / row[f"view_h{heading:03d}_path"]
        for heading in CARDINAL_HEADINGS
    }
    missing = [str(path) for path in paths.values() if not path.is_file()]
    if missing:
        raise FileNotFoundError(
            "cardinal views are unavailable in both the object store and legacy paths: "
            + ", ".join(missing)
        )
    return paths


def resolve_mas_view_paths(
    row: Mapping[str, str],
    *,
    root: Path = Path("."),
    migration_report: Path | None = None,
    object_store: LocalObjectStore | None = None,
) -> dict[int, Path]:
    """Resolve model inputs from runtime-private object keys when migration applies.

    Pilot manifests intentionally retain their frozen legacy path columns. A completed migration
    report is therefore the authoritative bridge from a manifest image identity to portable
    object-store keys. Storage paths and identities remain local and are never model content.
    """
    root = root.resolve()
    report_path = migration_report or root / DEFAULT_PILOT_MIGRATION_REPORT
    image_id = str(row.get("mapillary_image_id", "")).strip()
    dataset_version = str(row.get("dataset_version", "")).strip()

    if report_path.is_file() and image_id:
        report = json.loads(report_path.read_text(encoding="utf-8"))
        report_version = str(report.get("dataset_version", ""))
        applies = not dataset_version or dataset_version == report_version
        if report.get("status") == "complete" and applies:
            items = {
                str(item.get("provider_image_id")): item
                for item in report.get("items", [])
                if isinstance(item, dict)
            }
            item = items.get(image_id)
            if item is None:
                raise ValueError(
                    f"completed {report_version} migration has no object-store entry for {image_id}"
                )
            keys = item.get("view_object_keys")
            if not isinstance(keys, list) or len(keys) != len(CARDINAL_HEADINGS):
                raise ValueError(f"object-store entry for {image_id} must contain four view keys")
            store = object_store or _object_store(root)
            paths = {
                heading: store.path_for(RUNTIME_PRIVATE, str(key))
                for heading, key in zip(CARDINAL_HEADINGS, keys)
            }
            missing = [str(path) for path in paths.values() if not path.is_file()]
            if missing:
                raise FileNotFoundError(
                    f"runtime-private object-store views are missing for {image_id}: "
                    + ", ".join(missing)
                )
            for heading, key in zip(CARDINAL_HEADINGS, keys):
                expected = str(row.get(f"view_h{heading:03d}_sha256", "")).strip()
                key_digest = Path(str(key)).stem
                if expected and key_digest != expected:
                    raise ValueError(
                        f"object-store key checksum does not match manifest for {image_id}/{heading}"
                    )
                if expected and _sha256(paths[heading]) != expected:
                    raise ValueError(
                        f"runtime-private object checksum does not match manifest for {image_id}/{heading}"
                    )
            return paths

    return _legacy_paths(row, root)
