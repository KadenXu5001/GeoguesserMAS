import importlib.util
from pathlib import Path


def test_vision_mas_configures_utf8_output_before_running() -> None:
    script = Path("scripts/run_vision_mas.py").read_text(encoding="utf-8")

    stdout_config = 'sys.stdout.reconfigure(encoding="utf-8")'
    stderr_config = 'sys.stderr.reconfigure(encoding="utf-8")'
    assert stdout_config in script
    assert stderr_config in script
    assert script.index(stdout_config) < script.index("def main()")
    assert script.index(stderr_config) < script.index("def main()")


def test_browser_adapter_emits_only_the_selected_prediction_country() -> None:
    script = Path("scripts/run_vision_mas.py").read_text(encoding="utf-8")

    assert '"predictedCountry": result["prediction"]["country"]' in script
    assert 'result["prediction"]["alternatives"]' not in script


def test_browser_adapter_preserves_object_store_identity_and_hashes(tmp_path: Path) -> None:
    script_path = Path("scripts/run_vision_mas.py")
    spec = importlib.util.spec_from_file_location("run_vision_mas", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    paths = [tmp_path / f"h{heading:03d}.jpg" for heading in (0, 90, 180, 270)]

    row = module.build_mas_row(
        {
            "imageId": "image-1",
            "datasetVersion": "pilot_v1",
            "paths": [str(path) for path in paths],
            "viewHashes": ["a", "b", "c", "d"],
        }
    )

    assert row["mapillary_image_id"] == "image-1"
    assert row["dataset_version"] == "pilot_v1"
    assert row["view_h000_path"] == str(paths[0].resolve())
    assert row["view_h270_path"] == str(paths[3].resolve())
    assert [row[f"view_h{heading:03d}_sha256"] for heading in (0, 90, 180, 270)] == [
        "a", "b", "c", "d"
    ]
