from pathlib import Path


def test_flash_baseline_is_single_call_and_does_not_use_mas_or_langsmith() -> None:
    script = Path("scripts/run_gemini_flash.py").read_text(encoding="utf-8")

    assert "model=GEMINI_FLASH_MODEL" in script
    assert "max_attempts=1" in script
    assert "resolve_mas_view_paths" in script
    assert "run_mas_row" not in script
    assert "create_langsmith_tracer" not in script
    assert 'os.environ["LANGSMITH_TRACING"] = "false"' in script
