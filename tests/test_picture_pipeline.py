from pathlib import Path

from PIL import Image

from geoguesser.picture_pipeline import create_contact_sheet


def test_contact_sheet_combines_four_rendered_views(tmp_path) -> None:
    views = []
    for heading in (0, 90, 180, 270):
        path = tmp_path / f"h{heading}.jpg"
        Image.new("RGB", (64, 64), (heading % 255, 20, 30)).save(path)
        views.append({"heading": heading, "path": str(path), "sha256": "test"})

    output = create_contact_sheet(
        {"mapillary_image_id": "123", "rendered_views": views},
        tmp_path / "sheet.jpg",
    )

    assert output.exists()
    with Image.open(output) as image:
        assert image.size == (128, 208)
