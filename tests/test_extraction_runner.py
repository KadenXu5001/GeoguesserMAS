from pathlib import Path

import pytest

from geoguesser.extraction import ExtractionOutput
from geoguesser.extraction_runner import extract_cardinal_views


def category() -> dict:
    return {"status": "not_detected", "objects": [], "signal": "No usable signal."}


def payload() -> dict:
    return {
        "driving_side_and_markings": category(),
        "signs_and_language": category(),
        "vehicles_and_plates": category(),
        "infrastructure": category(),
        "terrain_vegetation_and_climate": category(),
        "architecture_and_settlement": category(),
    }


class Response:
    def __init__(self, text: str):
        self.text = text
        self.parsed = None


class InvalidSchemaModels:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        if len(self.calls) == 1:
            raise RuntimeError("400 INVALID_ARGUMENT schema rejected")
        return self.response


class Models:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        return next(self.responses)


class Client:
    def __init__(self, responses):
        self.models = Models(responses)


def views(tmp_path: Path) -> dict[int, Path]:
    from PIL import Image

    paths = {}
    for heading in (0, 90, 180, 270):
        path = tmp_path / f"view-{heading}.jpg"
        Image.new("RGB", (16, 16), "black").save(path)
        paths[heading] = path
    return paths


def test_sends_all_four_views_in_one_call_and_parses_schema(tmp_path: Path) -> None:
    client = Client([Response(__import__("json").dumps(payload()))])
    view_paths = views(tmp_path)
    result = extract_cardinal_views(client, view_paths)

    assert isinstance(result, ExtractionOutput)
    assert len(client.models.calls) == 1
    assert len(client.models.calls[0]["contents"]) == 9
    assert client.models.calls[0]["contents"][0].startswith(
        "The next image is the cardinal view at heading 0 degrees"
    )
    image_part = client.models.calls[0]["contents"][1]
    assert image_part.inline_data.mime_type == "image/jpeg"
    assert image_part.inline_data.data == view_paths[0].read_bytes()
    assert client.models.calls[0]["contents"][2].startswith(
        "The next image is the cardinal view at heading 90 degrees"
    )
    schema = client.models.calls[0]["config"].response_schema
    assert "$defs" not in str(schema)
    assert "$ref" not in str(schema)
    heading_schema = schema["properties"]["driving_side_and_markings"]["properties"]["objects"]["items"]["properties"]["heading"]
    assert heading_schema["type"] == "integer"
    assert "enum" not in heading_schema
    category_schema = schema["properties"]["signs_and_language"]
    assert category_schema["properties"]["status"]["enum"] == [
        "not_present",
        "not_detected",
        "present_but_illegible",
        "present",
    ]
    legibility_schema = category_schema["properties"]["objects"]["items"]["properties"]["legibility"]
    assert legibility_schema["enum"] == [
        "clear",
        "partial",
        "illegible",
        "not_applicable",
    ]


def test_malformed_response_is_not_retried(tmp_path: Path) -> None:
    client = Client([Response("not json")])
    with pytest.raises(Exception):
        extract_cardinal_views(client, views(tmp_path))
    assert len(client.models.calls) == 1


def test_provider_schema_failure_is_not_retried_with_json_fallback(tmp_path: Path) -> None:
    client = type("Client", (), {})()
    client.models = InvalidSchemaModels(Response(__import__("json").dumps(payload())))
    with pytest.raises(RuntimeError):
        extract_cardinal_views(client, views(tmp_path))
    assert client.models.calls[0]["config"].response_schema is not None
    assert len(client.models.calls) == 1


def test_normalizes_known_provider_aliases_before_validation(tmp_path: Path) -> None:
    value = payload()
    value["schema_version"] = "1.0.0"
    value["driving_side_and_markings"]["objects"] = [
        {
            "heading": 0,
            "observation": "road",
            "confidence": 80,
            "legibility": "legible",
        }
    ]
    client = Client([Response(__import__("json").dumps(value))])
    result = extract_cardinal_views(client, views(tmp_path))
    assert result.schema_version == "extraction-v1"
    assert result.driving_side_and_markings.objects[0].legibility == "clear"


def test_normalizes_category_status_used_as_object_legibility(tmp_path: Path) -> None:
    value = payload()
    value["signs_and_language"] = {
        "status": "present_but_illegible",
        "signal": "Text is visible but cannot be read.",
        "objects": [
            {
                "heading": 90,
                "observation": "distant road sign",
                "confidence": 75,
                "legibility": "present_but_illegible",
            }
        ],
    }
    client = Client([Response(__import__("json").dumps(value))])

    result = extract_cardinal_views(client, views(tmp_path))

    assert result.signs_and_language.status == "present_but_illegible"
    assert result.signs_and_language.objects[0].legibility == "illegible"
    assert len(client.models.calls) == 1


def test_reports_usage_for_the_single_extraction_call(tmp_path: Path) -> None:
    response = Response(__import__("json").dumps(payload()))
    response.usage_metadata = {"prompt_token_count": 11, "candidates_token_count": 3}
    events = []
    extract_cardinal_views(
        Client([response]),
        views(tmp_path),
        usage_callback=lambda response, latency: events.append(response),
    )
    assert len(events) == 1


def test_requires_four_cardinal_views(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="exactly four"):
        extract_cardinal_views(Client([]), {0: tmp_path / "missing.jpg"})


def test_rejects_attempt_count_other_than_one(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="single-call"):
        extract_cardinal_views(Client([]), views(tmp_path), max_attempts=2)
