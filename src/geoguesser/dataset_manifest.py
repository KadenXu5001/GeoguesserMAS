from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Iterable, Mapping

from geoguesser.pilot import (
    DEVELOPMENT_PER_COUNTRY,
    EVALUATION_PER_COUNTRY,
    PILOT_COUNTRIES,
    PILOT_VERSION,
)
from geoguesser.storage import MongoRepository


FIELDNAMES = [
    "dataset_version",
    "split",
    "country_iso2",
    "country",
    "mapillary_image_id",
    "panorama_path",
    "panorama_sha256",
    "panorama_width",
    "panorama_height",
    "view_h000_path",
    "view_h000_sha256",
    "view_h090_path",
    "view_h090_sha256",
    "view_h180_path",
    "view_h180_sha256",
    "view_h270_path",
    "view_h270_sha256",
    "quality_policy",
]


def _country_name(iso2: str) -> str:
    for country in PILOT_COUNTRIES:
        if country.iso2 == iso2:
            return country.country
    raise ValueError(f"unexpected pilot country: {iso2}")


def _validated_views(panorama: Mapping[str, Any]) -> dict[int, Mapping[str, Any]]:
    views = {int(view["heading"]): view for view in panorama.get("rendered_views", [])}
    if set(views) != {0, 90, 180, 270}:
        raise ValueError(
            f"{panorama['mapillary_image_id']} does not have the four cardinal views"
        )
    return views


def _row(panorama: Mapping[str, Any]) -> dict[str, Any]:
    views = _validated_views(panorama)
    panorama_file = panorama.get("panorama_file") or {}
    country_iso2 = panorama["country_iso2"]
    quality = panorama.get("quality") or {}
    row = {
        "dataset_version": PILOT_VERSION,
        "split": panorama["split"],
        "country_iso2": country_iso2,
        "country": _country_name(country_iso2),
        "mapillary_image_id": panorama["mapillary_image_id"],
        "panorama_path": panorama_file.get("path"),
        "panorama_sha256": panorama_file.get("sha256"),
        "panorama_width": panorama_file.get("width"),
        "panorama_height": panorama_file.get("height"),
        "quality_policy": quality.get("policy_version"),
    }
    for heading in (0, 90, 180, 270):
        row[f"view_h{heading:03d}_path"] = views[heading]["path"]
        row[f"view_h{heading:03d}_sha256"] = views[heading]["sha256"]
    return row


def _approved_rendered(panoramas: Iterable[Mapping[str, Any]], split: str) -> list[dict[str, Any]]:
    rows = []
    for panorama in panoramas:
        if panorama.get("status") != "rendered" or panorama.get("split") != split:
            continue
        if panorama.get("quality", {}).get("manual_review", {}).get("status") != "approved":
            continue
        rows.append(_row(panorama))
    return sorted(rows, key=lambda item: (item["country_iso2"], item["mapillary_image_id"]))


def _validate_counts(rows: list[dict[str, Any]], *, split: str, expected_per_country: int) -> None:
    counts = {country.iso2: 0 for country in PILOT_COUNTRIES}
    for row in rows:
        counts[row["country_iso2"]] += 1
        if row["split"] != split:
            raise ValueError(f"unexpected split in manifest row: {row['split']}")
    missing = {
        country: count
        for country, count in counts.items()
        if count != expected_per_country
    }
    if missing:
        raise ValueError(
            f"{split} manifest does not match target counts: {missing}"
        )


def write_pilot_manifests(
    repository: MongoRepository,
    output_dir: Path,
) -> dict[str, Path]:
    panoramas = repository.list_panoramas(status="rendered")
    dev_rows = _approved_rendered(panoramas, "development")
    eval_rows = _approved_rendered(panoramas, "evaluation")
    _validate_counts(
        dev_rows,
        split="development",
        expected_per_country=DEVELOPMENT_PER_COUNTRY,
    )
    _validate_counts(
        eval_rows,
        split="evaluation",
        expected_per_country=EVALUATION_PER_COUNTRY,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    outputs = {
        "development": output_dir / "dev_v1.csv",
        "evaluation": output_dir / "eval_c1.csv",
    }
    for path, rows in ((outputs["development"], dev_rows), (outputs["evaluation"], eval_rows)):
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
            writer.writeheader()
            writer.writerows(rows)
    return outputs
