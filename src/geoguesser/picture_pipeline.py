from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from PIL import Image, ImageDraw

from geoguesser.boundaries import CountryBoundaries
from geoguesser.mapillary import MapillaryClient
from geoguesser.panorama import CARDINAL_HEADINGS, render_cardinal_views
from geoguesser.pilot import PILOT_COUNTRIES
from geoguesser.storage import MongoRepository


DEFAULT_COVERAGE_SCAN = Path("data/coverage_scan.json")
DEFAULT_PANORAMA_DIR = Path("data/panoramas")
DEFAULT_RENDERED_DIR = Path("data/rendered")


def _coordinates(metadata: Mapping[str, Any]) -> tuple[float, float]:
    geometry = metadata.get("computed_geometry") or metadata.get("geometry")
    if not geometry or geometry.get("type") != "Point":
        raise ValueError("Mapillary metadata has no point geometry")
    longitude, latitude = geometry["coordinates"]
    return float(latitude), float(longitude)


def _sequence_id(metadata: Mapping[str, Any], fallback: str) -> str:
    sequence = metadata.get("sequence")
    if isinstance(sequence, Mapping):
        return str(sequence.get("id") or fallback)
    return str(sequence or fallback)


def pilot_candidates(path: Path = DEFAULT_COVERAGE_SCAN) -> Iterable[tuple[str, dict]]:
    report = json.loads(path.read_text(encoding="utf-8"))
    pilot_iso2 = {country.iso2 for country in PILOT_COUNTRIES}
    for country in report["countries"]:
        if country["iso2"] not in pilot_iso2:
            continue
        for evidence in country.get("evidence", []):
            yield country["iso2"], evidence


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def ingest_picture_candidates(
    repository: MongoRepository,
    mapillary: MapillaryClient,
    boundaries: CountryBoundaries,
    *,
    limit: int | None = None,
    country_iso2: str | None = None,
    split: str = "development",
    coverage_path: Path = DEFAULT_COVERAGE_SCAN,
    panorama_dir: Path = DEFAULT_PANORAMA_DIR,
    rendered_dir: Path = DEFAULT_RENDERED_DIR,
) -> dict[str, int]:
    counts = {
        "examined": 0,
        "rendered": 0,
        "rejected": 0,
        "failed": 0,
        "skipped": 0,
    }
    for expected_country, evidence in pilot_candidates(coverage_path):
        if country_iso2 and expected_country != country_iso2.upper():
            continue
        if limit is not None and counts["examined"] >= limit:
            break
        image_id = str(evidence["image_id"])
        existing = repository.get_panorama(image_id)
        if existing and existing.get("status") in {"downloaded", "rendered"}:
            counts["skipped"] += 1
            continue
        counts["examined"] += 1
        repository.record_attempt(image_id, "ingest", "started")
        try:
            metadata = mapillary.get_image(image_id)
            if metadata.get("is_pano") is not True:
                raise ValueError("Mapillary image-level is_pano is not true")
            latitude, longitude = _coordinates(metadata)
            sequence_id = _sequence_id(metadata, str(evidence["sequence_id"]))
            repository.record_candidate(
                mapillary_image_id=image_id,
                sequence_id=sequence_id,
                latitude=latitude,
                longitude=longitude,
                source={
                    "provider": "mapillary",
                    "captured_at": metadata.get("captured_at"),
                    "quality_score": metadata.get("quality_score"),
                    "width": metadata.get("width"),
                    "height": metadata.get("height"),
                },
            )
            actual_country = boundaries.country_iso2(latitude, longitude)
            if actual_country != expected_country:
                repository.reject(
                    image_id,
                    f"offline boundary resolved {actual_country!r}, expected {expected_country}",
                )
                repository.record_attempt(image_id, "validate_country", "rejected")
                counts["rejected"] += 1
                continue
            repository.assign_validated(
                mapillary_image_id=image_id,
                country_iso2=actual_country,
                split=split,
                boundary_dataset=boundaries.dataset_id,
            )

            panorama_path = panorama_dir / actual_country / f"{image_id}.jpg"
            downloaded = mapillary.download_original(metadata, panorama_path)
            repository.mark_downloaded(
                image_id,
                path=downloaded.path.as_posix(),
                sha256=downloaded.sha256,
                byte_count=downloaded.byte_count,
                width=downloaded.width,
                height=downloaded.height,
            )
            view_paths = render_cardinal_views(
                downloaded.path,
                rendered_dir / actual_country / image_id,
            )
            views = [
                {
                    "heading": heading,
                    "path": path.as_posix(),
                    "sha256": _file_sha256(path),
                }
                for heading, path in zip(CARDINAL_HEADINGS, view_paths)
            ]
            repository.mark_rendered(image_id, views)
            repository.record_attempt(image_id, "ingest", "rendered")
            counts["rendered"] += 1
        except ValueError as error:
            repository.reject(image_id, str(error))
            repository.record_attempt(image_id, "ingest", "rejected", str(error))
            counts["rejected"] += 1
        except Exception as error:
            repository.record_attempt(image_id, "ingest", "failed", str(error))
            counts["failed"] += 1
    return counts


def create_contact_sheet(panorama: Mapping[str, Any], output_path: Path) -> Path:
    rendered_views = panorama.get("rendered_views") or []
    if len(rendered_views) != 4:
        raise ValueError("panorama does not have four rendered views")
    tiles = []
    for view in sorted(rendered_views, key=lambda item: item["heading"]):
        with Image.open(view["path"]) as image:
            tiles.append((view["heading"], image.convert("RGB").copy()))
    tile_width, tile_height = tiles[0][1].size
    label_height = 40
    sheet = Image.new("RGB", (tile_width * 2, (tile_height + label_height) * 2), "white")
    draw = ImageDraw.Draw(sheet)
    for index, (heading, image) in enumerate(tiles):
        x = (index % 2) * tile_width
        y = (index // 2) * (tile_height + label_height)
        sheet.paste(image, (x, y + label_height))
        draw.text((x + 12, y + 10), f"Heading {heading} degrees", fill="black")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output_path, format="JPEG", quality=90)
    return output_path
