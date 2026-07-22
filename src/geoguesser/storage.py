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
                "enum": [
                    "candidate",
                    "validated",
                    "rejected",
                    "downloaded",
                    "quality_review",
                    "rendered",
                ]
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

REFERENCE_VALIDATOR = {
    "$jsonSchema": {
        "bsonType": "object",
        "required": ["version", "category", "indicator", "source_url", "retrieved_at"],
        "properties": {
            "version": {"bsonType": "string", "minLength": 1},
            "category": {"bsonType": "string", "minLength": 1},
            "country": {"bsonType": ["string", "null"]},
            "indicator": {"bsonType": "string", "minLength": 1},
            "source_url": {"bsonType": "string", "minLength": 1},
            "retrieved_at": {"bsonType": "string", "minLength": 1},
        },
    }
}

REFERENCE_UNIQUE_INDEX = [
    ("version", ASCENDING),
    ("category", ASCENDING),
    ("country", ASCENDING),
    ("indicator", ASCENDING),
    ("source_url", ASCENDING),
]

VISION_ANALYSIS_CACHE_VALIDATOR = {
    "$jsonSchema": {
        "bsonType": "object",
        "required": [
            "_id", "cache_version", "source_id", "view_hashes", "payload",
            "created_at", "updated_at",
        ],
        "properties": {
            "_id": {"bsonType": "string", "minLength": 64, "maxLength": 64},
            "cache_version": {"bsonType": "string", "minLength": 1},
            "source_id": {"bsonType": "string", "minLength": 1},
            "view_hashes": {
                "bsonType": "array",
                "minItems": 4,
                "maxItems": 4,
                "items": {"bsonType": ["string", "null"]},
            },
            "payload": {
                "bsonType": "object",
                "required": ["analysis", "informedEvidence", "predictedCountry"],
                "properties": {
                    "analysis": {"bsonType": "object"},
                    "informedEvidence": {"bsonType": "array"},
                    "predictedCountry": {"bsonType": "string", "minLength": 1},
                },
            },
            "created_at": {"bsonType": "date"},
            "updated_at": {"bsonType": "date"},
        },
    }
}

ACTIVE_ROUND_VALIDATOR = {
    "$jsonSchema": {
        "bsonType": "object",
        "required": [
            "_id", "owner_id", "panorama", "answered", "created_at", "expires_at",
        ],
        "properties": {
            "_id": {"bsonType": "string", "minLength": 36, "maxLength": 36},
            "owner_id": {"bsonType": "string", "minLength": 1, "maxLength": 128},
            "panorama": {"bsonType": "object"},
            "answered": {"bsonType": "bool"},
            "result": {"bsonType": ["object", "null"]},
            "created_at": {"bsonType": "date"},
            "expires_at": {"bsonType": "date"},
        },
    }
}

REQUEST_LIMIT_VALIDATOR = {
    "$jsonSchema": {
        "bsonType": "object",
        "required": ["_id", "count", "expires_at"],
        "properties": {
            "_id": {"bsonType": "string", "minLength": 1, "maxLength": 256},
            "count": {"bsonType": ["int", "long"]},
            "expires_at": {"bsonType": "date"},
        },
    }
}

RUNTIME_BUDGET_VALIDATOR = {
    "$jsonSchema": {
        "bsonType": "object",
        "required": ["_id", "spent_usd", "reserved_usd", "expires_at"],
        "properties": {
            "_id": {"bsonType": "string", "minLength": 7, "maxLength": 7},
            "spent_usd": {"bsonType": ["double", "int", "long", "decimal"]},
            "reserved_usd": {"bsonType": ["double", "int", "long", "decimal"]},
            "expires_at": {"bsonType": "date"},
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
        self._ensure_collection("reference_rows", REFERENCE_VALIDATOR)
        self._ensure_collection("vision_analysis_cache", VISION_ANALYSIS_CACHE_VALIDATOR)
        self._ensure_collection("active_rounds", ACTIVE_ROUND_VALIDATOR)
        self._ensure_collection("request_limits", REQUEST_LIMIT_VALIDATOR)
        self._ensure_collection("runtime_budgets", RUNTIME_BUDGET_VALIDATOR)

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
        self.database.reference_rows.create_index(
            [("version", ASCENDING), ("category", ASCENDING), ("country", ASCENDING)],
            name="reference_category_country",
        )
        reference_indexes = self.database.reference_rows.index_information()
        existing_unique = (
            reference_indexes.get("uq_reference_row")
            if isinstance(reference_indexes, Mapping)
            else None
        )
        if existing_unique and list(existing_unique.get("key", [])) != REFERENCE_UNIQUE_INDEX:
            self.database.reference_rows.drop_index("uq_reference_row")
        self.database.reference_rows.create_index(
            REFERENCE_UNIQUE_INDEX, unique=True, name="uq_reference_row"
        )
        self.database.vision_analysis_cache.create_index(
            [("source_id", ASCENDING), ("cache_version", ASCENDING)],
            name="source_cache_version",
        )
        self.database.active_rounds.create_index(
            [("expires_at", ASCENDING)], expireAfterSeconds=0, name="expire_active_rounds"
        )
        self.database.active_rounds.create_index(
            [("owner_id", ASCENDING), ("created_at", ASCENDING)], name="owner_round_history"
        )
        self.database.request_limits.create_index(
            [("expires_at", ASCENDING)], expireAfterSeconds=0, name="expire_request_limits"
        )
        self.database.runtime_budgets.create_index(
            [("expires_at", ASCENDING)], expireAfterSeconds=0, name="expire_runtime_budgets"
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

    def register_dataset(self, document: Mapping[str, Any]) -> None:
        version = str(document.get("version", ""))
        countries = document.get("countries")
        if not version or not isinstance(countries, list) or not countries:
            raise ValueError("dataset document must include version and countries")
        now = utc_now()
        self.database.dataset_versions.update_one(
            {"version": version},
            {
                "$set": {**dict(document), "updated_at": now},
                "$setOnInsert": {"created_at": now},
            },
            upsert=True,
        )

    def attach_object_store_assets(
        self,
        image_id: str,
        *,
        panorama_object: Mapping[str, Any],
        view_objects: list[Mapping[str, Any]],
        migration_version: str,
    ) -> None:
        panorama = self.get_panorama(image_id)
        if panorama is None:
            raise ValueError(f"cannot migrate unknown panorama: {image_id}")
        panorama_file = dict(panorama.get("panorama_file") or {})
        if panorama_file.get("sha256") != panorama_object.get("sha256"):
            raise ValueError(f"panorama checksum changed before migration: {image_id}")
        panorama_file.update(dict(panorama_object))

        existing_views = {
            int(view["heading"]): dict(view)
            for view in panorama.get("rendered_views", [])
        }
        migrated_views = {int(view["heading"]): dict(view) for view in view_objects}
        if set(existing_views) != {0, 90, 180, 270} or set(migrated_views) != {
            0,
            90,
            180,
            270,
        }:
            raise ValueError(f"panorama does not have four migration views: {image_id}")
        merged_views = []
        for heading in (0, 90, 180, 270):
            if existing_views[heading].get("sha256") != migrated_views[heading].get(
                "sha256"
            ):
                raise ValueError(
                    f"rendered view checksum changed before migration: {image_id}/{heading}"
                )
            merged_views.append({**existing_views[heading], **migrated_views[heading]})

        self.database.panoramas.update_one(
            {"mapillary_image_id": image_id},
            {
                "$set": {
                    "provider": "mapillary",
                    "provider_image_id": image_id,
                    "provider_sequence_id": panorama["sequence_id"],
                    "panorama_file": panorama_file,
                    "rendered_views": merged_views,
                    "storage_migration": {
                        "version": migration_version,
                        "status": "complete",
                        "migrated_at": utc_now(),
                    },
                    "updated_at": utc_now(),
                }
            },
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
                "status": {
                    "$in": ["validated", "downloaded", "quality_review", "rendered"]
                },
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

    def reject(self, mapillary_image_id: str, reason: str) -> None:
        self.database.panoramas.update_one(
            {"mapillary_image_id": mapillary_image_id},
            {
                "$set": {
                    "status": "rejected",
                    "rejection_reason": reason,
                    "updated_at": utc_now(),
                }
            },
        )

    def mark_downloaded(
        self,
        mapillary_image_id: str,
        *,
        path: str,
        sha256: str,
        byte_count: int,
        width: int,
        height: int,
        object_key: str | None = None,
        storage_namespace: str | None = None,
        crc32c: str | None = None,
        content_type: str = "application/octet-stream",
        storage_country_iso2: str | None = None,
        storage_subdivision_code: str | None = None,
    ) -> None:
        panorama_file = {
            "path": path,
            "sha256": sha256,
            "byte_count": byte_count,
            "width": width,
            "height": height,
            "content_type": content_type,
        }
        for key, value in (
            ("object_key", object_key),
            ("storage_namespace", storage_namespace),
            ("crc32c", crc32c),
            ("country_iso2", storage_country_iso2),
            ("subdivision_code", storage_subdivision_code),
        ):
            if value is not None:
                panorama_file[key] = str(value)
        self.database.panoramas.update_one(
            {"mapillary_image_id": mapillary_image_id},
            {
                "$set": {
                    "status": "downloaded",
                    "panorama_file": panorama_file,
                    "updated_at": utc_now(),
                }
            },
        )

    def mark_rendered(
        self,
        mapillary_image_id: str,
        views: list[Mapping[str, Any]],
    ) -> None:
        self.database.panoramas.update_one(
            {"mapillary_image_id": mapillary_image_id},
            {
                "$set": {
                    "status": "quality_review",
                    "rendered_views": [dict(view) for view in views],
                    "updated_at": utc_now(),
                }
            },
        )

    def record_quality(self, mapillary_image_id: str, assessment: Mapping[str, Any]) -> None:
        automatic_pass = bool(assessment.get("automatic_pass"))
        panorama = self.get_panorama(mapillary_image_id)
        update: dict[str, Any] = {
            "quality": dict(assessment),
            "updated_at": utc_now(),
        }
        if not automatic_pass:
            update["status"] = "rejected"
            update["rejection_reason"] = "; ".join(
                assessment.get("rejection_reasons", ["automatic quality failure"])
            )
        elif panorama and panorama.get("rendered_views"):
            update["status"] = "quality_review"
        self.database.panoramas.update_one(
            {"mapillary_image_id": mapillary_image_id}, {"$set": update}
        )

    def review_quality(
        self,
        mapillary_image_id: str,
        *,
        approved: bool,
        notes: str,
    ) -> None:
        panorama = self.get_panorama(mapillary_image_id)
        if panorama is None:
            raise ValueError("panorama does not exist")
        if not panorama.get("quality", {}).get("automatic_pass"):
            raise ValueError("panorama did not pass automatic quality checks")
        self.database.panoramas.update_one(
            {"mapillary_image_id": mapillary_image_id},
            {
                "$set": {
                    "quality.manual_review": {
                        "status": "approved" if approved else "rejected",
                        "notes": notes,
                        "reviewed_at": utc_now(),
                    },
                    "status": "rendered" if approved else "rejected",
                    "rejection_reason": None if approved else f"manual quality review: {notes}",
                    "updated_at": utc_now(),
                }
            },
        )

    def list_panoramas(
        self,
        *,
        country_iso2: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        query: dict[str, Any] = {}
        if country_iso2:
            query["country_iso2"] = country_iso2.upper()
        if status:
            query["status"] = status
        return list(
            self.database.panoramas.find(query).sort(
                [("country_iso2", ASCENDING), ("split", ASCENDING), ("mapillary_image_id", ASCENDING)]
            )
        )

    def get_panorama(self, mapillary_image_id: str) -> dict[str, Any] | None:
        return self.database.panoramas.find_one(
            {"mapillary_image_id": mapillary_image_id}
        )

    def seed_reference_snapshot(self, snapshot: Mapping[str, Any]) -> int:
        version = str(snapshot.get("version", ""))
        retrieved_at = str(snapshot.get("retrieved_at", ""))
        rows = snapshot.get("rows", [])
        if not version or not retrieved_at or not isinstance(rows, list):
            raise ValueError("reference snapshot must include version, retrieved_at, and rows")
        self.database.reference_rows.delete_many({"version": version})
        seeded = 0
        for row in rows:
            document = {
                "version": version,
                "category": str(row["category"]),
                "country": row.get("country"),
                "indicator": str(row["indicator"]),
                "source_url": str(row["source_url"]),
                "retrieved_at": retrieved_at,
            }
            for optional in (
                "family",
                "description",
                "source_name",
                "source_section",
                "image_evidence",
                "confidence",
            ):
                if optional in row:
                    document[optional] = row[optional]
            self.database.reference_rows.update_one(
                {
                    "version": version,
                    "category": document["category"],
                    "country": document["country"],
                    "indicator": document["indicator"],
                    "source_url": document["source_url"],
                },
                {"$set": document},
                upsert=True,
            )
            seeded += 1
        return seeded

    def lookup_references(
        self,
        *,
        version: str,
        category: str,
        country: str | None = None,
    ) -> list[dict[str, Any]]:
        query: dict[str, Any] = {"version": version, "category": category}
        if country is not None:
            query["country"] = {"$regex": f"^{country}$", "$options": "i"}
        return list(self.database.reference_rows.find(query, {"_id": 0}))
