from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Mapping

from pymongo import ASCENDING, GEOSPHERE, MongoClient
from pymongo.database import Database

from geoguesser.pilot import MINIMUM_SEPARATION_METERS, pilot_dataset_document


PANORAMA_VALIDATOR = {
    "$jsonSchema": {
        "bsonType": "object",
        "required": ["mapillary_image_id", "sequence_id", "location", "status"],
        "properties": {
            "mapillary_image_id": {"bsonType": "string", "minLength": 1},
            "sequence_id": {"bsonType": "string", "minLength": 1},
            "location": {
                "bsonType": "object",
                "required": ["type", "coordinates"],
                "properties": {
                    "type": {"enum": ["Point"]},
                    "coordinates": {
                        "bsonType": "array",
                        "minItems": 2,
                        "maxItems": 2,
                    },
                },
            },
            "split": {"enum": ["development", "evaluation", None]},
            "status": {
                "enum": ["candidate", "validated", "rejected", "downloaded", "rendered"]
            },
        },
    }
}

DATASET_VALIDATOR = {
    "$jsonSchema": {
        "bsonType": "object",
        "required": ["version", "kind", "status", "countries", "targets", "constraints"],
        "properties": {
            "version": {"bsonType": "string", "minLength": 1},
            "status": {"enum": ["draft", "frozen", "retired"]},
        },
    }
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def geojson_point(latitude: float, longitude: float) -> dict[str, Any]:
    if not -90 <= latitude <= 90:
        raise ValueError("latitude must be in [-90, 90]")
    if not -180 <= longitude <= 180:
        raise ValueError("longitude must be in [-180, 180]")
    return {"type": "Point", "coordinates": [longitude, latitude]}


def connect_database(
    uri: str | None = None,
    database_name: str | None = None,
) -> tuple[MongoClient, Database]:
    client = MongoClient(
        uri or os.environ.get("MONGODB_URI", "mongodb://localhost:27017"),
        serverSelectionTimeoutMS=5_000,
    )
    database = client[database_name or os.environ.get("MONGODB_DATABASE", "geoguesser")]
    return client, database


class MongoRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def initialize(self) -> None:
        self._ensure_collection("panoramas", PANORAMA_VALIDATOR)
        self._ensure_collection("dataset_versions", DATASET_VALIDATOR)
        self._ensure_collection("ingestion_attempts", None)

        self.database.panoramas.create_index(
            [("mapillary_image_id", ASCENDING)], unique=True, name="uq_mapillary_image"
        )
        self.database.panoramas.create_index(
            [("location", GEOSPHERE)], name="geo_location"
        )
        self.database.panoramas.create_index(
            [("country_iso2", ASCENDING), ("split", ASCENDING)],
            name="country_split",
        )
        self.database.panoramas.create_index(
            [("sequence_id", ASCENDING), ("split", ASCENDING)],
            name="sequence_split",
        )
        self.database.dataset_versions.create_index(
            [("version", ASCENDING)], unique=True, name="uq_dataset_version"
        )
        self.database.ingestion_attempts.create_index(
            [("mapillary_image_id", ASCENDING), ("created_at", ASCENDING)],
            name="image_attempt_history",
        )

        pilot = pilot_dataset_document()
        self.database.dataset_versions.update_one(
            {"version": pilot["version"]},
            {"$setOnInsert": {**pilot, "created_at": utc_now()}},
            upsert=True,
        )

    def _ensure_collection(self, name: str, validator: Mapping | None) -> None:
        options = {"validator": dict(validator)} if validator else {}
        if name not in self.database.list_collection_names():
            self.database.create_collection(name, **options)
            return
        if validator:
            self.database.command("collMod", name, **options)

    def record_candidate(
        self,
        *,
        mapillary_image_id: str,
        sequence_id: str,
        latitude: float,
        longitude: float,
        source: Mapping[str, Any] | None = None,
    ) -> None:
        now = utc_now()
        self.database.panoramas.update_one(
            {"mapillary_image_id": mapillary_image_id},
            {
                "$set": {
                    "sequence_id": sequence_id,
                    "location": geojson_point(latitude, longitude),
                    "source": dict(source or {}),
                    "updated_at": now,
                },
                "$setOnInsert": {
                    "status": "candidate",
                    "split": None,
                    "created_at": now,
                },
            },
            upsert=True,
        )

    def assign_validated(
        self,
        *,
        mapillary_image_id: str,
        country_iso2: str,
        split: str,
        boundary_dataset: str,
    ) -> None:
        if split not in {"development", "evaluation"}:
            raise ValueError("split must be development or evaluation")
        panorama = self.database.panoramas.find_one(
            {"mapillary_image_id": mapillary_image_id}
        )
        if panorama is None:
            raise ValueError("candidate panorama does not exist")

        conflict = self.database.panoramas.find_one(
            {
                "sequence_id": panorama["sequence_id"],
                "split": {"$nin": [None, split]},
                "mapillary_image_id": {"$ne": mapillary_image_id},
            }
        )
        if conflict:
            raise ValueError("Mapillary sequence cannot cross dataset splits")

        nearby = self.database.panoramas.find_one(
            {
                "mapillary_image_id": {"$ne": mapillary_image_id},
                "country_iso2": country_iso2,
                "status": {"$in": ["validated", "downloaded", "rendered"]},
                "location": {
                    "$near": {
                        "$geometry": panorama["location"],
                        "$maxDistance": MINIMUM_SEPARATION_METERS,
                    }
                },
            }
        )
        if nearby:
            raise ValueError("panorama is within 10 km of an already retained panorama")

        self.database.panoramas.update_one(
            {"mapillary_image_id": mapillary_image_id},
            {
                "$set": {
                    "country_iso2": country_iso2,
                    "split": split,
                    "ground_truth": {
                        "method": "offline_boundaries",
                        "dataset": boundary_dataset,
                    },
                    "status": "validated",
                    "updated_at": utc_now(),
                }
            },
        )

    def record_attempt(
        self,
        mapillary_image_id: str,
        operation: str,
        outcome: str,
        detail: str | None = None,
    ) -> None:
        self.database.ingestion_attempts.insert_one(
            {
                "mapillary_image_id": mapillary_image_id,
                "operation": operation,
                "outcome": outcome,
                "detail": detail,
                "created_at": utc_now(),
            }
        )
