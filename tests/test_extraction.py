import pytest
from pydantic import ValidationError

from geoguesser.extraction import ExtractionOutput, NormalizedBox


def category(status: str = "not_detected") -> dict:
    return {"status": status, "objects": [], "signal": "No usable signal."}


def test_extraction_schema_accepts_all_required_categories() -> None:
    result = ExtractionOutput(
        driving_side_and_markings=category(),
        signs_and_language=category("present_but_illegible"),
        vehicles_and_plates=category(),
        infrastructure=category("present"),
        terrain_vegetation_and_climate=category("present"),
        architecture_and_settlement=category(),
    )

    assert result.schema_version == "extraction-v1"
    assert result.signs_and_language.status == "present_but_illegible"


def test_bbox_uses_documented_order_and_rejects_zero_area() -> None:
    assert NormalizedBox(ymin=100, xmin=200, ymax=500, xmax=800).model_dump() == {
        "ymin": 100,
        "xmin": 200,
        "ymax": 500,
        "xmax": 800,
    }
    with pytest.raises(ValidationError):
        NormalizedBox(ymin=100, xmin=200, ymax=100, xmax=800)

