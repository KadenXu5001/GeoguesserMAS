import csv
import hashlib

from PIL import Image

from geoguesser import asset_migration
from geoguesser.asset_migration import migrate_pilot_assets
from geoguesser.object_store import LocalObjectStore


def _sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_migration_moves_verified_assets_and_preserves_manifest(tmp_path, monkeypatch) -> None:
    legacy_panoramas = tmp_path / "data" / "panoramas"
    legacy_views = tmp_path / "data" / "rendered"
    panorama = legacy_panoramas / "FR" / "image-1.jpg"
    panorama.parent.mkdir(parents=True)
    Image.new("RGB", (400, 200), "green").save(panorama)
    views = {}
    for heading in (0, 90, 180, 270):
        view = legacy_views / "FR" / "image-1" / f"h{heading:03d}.jpg"
        view.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (32, 32), (heading % 255, 20, 30)).save(view)
        views[heading] = view

    manifest = tmp_path / "pilot.csv"
    fieldnames = [
        "mapillary_image_id",
        "country_iso2",
        "panorama_path",
        "panorama_sha256",
        *[
            field
            for heading in (0, 90, 180, 270)
            for field in (f"view_h{heading:03d}_path", f"view_h{heading:03d}_sha256")
        ],
    ]
    row = {
        "mapillary_image_id": "image-1",
        "country_iso2": "FR",
        "panorama_path": str(panorama),
        "panorama_sha256": _sha256(panorama),
    }
    for heading, path in views.items():
        row[f"view_h{heading:03d}_path"] = str(path)
        row[f"view_h{heading:03d}_sha256"] = _sha256(path)
    with manifest.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerow(row)
    original_manifest = manifest.read_bytes()

    class Repository:
        def __init__(self):
            self.calls = []

        def attach_object_store_assets(self, image_id, **kwargs):
            self.calls.append((image_id, kwargs))

    monkeypatch.setattr(
        asset_migration,
        "LEGACY_MEDIA_ROOTS",
        (legacy_panoramas, legacy_views),
    )
    repository = Repository()
    report = migrate_pilot_assets(
        LocalObjectStore(tmp_path / ".local-data"),
        repository,
        manifest_paths=[manifest],
        report_path=tmp_path / "migration.json",
        remove_legacy_files=True,
    )

    assert report["status"] == "complete"
    assert report["legacy_files_removed"] == 5
    assert report["asset_reference_count"] == 5
    assert manifest.read_bytes() == original_manifest
    assert not panorama.exists()
    assert all(not path.exists() for path in views.values())
    item = report["items"][0]
    assert item["panorama_object_key"].startswith("countries/FR/objects/")
    assert all((tmp_path / path).is_file() for path in [
        item["panorama_object_store_path"],
        *item["view_object_store_paths"].values(),
    ])
    assert repository.calls[0][0] == "image-1"
