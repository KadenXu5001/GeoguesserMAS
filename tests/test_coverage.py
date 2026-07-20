import mercantile
import pytest

from geoguesser.coverage import (
    CoveragePoint,
    _neighbor_tiles,
    _tile_coordinate_to_lnglat,
    candidate_tiles,
    scan_country,
    select_separated,
)


def point(sequence: str, latitude: float, longitude: float) -> CoveragePoint:
    return CoveragePoint(sequence, sequence, latitude, longitude, None, None)


def test_tile_coordinate_center_matches_tile_center() -> None:
    tile = mercantile.tile(-122.45, 37.75, 8)
    longitude, latitude = _tile_coordinate_to_lnglat(tile, 2048, 2048, 4096)
    bounds = mercantile.bounds(tile)
    assert bounds.west < longitude < bounds.east
    assert bounds.south < latitude < bounds.north


def test_separation_rejects_nearby_points() -> None:
    selected = select_separated(
        [
            point("a", 40.0, -75.0),
            point("b", 40.01, -75.0),
            point("c", 40.2, -75.0),
        ],
        minimum_distance_km=10,
        target=15,
    )
    assert [item.sequence_id for item in selected] == ["a", "c"]


def test_candidate_tiles_progressively_fill_deep_budget() -> None:
    tiles = candidate_tiles([-125.0, 25.0, -67.0, 49.0], zoom=8, max_tiles=64)

    assert len(tiles) == 64
    assert len({(tile.x, tile.y, tile.z) for tile in tiles}) == 64


def test_neighbor_tiles_are_unique_and_adjacent() -> None:
    origin = mercantile.Tile(x=100, y=100, z=8)
    neighbors = list(_neighbor_tiles(origin))

    assert len(neighbors) == 8
    assert len(set(neighbors)) == 8
    assert all(
        abs(tile.x - origin.x) <= 1 and abs(tile.y - origin.y) <= 1
        for tile in neighbors
    )


def test_deep_scan_requires_offline_boundaries() -> None:
    with pytest.raises(ValueError, match="pinned offline country boundaries"):
        scan_country(
            {
                "iso2": "FR",
                "country": "France",
                "continent": "Europe",
                "bbox": [-5.0, 42.0, 8.0, 51.0],
            },
            "token",
            boundaries=None,
        )
