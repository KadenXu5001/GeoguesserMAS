import json

import pytest

from geoguesser.dataset_definition import (
    dataset_document,
    definition_path,
    load_dataset_definition,
)


def test_worldwide_v2_freezes_exactly_30_qualified_countries() -> None:
    definition = load_dataset_definition("worldwide_v2")

    assert len(definition.countries) == 30
    assert len({country.continent for country in definition.countries}) == 6
    assert "ID" in definition.country_iso2
    assert "TN" in definition.country_iso2
    assert "GH" not in definition.country_iso2
    assert definition.development_per_country == 10
    assert definition.evaluation_per_country == 5
    assert len(definition.active_countries("play")) == 29
    assert definition.excluded_iso2("evaluation") == frozenset({"MA"})
    assert "MA" not in {country.iso2 for country in definition.active_countries("reference_generation")}
    assert dataset_document(definition)["definition_sha256"] == definition.sha256


def test_definition_rejects_coverage_report_checksum_mismatch(tmp_path) -> None:
    report = tmp_path / "coverage.json"
    report.write_text(
        json.dumps(
            {
                "countries": [
                    {"iso2": "FR", "qualified": True},
                    {"iso2": "DE", "qualified": True},
                    {"iso2": "US", "qualified": True},
                    {"iso2": "BR", "qualified": True},
                    {"iso2": "JP", "qualified": True},
                    {"iso2": "MA", "qualified": True},
                ]
            }
        ),
        encoding="utf-8",
    )
    definition = {
        "schema_version": 1,
        "version": "test_v1",
        "kind": "panorama_dataset",
        "status": "draft",
        "country_selection": {
            "status": "frozen",
            "coverage_report": str(report),
            "coverage_report_sha256": "0" * 64,
        },
        "countries": [
            {"iso2": "FR", "country": "France", "continent": "Europe"},
            {"iso2": "DE", "country": "Germany", "continent": "Europe"},
            {"iso2": "US", "country": "United States", "continent": "North America"},
            {"iso2": "BR", "country": "Brazil", "continent": "South America"},
            {"iso2": "JP", "country": "Japan", "continent": "Asia"},
            {"iso2": "MA", "country": "Morocco", "continent": "Africa"},
        ],
        "targets": {
            "development_per_country": 1,
            "evaluation_per_country": 1,
            "total_panoramas": 12,
        },
        "constraints": {},
        "split_seed": "test-seed",
    }
    path = tmp_path / "test_v1.json"
    path.write_text(json.dumps(definition), encoding="utf-8")

    with pytest.raises(ValueError, match="checksum"):
        load_dataset_definition("test_v1", definition_dir=tmp_path)


def test_definition_path_rejects_traversal() -> None:
    with pytest.raises(ValueError, match="unsupported characters"):
        definition_path("../worldwide_v2")


def test_definition_rejects_unknown_temporary_exclusion_scope(tmp_path) -> None:
    document = json.loads(
        open("data/dataset_definitions/worldwide_v2.json", encoding="utf-8").read()
    )
    document["version"] = "test_v1"
    document["temporary_exclusions"][0]["scopes"] = ["training"]
    (tmp_path / "test_v1.json").write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(ValueError, match="unsupported scopes"):
        load_dataset_definition("test_v1", definition_dir=tmp_path)
