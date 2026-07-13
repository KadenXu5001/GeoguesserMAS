from PIL import Image

from geoguesser.picture_pipeline import (
    create_contact_sheet,
    create_horizontal_strip,
    ingest_picture_candidates,
)


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


def test_horizontal_strip_orders_four_views(tmp_path) -> None:
    views = []
    for heading in (270, 0, 180, 90):
        path = tmp_path / f"strip-h{heading}.jpg"
        Image.new("RGB", (32, 24), (heading % 255, 40, 50)).save(path)
        views.append({"heading": heading, "path": str(path), "sha256": "test"})

    output = create_horizontal_strip(
        {"mapillary_image_id": "123", "rendered_views": views},
        tmp_path / "strip.jpg",
    )

    with Image.open(output) as image:
        assert image.size == (128, 64)


def test_ingest_skips_rejected_candidates(tmp_path) -> None:
    coverage = tmp_path / "coverage.json"
    coverage.write_text(
        """
        {
          "countries": [
            {
              "iso2": "FR",
              "evidence": [
                {"image_id": "already-rejected", "sequence_id": "seq-1"}
              ]
            }
          ]
        }
        """,
        encoding="utf-8",
    )

    class Repository:
        def get_panorama(self, image_id):
            assert image_id == "already-rejected"
            return {"status": "rejected"}

    class UnusedMapillary:
        def get_image(self, image_id):
            raise AssertionError("rejected candidates should not be fetched again")

    counts = ingest_picture_candidates(
        Repository(),
        UnusedMapillary(),
        boundaries=None,
        coverage_path=coverage,
    )

    assert counts == {
        "examined": 0,
        "rendered": 0,
        "rejected": 0,
        "failed": 0,
        "skipped": 1,
    }
