from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


FORBIDDEN_METADATA_KEYS = frozenset(
    {
        "latitude",
        "longitude",
        "coordinates",
        "location",
        "captured_at",
        "timestamp",
        "sequence_id",
        "image_id",
        "mapillary_image_id",
        "panorama_path",
        "filename",
        "sha256",
        "country_iso2",
        "split",
    }
)


class ModelPayloadViolation(ValueError):
    """Raised when evaluation metadata crosses into a model-facing payload."""


def _walk(value: Any, path: str = "payload") -> list[str]:
    violations: list[str] = []
    if isinstance(value, Mapping):
        for key, child in value.items():
            key_text = str(key).lower()
            child_path = f"{path}.{key}"
            if key_text in FORBIDDEN_METADATA_KEYS:
                violations.append(child_path)
            violations.extend(_walk(child, child_path))
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, child in enumerate(value):
            violations.extend(_walk(child, f"{path}[{index}]"))
    return violations


def assert_model_payload_safe(payload: Any) -> None:
    violations = _walk(payload)
    if violations:
        joined = ", ".join(violations)
        raise ModelPayloadViolation(f"forbidden metadata in model payload: {joined}")

