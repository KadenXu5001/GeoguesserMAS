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
    result = extract_cardinal_views(client, views(tmp_path))

    assert isinstance(result, ExtractionOutput)
    assert len(client.models.calls) == 1
    assert len(client.models.calls[0]["contents"]) == 5


def test_retries_once_after_malformed_response(tmp_path: Path) -> None:
    client = Client([Response("not json"), Response(__import__("json").dumps(payload()))])
    result = extract_cardinal_views(client, views(tmp_path))

    assert result.schema_version == "extraction-v1"
    assert len(client.models.calls) == 2


def test_requires_four_cardinal_views(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="exactly four"):
        extract_cardinal_views(Client([]), {0: tmp_path / "missing.jpg"})

