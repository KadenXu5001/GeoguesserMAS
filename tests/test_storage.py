from unittest.mock import MagicMock

import pytest

from geoguesser.storage import MongoRepository, geojson_point


def test_geojson_point_uses_longitude_latitude_order() -> None:
    assert geojson_point(13.75, 100.5) == {
        "type": "Point",
        "coordinates": [100.5, 13.75],
    }


@pytest.mark.parametrize(
    ("latitude", "longitude"),
    [(91, 0), (-91, 0), (0, 181), (0, -181)],
)
def test_geojson_point_rejects_invalid_coordinates(latitude, longitude) -> None:
    with pytest.raises(ValueError):
        geojson_point(latitude, longitude)


def test_initialize_creates_schema_indexes_and_pilot_version() -> None:
    database = MagicMock()
    database.list_collection_names.return_value = []

    MongoRepository(database).initialize()

    assert database.create_collection.call_count == 5
    database.panoramas.create_index.assert_any_call(
        [("mapillary_image_id", 1)], unique=True, name="uq_mapillary_image"
    )
    database.panoramas.create_index.assert_any_call(
        [("location", "2dsphere")], name="geo_location"
    )
    database.vision_analysis_cache.create_index.assert_called_once_with(
        [("source_id", 1), ("cache_version", 1)],
        name="source_cache_version",
    )
    update = database.dataset_versions.update_one.call_args
    assert update.args[0] == {"version": "pilot_v1"}
    assert update.kwargs["upsert"] is True


def test_seed_and_lookup_reference_rows() -> None:
    database = MagicMock()
    repository = MongoRepository(database)
    snapshot = {
        "version": "reference-v1",
        "retrieved_at": "2026-07-13",
        "rows": [
            {
                "category": "bollards",
                "country": "France",
                "indicator": "white with red reflector",
                "source_url": "https://geohints.com/meta/bollards",
            }
        ],
    }

    assert repository.seed_reference_snapshot(snapshot) == 1
    database.reference_rows.update_one.assert_called_once()
    database.reference_rows.find.return_value = [{"category": "bollards"}]
    assert repository.lookup_references(version="reference-v1", category="bollards") == [
        {"category": "bollards"}
    ]


def test_assign_validated_rejects_cross_split_sequence() -> None:
    database = MagicMock()
    database.panoramas.find_one.side_effect = [
        {
            "mapillary_image_id": "image-a",
            "sequence_id": "sequence-1",
            "location": geojson_point(48.85, 2.35),
        },
        {"mapillary_image_id": "image-b", "split": "evaluation"},
    ]

    with pytest.raises(ValueError, match="cannot cross"):
        MongoRepository(database).assign_validated(
            mapillary_image_id="image-a",
            country_iso2="FR",
            split="development",
            boundary_dataset="example-v1",
        )


def test_mark_downloaded_records_cloud_ready_object_reference() -> None:
    database = MagicMock()

    MongoRepository(database).mark_downloaded(
        "image-a",
        path=".local-data/source-private/objects/ab/abcdef.jpg",
        sha256="abcdef",
        byte_count=123,
        width=400,
        height=200,
        object_key="objects/ab/abcdef.jpg",
        storage_namespace="source-private",
        crc32c="4waSgw==",
        content_type="image/jpeg",
    )

    update = database.panoramas.update_one.call_args.args[1]["$set"]
    assert update["panorama_file"] == {
        "path": ".local-data/source-private/objects/ab/abcdef.jpg",
        "sha256": "abcdef",
        "byte_count": 123,
        "width": 400,
        "height": 200,
        "content_type": "image/jpeg",
        "object_key": "objects/ab/abcdef.jpg",
        "storage_namespace": "source-private",
        "crc32c": "4waSgw==",
    }
