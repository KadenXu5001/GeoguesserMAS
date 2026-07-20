from __future__ import annotations

import csv
import hashlib
import json
import time
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping, Protocol

from geoguesser.object_store import (
    RUNTIME_PRIVATE,
    SOURCE_PRIVATE,
    LocalObjectStore,
    StoredObject,
)


PILOT_MANIFESTS = (
    Path("data/datasets/dev_v1.csv"),
    Path("data/datasets/eval_c1.csv"),
)
DEFAULT_MIGRATION_REPORT = Path("data/migrations/pilot_v1_object_store.json")
LEGACY_MEDIA_ROOTS = (Path("data/panoramas"), Path("data/rendered"))
HEADINGS = (0, 90, 180, 270)


class MigrationRepository(Protocol):
    def attach_object_store_assets(
        self,
        image_id: str,
        *,
        panorama_object: Mapping[str, Any],
        view_objects: list[Mapping[str, Any]],
        migration_version: str,
    ) -> None: ...


def _manifest_rows(paths: Iterable[Path]) -> tuple[list[dict[str, str]], dict[str, str]]:
    rows: list[dict[str, str]] = []
    checksums: dict[str, str] = {}
    for path in paths:
        raw = path.read_bytes()
        checksums[path.as_posix()] = hashlib.sha256(raw).hexdigest()
        with path.open(newline="", encoding="utf-8") as handle:
            rows.extend(dict(row) for row in csv.DictReader(handle))
    identities = [row["mapillary_image_id"] for row in rows]
    if len(identities) != len(set(identities)):
        raise ValueError("pilot manifests contain duplicate image identities")
    return rows, checksums


def _store_verified(
    store: LocalObjectStore,
    source_path: Path,
    expected_sha256: str,
    *,
    namespace: str,
    country_iso2: str,
) -> StoredObject:
    if not source_path.is_file():
        expected_key = (
            f"countries/{country_iso2}/objects/{expected_sha256[:2]}/"
            f"{expected_sha256}{source_path.suffix.lower()}"
        )
        migrated_path = store.path_for(namespace, expected_key)
        if not migrated_path.is_file():
            raise FileNotFoundError(f"legacy and migrated assets are missing: {source_path}")
        source_path = migrated_path
    stored = store.put_file(
        source_path,
        namespace=namespace,
        country_iso2=country_iso2,
        content_type="image/jpeg",
    )
    if stored.sha256 != expected_sha256:
        raise ValueError(f"manifest checksum mismatch: {source_path}")
    return stored


def _migration_reference(stored: StoredObject) -> dict[str, Any]:
    document = stored.as_document()
    path = str(document.pop("path"))
    return {**document, "object_store_path": path}


def migrate_pilot_assets(
    store: LocalObjectStore,
    repository: MigrationRepository,
    *,
    manifest_paths: Iterable[Path] = PILOT_MANIFESTS,
    report_path: Path = DEFAULT_MIGRATION_REPORT,
    remove_legacy_files: bool = False,
) -> dict[str, Any]:
    rows, manifest_checksums = _manifest_rows(manifest_paths)
    country_counts: Counter[str] = Counter()
    unique_objects: set[tuple[str, str]] = set()
    total_source_bytes = 0
    migrated_items = []
    legacy_paths: set[Path] = set()
    for row in rows:
        image_id = row["mapillary_image_id"]
        country_iso2 = row["country_iso2"].upper()
        panorama = _store_verified(
            store,
            Path(row["panorama_path"]),
            row["panorama_sha256"],
            namespace=SOURCE_PRIVATE,
            country_iso2=country_iso2,
        )
        legacy_paths.add(Path(row["panorama_path"]))
        total_source_bytes += panorama.byte_count
        unique_objects.add((panorama.storage_namespace, panorama.object_key))
        views = []
        for heading in HEADINGS:
            view = _store_verified(
                store,
                Path(row[f"view_h{heading:03d}_path"]),
                row[f"view_h{heading:03d}_sha256"],
                namespace=RUNTIME_PRIVATE,
                country_iso2=country_iso2,
            )
            legacy_paths.add(Path(row[f"view_h{heading:03d}_path"]))
            total_source_bytes += view.byte_count
            unique_objects.add((view.storage_namespace, view.object_key))
            views.append({"heading": heading, **_migration_reference(view)})
        panorama_reference = _migration_reference(panorama)
        repository.attach_object_store_assets(
            image_id,
            panorama_object=panorama_reference,
            view_objects=views,
            migration_version="pilot-object-store-v1",
        )
        country_counts[country_iso2] += 1
        migrated_items.append(
            {
                "provider": "mapillary",
                "provider_image_id": image_id,
                "country_iso2": country_iso2,
                "panorama_object_key": panorama.object_key,
                "panorama_object_store_path": panorama.path.as_posix(),
                "view_object_keys": [view["object_key"] for view in views],
                "view_object_store_paths": {
                    str(view["heading"]): str(view["object_store_path"])
                    for view in views
                },
            }
        )

    report = {
        "schema_version": 1,
        "migration_version": "pilot-object-store-v1",
        "dataset_version": "pilot_v1",
        "status": "objects_verified",
        "completed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "storage_policy": "country-scoped-content-addressed-private-namespaces-v1",
        "manifest_sha256": manifest_checksums,
        "panorama_count": len(rows),
        "asset_reference_count": len(rows) * 5,
        "unique_object_count": len(unique_objects),
        "source_byte_count": total_source_bytes,
        "countries": dict(sorted(country_counts.items())),
        "items": migrated_items,
    }
    _write_report(report_path, report)
    removed = 0
    if remove_legacy_files:
        removed = _remove_legacy_files(legacy_paths)
    report["status"] = "complete"
    report["legacy_files_removed"] = removed
    report["legacy_files_retained"] = not remove_legacy_files
    _write_report(report_path, report)
    return report


def _write_report(path: Path, report: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    temporary_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    temporary_path.replace(path)


def _remove_legacy_files(paths: Iterable[Path]) -> int:
    allowed_roots = tuple(root.resolve() for root in LEGACY_MEDIA_ROOTS)
    removed = 0
    for path in sorted(set(paths), key=lambda item: item.as_posix()):
        resolved = path.resolve()
        if not any(resolved.is_relative_to(root) for root in allowed_roots):
            raise ValueError(f"refusing to remove media outside legacy roots: {path}")
        if path.is_file():
            path.unlink()
            removed += 1
    for root in LEGACY_MEDIA_ROOTS:
        if not root.exists():
            continue
        directories = sorted(
            (path for path in root.rglob("*") if path.is_dir()),
            key=lambda path: len(path.parts),
            reverse=True,
        )
        for directory in directories:
            try:
                directory.rmdir()
            except OSError:
                pass
        try:
            root.rmdir()
        except OSError:
            pass
    return removed
