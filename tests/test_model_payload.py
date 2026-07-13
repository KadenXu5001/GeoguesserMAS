import pytest

from geoguesser.model_payload import ModelPayloadViolation, assert_model_payload_safe


def test_structured_extraction_payload_is_safe() -> None:
    assert_model_payload_safe(
        {
            "views": [
                {"heading": 0, "objects": [{"label": "road sign"}]},
                {"heading": 90, "objects": []},
            ],
            "question": "Which visible clues distinguish likely countries?",
        }
    )


@pytest.mark.parametrize(
    "key",
    [
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
    ],
)
def test_rejects_forbidden_metadata_at_any_nesting_level(key: str) -> None:
    with pytest.raises(ModelPayloadViolation, match=key):
        assert_model_payload_safe({"extraction": [{"details": {key: "secret"}}]})

