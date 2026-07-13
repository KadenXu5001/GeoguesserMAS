import csv

import pytest

from geoguesser import dataset_manifest
from geoguesser.dataset_manifest import write_pilot_manifests
from geoguesser.pilot import PilotCountry


def panorama(image_id: str, country: str, split: str) -> dict:
    return {
        "mapillary_image_id": image_id,
        "country_iso2": country,
        "split": split,
        "status": "rendered",
        "panorama_file": {
            "path": f"data/panoramas/{country}/{image_id}.jpg",
            "sha256": f"pano-{image_id}",
            "width": 5760,
            "height": 2880,
        },
        "rendered_views": [
            {
                "heading": heading,
                "path": f"data/rendered/{country}/{image_id}/h{heading}.jpg",
                "sha256": f"{image_id}-{heading}",
            }
            for heading in (0, 90, 180, 270)
        ],
        "quality": {
            "policy_version": "panorama-quality-v1",
            "manual_review": {"status": "approved"},
        },
    }


class Repository:
    def __init__(self, rows):
        self.rows = rows

    def list_panoramas(self, *, status=None):
        assert status == "rendered"
        return self.rows


def test_write_pilot_manifests_writes_exact_split_csvs(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        dataset_manifest,
        "PILOT_COUNTRIES",
        (PilotCountry("FR", "France", "Europe"),),
    )
    monkeypatch.setattr(dataset_manifest, "DEVELOPMENT_PER_COUNTRY", 1)
    monkeypatch.setattr(dataset_manifest, "EVALUATION_PER_COUNTRY", 1)

    outputs = write_pilot_manifests(
        Repository(
            [
                panorama("dev-1", "FR", "development"),
                panorama("eval-1", "FR", "evaluation"),
            ]
        ),
        tmp_path,
    )

    assert outputs["development"] == tmp_path / "dev_v1.csv"
    with outputs["development"].open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["mapillary_image_id"] == "dev-1"
    assert rows[0]["country_iso2"] == "FR"
    assert rows[0]["view_h270_sha256"] == "dev-1-270"


def test_write_pilot_manifests_rejects_incomplete_counts(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        dataset_manifest,
        "PILOT_COUNTRIES",
        (PilotCountry("FR", "France", "Europe"),),
    )
    monkeypatch.setattr(dataset_manifest, "DEVELOPMENT_PER_COUNTRY", 1)
    monkeypatch.setattr(dataset_manifest, "EVALUATION_PER_COUNTRY", 1)

    with pytest.raises(ValueError, match="evaluation manifest"):
        write_pilot_manifests(
            Repository([panorama("dev-1", "FR", "development")]),
            tmp_path,
        )
