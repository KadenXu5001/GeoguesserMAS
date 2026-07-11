import mercantile

from geoguesser.coverage import CoveragePoint, _tile_coordinate_to_lnglat, select_separated


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
