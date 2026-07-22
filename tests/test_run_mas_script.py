import importlib.util
from pathlib import Path

import pytest


def _load_script():
    script_path = Path("scripts/run_mas.py")
    spec = importlib.util.spec_from_file_location("run_mas", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_snapshot_repository_reads_versioned_local_rows() -> None:
    module = _load_script()
    repository = module.SnapshotRepository(
        {
            "version": "reference-test",
            "rows": [
                {"category": "road_markings", "country": "France", "clue": "white lines"},
                {"category": "road_markings", "country": "Brazil", "clue": "yellow center"},
            ],
        }
    )

    rows = repository.lookup_references(
        version="reference-test", category="road_markings", country="france"
    )

    assert [row["clue"] for row in rows] == ["white lines"]


def test_snapshot_repository_rejects_a_different_version() -> None:
    module = _load_script()
    repository = module.SnapshotRepository({"version": "reference-test", "rows": []})

    with pytest.raises(ValueError, match="unavailable"):
        repository.lookup_references(version="other", category="road_markings")


def test_local_mas_runner_has_no_mongodb_dependency() -> None:
    script = Path("scripts/run_mas.py").read_text(encoding="utf-8")

    assert "connect_database" not in script
    assert "MongoRepository" not in script
