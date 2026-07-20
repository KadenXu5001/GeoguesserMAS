from __future__ import annotations

import argparse
from collections import Counter, deque
import hashlib
import json
import math
import os
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Iterator

import mapbox_vector_tile
import mercantile
import requests
from dotenv import load_dotenv
from haversine import Unit, haversine

from geoguesser.boundaries import CountryBoundaries


TILE_ENDPOINT = "https://tiles.mapillary.com/maps/vtp/mly1_public/2/{z}/{x}/{y}"


@dataclass(frozen=True)
class CoveragePoint:
    image_id: str
    sequence_id: str
    latitude: float
    longitude: float
    captured_at: int | None
    quality_score: float | None


def _grid_centers(bbox: list[float], grid_size: int = 5) -> Iterator[tuple[float, float]]:
    west, south, east, north = bbox
    yield ((west + east) / 2, (south + north) / 2)
    fractions = [((index + 0.5) / grid_size) for index in range(grid_size)]
    cells = [
        (west + (east - west) * x, south + (north - south) * y)
        for y in fractions
        for x in fractions
    ]
    cells.sort(key=lambda point: abs(point[0] - (west + east) / 2) + abs(point[1] - (south + north) / 2))
    yield from cells


def candidate_tiles(bbox: list[float], *, zoom: int, max_tiles: int) -> list[mercantile.Tile]:
    """Return deterministic, progressively denser exploratory tiles for a country."""
    seen: set[tuple[int, int, int]] = set()
    tiles: list[mercantile.Tile] = []
    grid_size = 1
    while len(tiles) < max_tiles:
        before = len(tiles)
        for longitude, latitude in _grid_centers(bbox, grid_size=grid_size):
            tile = mercantile.tile(longitude, latitude, zoom)
            key = (tile.x, tile.y, tile.z)
            if key in seen:
                continue
            seen.add(key)
            tiles.append(tile)
            if len(tiles) >= max_tiles:
                break
        if len(tiles) >= max_tiles:
            break
        grid_size *= 2
        if len(tiles) == before and grid_size > 128:
            break
    return tiles


def _neighbor_tiles(tile: mercantile.Tile) -> Iterator[mercantile.Tile]:
    """Yield nearby tiles so productive areas receive a deeper local scan."""
    limit = 2**tile.z
    for y_offset in (-1, 0, 1):
        for x_offset in (-1, 0, 1):
            if x_offset == 0 and y_offset == 0:
                continue
            x = tile.x + x_offset
            y = tile.y + y_offset
            if 0 <= x < limit and 0 <= y < limit:
                yield mercantile.Tile(x=x, y=y, z=tile.z)


def _tile_intersects_bbox(tile: mercantile.Tile, bbox: list[float]) -> bool:
    bounds = mercantile.bounds(tile)
    west, south, east, north = bbox
    return not (
        bounds.east < west
        or bounds.west > east
        or bounds.north < south
        or bounds.south > north
    )


def _tile_coordinate_to_lnglat(
    tile: mercantile.Tile,
    x: float,
    y: float,
    extent: int,
) -> tuple[float, float]:
    scale = 2**tile.z
    world_x = (tile.x + x / extent) / scale
    world_y = (tile.y + y / extent) / scale
    longitude = world_x * 360.0 - 180.0
    latitude = math.degrees(math.atan(math.sinh(math.pi * (1.0 - 2.0 * world_y))))
    return longitude, latitude


def _first_coordinate(geometry: dict) -> tuple[float, float]:
    coordinates = geometry["coordinates"]
    geometry_type = geometry["type"]
    if geometry_type == "LineString":
        return tuple(coordinates[len(coordinates) // 2])
    if geometry_type == "MultiLineString":
        longest = max(coordinates, key=len)
        return tuple(longest[len(longest) // 2])
    if geometry_type == "Point":
        return tuple(coordinates)
    raise ValueError(f"unsupported sequence geometry: {geometry_type}")


def fetch_sequence_tile(
    session: requests.Session,
    token: str,
    tile: mercantile.Tile,
    *,
    attempts: int = 4,
) -> list[CoveragePoint]:
    url = TILE_ENDPOINT.format(z=tile.z, x=tile.x, y=tile.y)
    for attempt in range(attempts):
        response = session.get(url, params={"access_token": token}, timeout=60)
        if response.status_code == 200:
            break
        if response.status_code not in {429, 500, 502, 503, 504} or attempt == attempts - 1:
            raise RuntimeError(f"Mapillary tile request failed with status {response.status_code}")
        time.sleep(2**attempt)
    decoded = mapbox_vector_tile.decode(
        response.content,
        default_options={"y_coord_down": True},
    )
    layer = decoded.get("sequence")
    if not layer:
        return []
    extent = int(layer.get("extent", 4096))
    results: list[CoveragePoint] = []
    for feature in layer.get("features", []):
        properties = feature.get("properties", {})
        if not properties.get("is_pano"):
            continue
        x, y = _first_coordinate(feature["geometry"])
        longitude, latitude = _tile_coordinate_to_lnglat(tile, x, y, extent)
        results.append(
            CoveragePoint(
                image_id=str(properties.get("image_id", "")),
                sequence_id=str(properties.get("id", "")),
                latitude=latitude,
                longitude=longitude,
                captured_at=properties.get("captured_at"),
                quality_score=properties.get("quality_score"),
            )
        )
    return results


def _inside_bbox(point: CoveragePoint, bbox: list[float]) -> bool:
    west, south, east, north = bbox
    return west <= point.longitude <= east and south <= point.latitude <= north


def select_separated(
    candidates: Iterable[CoveragePoint],
    *,
    minimum_distance_km: float,
    target: int,
) -> list[CoveragePoint]:
    selected: list[CoveragePoint] = []
    seen_sequences: set[str] = set()
    for candidate in candidates:
        if not candidate.image_id or not candidate.sequence_id or candidate.sequence_id in seen_sequences:
            continue
        location = (candidate.latitude, candidate.longitude)
        if any(
            haversine(location, (item.latitude, item.longitude), unit=Unit.KILOMETERS)
            < minimum_distance_km
            for item in selected
        ):
            continue
        selected.append(candidate)
        seen_sequences.add(candidate.sequence_id)
        if len(selected) >= target:
            break
    return selected


def scan_country(
    country: dict,
    token: str,
    *,
    zoom: int = 8,
    max_tiles: int = 64,
    target: int = 15,
    minimum_distance_km: float = 10.0,
    boundaries: CountryBoundaries | None = None,
) -> dict:
    if boundaries is None:
        raise ValueError("deep coverage scans require pinned offline country boundaries")

    eligible: list[CoveragePoint] = []
    selected: list[CoveragePoint] = []
    rejection_counts: Counter[str] = Counter()
    raw_candidates_seen = 0
    seen_images: set[str] = set()
    seen_sequences: set[str] = set()
    searched_tiles: list[str] = []
    tiles_scanned = 0
    session = requests.Session()
    exploratory = deque(
        candidate_tiles(country["bbox"], zoom=zoom, max_tiles=max_tiles * 4)
    )
    pending: deque[mercantile.Tile] = deque()
    queued: set[tuple[int, int, int]] = set()
    visited: set[tuple[int, int, int]] = set()

    def enqueue(tile: mercantile.Tile, *, prioritize: bool = False) -> None:
        key = (tile.x, tile.y, tile.z)
        if (
            key in queued
            or key in visited
            or not _tile_intersects_bbox(tile, country["bbox"])
        ):
            return
        queued.add(key)
        if prioritize:
            pending.appendleft(tile)
        else:
            pending.append(tile)

    while exploratory and len(pending) < 4:
        enqueue(exploratory.popleft())

    while pending and tiles_scanned < max_tiles:
        tile = pending.popleft()
        key = (tile.x, tile.y, tile.z)
        queued.discard(key)
        if key in visited:
            continue
        visited.add(key)
        points = fetch_sequence_tile(session, token, tile)
        raw_candidates_seen += len(points)
        new_eligible = 0
        for point in points:
            if not point.image_id or not point.sequence_id:
                rejection_counts["missing_source_identity"] += 1
                continue
            if not _inside_bbox(point, country["bbox"]):
                rejection_counts["outside_candidate_bbox"] += 1
                continue
            if (
                boundaries.country_iso2(point.latitude, point.longitude)
                != country["iso2"].upper()
            ):
                rejection_counts["country_boundary_mismatch"] += 1
                continue
            if point.image_id in seen_images:
                rejection_counts["duplicate_provider_image"] += 1
                continue
            if point.sequence_id in seen_sequences:
                rejection_counts["duplicate_provider_sequence"] += 1
                continue
            seen_images.add(point.image_id)
            seen_sequences.add(point.sequence_id)
            eligible.append(point)
            new_eligible += 1

        selected = select_separated(
            eligible,
            minimum_distance_km=minimum_distance_km,
            target=target,
        )
        tiles_scanned += 1
        searched_tiles.append(f"{tile.z}/{tile.x}/{tile.y}")
        if len(selected) >= target:
            break
        if new_eligible:
            for neighbor in reversed(list(_neighbor_tiles(tile))):
                enqueue(neighbor, prioritize=True)
        while exploratory and len(pending) < 4:
            enqueue(exploratory.popleft())

    rejection_counts["not_selected_by_distance_policy"] += max(
        0, len(eligible) - len(selected)
    )
    qualified = len(selected) >= target
    return {
        **country,
        "provider": "mapillary",
        "qualified": qualified,
        "separated_pano_sequences": len(selected),
        "minimum_distance_km": minimum_distance_km,
        "tiles_scanned": tiles_scanned,
        "tiles_searched": searched_tiles,
        "candidates_seen": raw_candidates_seen,
        "candidates_eligible_before_distance": len(eligible),
        "candidates_rejected": dict(sorted(rejection_counts.items())),
        "failure_reason": (
            None
            if qualified
            else (
                "insufficient_panorama_coverage"
                if not eligible
                else "insufficient_coverage"
            )
        ),
        "evidence": [asdict(point) for point in selected],
    }


def scan_all(
    candidates_path: Path,
    output_path: Path,
    *,
    max_tiles: int,
    target: int,
    minimum_countries: int = 30,
    country_iso2: str | None = None,
    resume: bool = True,
) -> dict:
    load_dotenv()
    token = os.environ.get("MAPILLARY_ACCESS_TOKEN")
    if not token:
        raise RuntimeError("MAPILLARY_ACCESS_TOKEN is required")
    boundaries = CountryBoundaries()
    candidate_bytes = candidates_path.read_bytes()
    candidates = json.loads(candidate_bytes.decode("utf-8"))
    if country_iso2:
        candidates = [
            candidate
            for candidate in candidates
            if candidate["iso2"].upper() == country_iso2.upper()
        ]
        if not candidates:
            raise ValueError(f"unknown country in candidates file: {country_iso2}")
    scan_configuration = {
        "provider": "mapillary",
        "target": target,
        "minimum_distance_km": 10.0,
        "sequence_layer_zoom": 8,
        "max_tiles_per_country": max_tiles,
        "boundary_dataset": boundaries.dataset_id,
        "candidate_catalog": candidates_path.as_posix(),
        "candidate_catalog_sha256": hashlib.sha256(candidate_bytes).hexdigest(),
        "adaptive_strategy": "progressive-grid-with-productive-neighbor-expansion-v1",
    }
    existing_by_iso2: dict[str, dict] = {}
    if resume and output_path.exists():
        existing = json.loads(output_path.read_text(encoding="utf-8"))
        if existing.get("scan_configuration") == scan_configuration:
            existing_by_iso2 = {
                item["iso2"].upper(): item for item in existing.get("countries", [])
            }

    results = []

    def build_report() -> dict:
        qualified = [result for result in results if result["qualified"]]
        continents = sorted({result["continent"] for result in qualified})
        complete = len(results) == len(candidates)
        passes = complete and (
            len(qualified) == len(results)
            if country_iso2
            else len(qualified) >= minimum_countries and len(continents) >= 5
        )
        return {
            "schema_version": 2,
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "scan_configuration": scan_configuration,
            "criteria": {
                "minimum_countries": minimum_countries,
                "minimum_continents": 5,
                "panoramas_per_country": target,
                "minimum_distance_km": 10.0,
            },
            "candidate_country_count": len(candidates),
            "completed_country_count": len(results),
            "qualified_country_count": len(qualified),
            "qualified_continents": continents,
            "passes": passes,
            "countries": results,
        }

    def write_report(report: dict) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = output_path.with_suffix(output_path.suffix + ".tmp")
        temporary_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        temporary_path.replace(output_path)

    for index, candidate in enumerate(candidates, start=1):
        prior = existing_by_iso2.get(candidate["iso2"].upper())
        if prior is not None:
            results.append(prior)
            print(f"[{index}/{len(candidates)}] resumed {candidate['country']}", flush=True)
            continue
        print(f"[{index}/{len(candidates)}] scanning {candidate['country']}...", flush=True)
        result = scan_country(
            candidate,
            token,
            max_tiles=max_tiles,
            target=target,
            boundaries=boundaries,
        )
        results.append(result)
        write_report(build_report())
        print(
            f"  separated panoramas: {result['separated_pano_sequences']} "
            f"in {result['tiles_scanned']} tile(s); qualified={result['qualified']}",
            flush=True,
        )
    report = build_report()
    write_report(report)
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Scan Mapillary panorama coverage by country")
    parser.add_argument("--candidates", type=Path, default=Path("data/country_candidates.json"))
    parser.add_argument("--output", type=Path, default=Path("data/coverage_scan.json"))
    parser.add_argument("--max-tiles", type=int, default=64)
    parser.add_argument("--target", type=int, default=15)
    parser.add_argument("--minimum-countries", type=int, default=30)
    parser.add_argument("--country")
    parser.add_argument(
        "--no-resume",
        dest="resume",
        action="store_false",
        help="discard a compatible partial report instead of resuming it",
    )
    parser.add_argument(
        "--boundary-filter",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = scan_all(
        args.candidates,
        args.output,
        max_tiles=args.max_tiles,
        target=args.target,
        minimum_countries=args.minimum_countries,
        country_iso2=args.country,
        resume=args.resume,
    )
    print(
        f"qualified={report['qualified_country_count']} "
        f"continents={len(report['qualified_continents'])} passes={report['passes']}"
    )
    return 0 if report["passes"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
