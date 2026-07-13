from pathlib import Path

from geoguesser.reference_data import load_reference_snapshot, lookup_references


SNAPSHOT = Path("data/reference_tables/reference_v1.json")


def test_reference_snapshot_is_worldwide_and_versioned() -> None:
    snapshot = load_reference_snapshot(SNAPSHOT)

    assert snapshot["version"] == "reference-v1"
    assert snapshot["scope"] == "worldwide"
    assert len(snapshot["sources"]) >= 5


def test_lookup_is_case_insensitive_and_category_scoped() -> None:
    snapshot = load_reference_snapshot(SNAPSHOT)

    rows = lookup_references(snapshot, category="driving_side", country="thailand")

    assert len(rows) == 1
    assert rows[0]["indicator"] == "left"
    assert lookup_references(snapshot, category="bollards", country="Thailand") == []

