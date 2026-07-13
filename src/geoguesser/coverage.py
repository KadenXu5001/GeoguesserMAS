from __future__ import annotations

import argparse
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
    seen: set[tuple[int, int, int]] = set()
    tiles: list[mercantile.Tile] = []
    for longitude, latitude in _grid_centers(bbox):
        tile = mercantile.tile(longitude, latitude, zoom)
        key = (tile.x, tile.y, tile.z)
        if key in seen:
            continue
        seen.add(key)
        tiles.append(tile)
        if len(tiles) >= max_tiles:
            break
    return tiles


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
    max_tiles: int = 12,
    target: int = 15,
    minimum_distance_km: float = 10.0,
    boundaries: CountryBoundaries | None = None,
) -> dict:
    selected: list[CoveragePoint] = []
    tiles_scanned = 0
    session = requests.Session()
    for tile in candidate_tiles(country["bbox"], zoom=zoom, max_tiles=max_tiles):
        points = [
            point
            for point in fetch_sequence_tile(session, token, tile)
            if _inside_bbox(point, country["bbox"])
            and (
                boundaries is None
                or boundaries.country_iso2(point.latitude, point.longitude)
                == country["iso2"].upper()
            )
        ]
        selected = select_separated(
            [*selected, *points],
            minimum_distance_km=minimum_distance_km,
            target=target,
        )
        tiles_scanned += 1
        if len(selected) >= target:
            break
    return {
        **country,
        "qualified": len(selected) >= target,
        "separated_pano_sequences": len(selected),
        "minimum_distance_km": minimum_distance_km,
        "tiles_scanned": tiles_scanned,
        "evidence": [asdict(point) for point in selected],
    }


def scan_all(
    candidates_path: Path,
    output_path: Path,
    *,
    max_tiles: int,
    target: int,
    country_iso2: str | None = None,
    boundary_filter: bool = False,
) -> dict:
    load_dotenv()
    token = os.environ.get("MAPILLARY_ACCESS_TOKEN")
    if not token:
        raise RuntimeError("MAPILLARY_ACCESS_TOKEN is required")
    boundaries = CountryBoundaries() if boundary_filter else None
    candidates = json.loads(candidates_path.read_text(encoding="utf-8"))
    if country_iso2:
        candidates = [
            candidate
            for candidate in candidates
            if candidate["iso2"].upper() == country_iso2.upper()
        ]
        if not candidates:
            raise ValueError(f"unknown country in candidates file: {country_iso2}")
    results = []
    for index, candidate in enumerate(candidates, start=1):
        print(f"[{index}/{len(candidates)}] scanning {candidate['country']}...", flush=True)
        result = scan_country(
            candidate,
            token,
            max_tiles=max_tiles,
            target=target,
            boundaries=boundaries,
        )
        results.append(result)
        print(
            f"  separated panoramas: {result['separated_pano_sequences']} "
            f"in {result['tiles_scanned']} tile(s); qualified={result['qualified']}",
            flush=True,
        )
    qualified = [result for result in results if result["qualified"]]
    continents = sorted({result["continent"] for result in qualified})
    passes = (
        len(qualified) == len(results)
        if country_iso2
        else len(qualified) >= 20 and len(continents) >= 5
    )
    report = {
        "schema_version": 1,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "criteria": {
            "minimum_countries": 20,
            "minimum_continents": 5,
            "panoramas_per_country": target,
            "minimum_distance_km": 10.0,
            "sequence_layer_zoom": 8,
        },
        "qualified_country_count": len(qualified),
        "qualified_continents": continents,
        "passes": passes,
        "countries": results,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Scan Mapillary panorama coverage by country")
    parser.add_argument("--candidates", type=Path, default=Path("data/country_candidates.json"))
    parser.add_argument("--output", type=Path, default=Path("data/coverage_scan.json"))
    parser.add_argument("--max-tiles", type=int, default=12)
    parser.add_argument("--target", type=int, default=15)
    parser.add_argument("--country")
    parser.add_argument("--boundary-filter", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = scan_all(
        args.candidates,
        args.output,
        max_tiles=args.max_tiles,
        target=args.target,
        country_iso2=args.country,
        boundary_filter=args.boundary_filter,
    )
    print(
        f"qualified={report['qualified_country_count']} "
        f"continents={len(report['qualified_continents'])} passes={report['passes']}"
    )
    return 0 if report["passes"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
