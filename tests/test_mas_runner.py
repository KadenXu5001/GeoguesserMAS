import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from geoguesser.extraction import ExtractionOutput
from geoguesser.mas_runner import build_agent_input
from geoguesser.model_payload import ModelPayloadViolation


def test_agent_input_contains_extraction_only() -> None:
    extraction = ExtractionOutput.model_validate(
        {
            "driving_side_and_markings": {"status": "present", "signal": "right", "objects": []},
            "signs_and_language": {"status": "not_detected", "signal": "", "objects": []},
            "vehicles_and_plates": {"status": "not_detected", "signal": "", "objects": []},
            "infrastructure": {"status": "not_detected", "signal": "", "objects": []},
            "terrain_vegetation_and_climate": {"status": "not_detected", "signal": "", "objects": []},
            "architecture_and_settlement": {"status": "not_detected", "signal": "", "objects": []},
        }
    )
    payload = build_agent_input(extraction)
    text = payload["messages"][0]["content"]
    assert "mapillary_image_id" not in text
    assert "filename" not in text
    assert "right" in text


def test_payload_audit_rejects_metadata_if_added_to_extraction() -> None:
    extraction = SimpleNamespace(model_dump=lambda: {"location": "secret"})
    with pytest.raises(ModelPayloadViolation):
        build_agent_input(extraction)  # type: ignore[arg-type]
