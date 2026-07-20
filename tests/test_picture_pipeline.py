import hashlib
from types import SimpleNamespace

from PIL import Image

from geoguesser import picture_pipeline
from geoguesser.mapillary import DownloadedImage
from geoguesser.object_store import RUNTIME_PRIVATE, SOURCE_PRIVATE, LocalObjectStore
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


def test_ingest_writes_cloud_ready_content_addressed_assets(tmp_path, monkeypatch) -> None:
    coverage = tmp_path / "coverage.json"
    coverage.write_text(
        """
        {
          "countries": [
            {
              "iso2": "FR",
              "evidence": [{"image_id": "image-1", "sequence_id": "seq-1"}]
            }
          ]
        }
        """,
        encoding="utf-8",
    )

    class Repository:
        def __init__(self):
            self.downloaded = None
            self.views = None

        def get_panorama(self, image_id):
            return None

        def record_attempt(self, *args):
            pass

        def record_candidate(self, **kwargs):
            pass

        def assign_validated(self, **kwargs):
            pass

        def mark_downloaded(self, image_id, **kwargs):
            self.downloaded = kwargs

        def record_quality(self, *args):
            pass

        def mark_rendered(self, image_id, views):
            self.views = views

        def reject(self, *args):
            raise AssertionError("valid fixture must not be rejected")

    class Mapillary:
        def get_image(self, image_id):
            return {
                "id": image_id,
                "is_pano": True,
                "computed_geometry": {"type": "Point", "coordinates": [2.35, 48.85]},
                "sequence": {"id": "seq-1"},
            }

        def download_original(self, metadata, output_path):
            output_path.parent.mkdir(parents=True, exist_ok=True)
            Image.new("RGB", (400, 200), "green").save(output_path, format="JPEG")
            content = output_path.read_bytes()
            return DownloadedImage(
                output_path,
                hashlib.sha256(content).hexdigest(),
                len(content),
                400,
                200,
            )

    class Boundaries:
        dataset_id = "boundaries-v1"

        def country_iso2(self, latitude, longitude):
            return "FR"

    def render_views(source, output_dir):
        output_dir.mkdir(parents=True, exist_ok=True)
        paths = []
        for heading in (0, 90, 180, 270):
            path = output_dir / f"h{heading:03d}.jpg"
            Image.new("RGB", (32, 32), (heading % 255, 20, 30)).save(path)
            paths.append(path)
        return paths

    monkeypatch.setattr(
        picture_pipeline,
        "assess_panorama",
        lambda path: SimpleNamespace(
            automatic_pass=True,
            rejection_reasons=(),
            as_document=lambda: {"automatic_pass": True},
        ),
    )
    monkeypatch.setattr(picture_pipeline, "render_cardinal_views", render_views)
    repository = Repository()
    store = LocalObjectStore(tmp_path / "store")

    counts = ingest_picture_candidates(
        repository,
        Mapillary(),
        Boundaries(),
        limit=1,
        coverage_path=coverage,
        object_store=store,
    )

    assert counts["rendered"] == 1
    assert repository.downloaded["storage_namespace"] == SOURCE_PRIVATE
    assert repository.downloaded["object_key"].startswith("countries/FR/objects/")
    assert repository.downloaded["storage_country_iso2"] == "FR"
    assert repository.downloaded["crc32c"]
    assert len(repository.views) == 4
    assert {view["storage_namespace"] for view in repository.views} == {
        RUNTIME_PRIVATE
    }
    assert {view["country_iso2"] for view in repository.views} == {"FR"}
    assert all(
        store.path_for(RUNTIME_PRIVATE, view["object_key"]).is_file()
        for view in repository.views
    )
