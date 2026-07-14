from pathlib import Path


def test_baseline_script_exists_and_documents_manifest_columns() -> None:
    script = Path("scripts/run_gemini_pro.py").read_text(encoding="utf-8")
    assert "view_h000_path" in script
    assert "gemini-pro-baseline" in script
    assert "dev_v1.csv" in script
