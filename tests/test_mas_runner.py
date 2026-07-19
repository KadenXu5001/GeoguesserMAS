import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from geoguesser.extraction import ExtractionOutput
from geoguesser.mas_runner import build_agent_input, build_informed_evidence, run_mas_row
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


def test_informed_evidence_uses_final_text_and_exact_lookup_object() -> None:
    extraction = {
        "schema_version": "extraction-v1",
        "infrastructure": {
            "objects": [{
                "heading": 90,
                "bbox": {"ymin": 100, "xmin": 200, "ymax": 600, "xmax": 400},
                "observation": "black-backed Brazilian roadside bollard",
            }]
        },
    }
    result = build_informed_evidence(
        {"evidence": ["A Brazilian-style roadside bollard is a strong country clue."]},
        extraction,
        [{
            "tool": "lookup_universal_clues",
            "category": "bollards",
            "object_observation": "black-backed Brazilian roadside bollard",
        }],
    )

    assert result == [{
        "id": "informed-1",
        "description": "A Brazilian-style roadside bollard is a strong country clue.",
        "tool": "lookup_universal_clues",
        "lookupCategory": "bollards",
        "category": "infrastructure",
        "heading": 90,
        "bbox": {"ymin": 100, "xmin": 200, "ymax": 600, "xmax": 400},
        "observation": "black-backed Brazilian roadside bollard",
    }]


def test_payload_audit_rejects_metadata_if_added_to_extraction() -> None:
    extraction = SimpleNamespace(model_dump=lambda: {"location": "secret"})
    with pytest.raises(ModelPayloadViolation):
        build_agent_input(extraction)  # type: ignore[arg-type]


class _ResultAgent:
    def __init__(self, result: dict, context_prediction: dict | None = None) -> None:
        self.result = result
        self.context_prediction = context_prediction

    def invoke(self, _payload, *, context, config=None):
        if self.context_prediction is not None:
            context["final_prediction"] = self.context_prediction
        return self.result


def _row() -> dict[str, str]:
    return {
        "view_h000_path": "0.jpg",
        "view_h090_path": "90.jpg",
        "view_h180_path": "180.jpg",
        "view_h270_path": "270.jpg",
    }


def test_run_mas_row_accepts_prediction_committed_by_terminal_emit_context() -> None:
    prediction = {
        "country": "France",
        "confidence": 80,
        "alternatives": ["Belgium"],
        "evidence": ["French road markings"],
    }

    result = run_mas_row(
        _row(),
        gemini_client=object(),
        reference_repository=object(),
        reference_version="v1",
        agent=_ResultAgent({"messages": []}, context_prediction=prediction),
    )

    assert result["prediction"] == prediction


def test_run_mas_row_reports_extraction_failure_instead_of_emit_error() -> None:
    agent = _ResultAgent({
        "extraction_status": "failed",
        "extraction_metrics": {
            "status": "failed",
            "error": "provider returned malformed extraction JSON",
        },
        "messages": [],
    })

    with pytest.raises(RuntimeError, match="visual extraction failed.*malformed extraction JSON"):
        run_mas_row(
            _row(),
            gemini_client=object(),
            reference_repository=object(),
            reference_version="v1",
            agent=agent,
        )
