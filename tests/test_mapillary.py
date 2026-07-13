from __future__ import annotations

from io import BytesIO
from unittest.mock import MagicMock

from PIL import Image

from geoguesser.mapillary import MapillaryClient


def jpeg_bytes(width: int = 400, height: int = 200) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (width, height), "green").save(buffer, format="JPEG")
    return buffer.getvalue()


def test_get_image_requests_required_fields_without_token_in_url() -> None:
    response = MagicMock(status_code=200)
    response.json.return_value = {"id": "123", "is_pano": True}
    session = MagicMock()
    session.headers = {}
    session.get.return_value = response

    result = MapillaryClient("secret", session=session).get_image("123")

    assert result["is_pano"] is True
    assert session.headers["Authorization"] == "OAuth secret"
    url = session.get.call_args.args[0]
    assert url == "https://graph.mapillary.com/123"
    assert "secret" not in url


def test_download_original_is_atomic_and_records_hash(tmp_path) -> None:
    content = jpeg_bytes()
    response = MagicMock(status_code=200)
    response.__enter__.return_value = response
    response.__exit__.return_value = False
    response.iter_content.return_value = [content]
    session = MagicMock()
    session.headers = {}
    session.get.return_value = response
    output = tmp_path / "panorama.jpg"

    downloaded = MapillaryClient("secret", session=session).download_original(
        {"thumb_original_url": "https://example.invalid/image"}, output
    )

    assert output.read_bytes() == content
    assert downloaded.width == 400
    assert downloaded.height == 200
    assert downloaded.byte_count == len(content)
    assert not (tmp_path / "panorama.jpg.part").exists()
