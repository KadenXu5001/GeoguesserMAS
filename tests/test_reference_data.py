import json
from pathlib import Path

from geoguesser.reference_data import load_reference_snapshot, lookup_references


SNAPSHOT = Path("data/reference_tables/reference_v2.json")


def _case_insensitive_key_collisions(value: object, path: str = "$") -> list[str]:
    collisions: list[str] = []
    if isinstance(value, dict):
        seen: dict[str, str] = {}
        for key, child in value.items():
            normalized = key.casefold()
            if normalized in seen:
                collisions.append(f"{path}: {seen[normalized]!r} and {key!r}")
            else:
                seen[normalized] = key
            collisions.extend(_case_insensitive_key_collisions(child, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            collisions.extend(_case_insensitive_key_collisions(child, f"{path}[{index}]"))
    return collisions


def test_reference_snapshot_is_worldwide_and_versioned() -> None:
    snapshot = load_reference_snapshot(SNAPSHOT)

    assert snapshot["version"] == "reference-v2"
    assert snapshot["scope"] == "worldwide"
    assert len(snapshot["sources"]) >= 5


def test_reference_snapshot_has_no_case_insensitive_duplicate_object_keys() -> None:
    snapshot = json.loads(SNAPSHOT.read_text(encoding="utf-8"))

    assert _case_insensitive_key_collisions(snapshot) == []


def test_lookup_is_case_insensitive_and_category_scoped() -> None:
    snapshot = load_reference_snapshot(SNAPSHOT)

    rows = lookup_references(snapshot, category="license_plates", country="thailand")

    assert len(rows) == 1
    assert rows[0]["indicator"] == "white and yellow license plates"
    assert lookup_references(snapshot, category="bollards", country="Thailand")


def test_rural_reference_rows_cover_every_active_worldwide_v2_country() -> None:
    snapshot = load_reference_snapshot(SNAPSHOT)
    definition = json.loads(
        Path("data/dataset_definitions/worldwide_v2.json").read_text(encoding="utf-8")
    )
    excluded = {
        item["iso2"]
        for item in definition.get("temporary_exclusions", [])
        if "reference_generation" in item["scopes"]
    }
    expected = {
        item["country"] for item in definition["countries"] if item["iso2"] not in excluded
    }
    rural_rows = [row for row in snapshot["rows"] if row.get("family") == "rural"]
    covered = {row["country"] for row in rural_rows}

    assert covered == expected
    assert "Morocco" not in covered
    assert all(row.get("indicator") and row.get("source_url") for row in rural_rows)
