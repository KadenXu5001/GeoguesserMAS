from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


DEFAULT_DEFINITION_DIR = Path("data/dataset_definitions")
PILOT_DATASET_VERSION = "pilot_v1"
_VERSION_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


@dataclass(frozen=True)
class DatasetCountry:
    iso2: str
    country: str
    continent: str


@dataclass(frozen=True)
class DatasetDefinition:
    version: str
    status: str
    countries: tuple[DatasetCountry, ...]
    development_per_country: int
    evaluation_per_country: int
    coverage_report: Path
    split_seed: str
    document: Mapping[str, Any]
    sha256: str

    @property
    def country_iso2(self) -> frozenset[str]:
        return frozenset(country.iso2 for country in self.countries)


def definition_path(
    version: str,
    *,
    definition_dir: Path = DEFAULT_DEFINITION_DIR,
) -> Path:
    if not _VERSION_PATTERN.fullmatch(version):
        raise ValueError("dataset version contains unsupported characters")
    return definition_dir / f"{version}.json"


def load_dataset_definition(
    version: str,
    *,
    definition_dir: Path = DEFAULT_DEFINITION_DIR,
) -> DatasetDefinition:
    path = definition_path(version, definition_dir=definition_dir)
    raw = path.read_bytes()
    document = json.loads(raw.decode("utf-8"))
    if document.get("schema_version") != 1:
        raise ValueError("dataset definition must use schema_version 1")
    if document.get("version") != version:
        raise ValueError("dataset definition version does not match its filename")
    if document.get("status") not in {"draft", "frozen", "retired"}:
        raise ValueError("dataset definition has an unsupported status")

    country_rows = document.get("countries")
    if not isinstance(country_rows, list) or not country_rows:
        raise ValueError("dataset definition must contain countries")
    countries = tuple(
        DatasetCountry(
            iso2=str(row["iso2"]).upper(),
            country=str(row["country"]),
            continent=str(row["continent"]),
        )
        for row in country_rows
    )
    iso2_values = [country.iso2 for country in countries]
    if any(not re.fullmatch(r"[A-Z]{2}", iso2) for iso2 in iso2_values):
        raise ValueError("dataset country ISO2 codes must be two uppercase letters")
    if len(iso2_values) != len(set(iso2_values)):
        raise ValueError("dataset definition contains duplicate country ISO2 codes")
    if len({country.continent for country in countries}) < 5:
        raise ValueError("dataset definition must represent at least five continents")

    targets = document.get("targets") or {}
    development = int(targets.get("development_per_country", 0))
    evaluation = int(targets.get("evaluation_per_country", 0))
    if development <= 0 or evaluation <= 0:
        raise ValueError("dataset split targets must be positive")
    expected_total = len(countries) * (development + evaluation)
    if int(targets.get("total_panoramas", 0)) != expected_total:
        raise ValueError("dataset total panorama target is inconsistent")

    country_selection = document.get("country_selection") or {}
    if country_selection.get("status") != "frozen":
        raise ValueError("dataset country selection must be frozen before collection")
    coverage_report = Path(str(country_selection.get("coverage_report", "")))
    report_sha256 = str(country_selection.get("coverage_report_sha256", ""))
    if not coverage_report.is_file():
        raise ValueError(f"coverage report not found: {coverage_report}")
    actual_report_sha256 = hashlib.sha256(coverage_report.read_bytes()).hexdigest()
    if actual_report_sha256 != report_sha256:
        raise ValueError("coverage report checksum does not match dataset definition")
    _validate_coverage_report(coverage_report, iso2_values)

    split_seed = str(document.get("split_seed", ""))
    if not split_seed:
        raise ValueError("dataset definition must record a split seed")
    return DatasetDefinition(
        version=version,
        status=str(document["status"]),
        countries=countries,
        development_per_country=development,
        evaluation_per_country=evaluation,
        coverage_report=coverage_report,
        split_seed=split_seed,
        document=document,
        sha256=hashlib.sha256(raw).hexdigest(),
    )


def _validate_coverage_report(path: Path, selected_iso2: list[str]) -> None:
    report = json.loads(path.read_text(encoding="utf-8"))
    qualified = {
        str(country["iso2"]).upper()
        for country in report.get("countries", [])
        if country.get("qualified")
    }
    missing = sorted(set(selected_iso2) - qualified)
    if missing:
        raise ValueError(
            f"dataset countries are not qualified in the coverage report: {missing}"
        )


def dataset_document(definition: DatasetDefinition) -> dict[str, Any]:
    return {
        **dict(definition.document),
        "definition_sha256": definition.sha256,
    }
