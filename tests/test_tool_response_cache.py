import json

from geoguesser.tool_response_cache import ToolResponseCache


def test_cache_read_capacity_resets_for_new_run(tmp_path) -> None:
    path = tmp_path / "tool_response_cache.json"
    first_run = ToolResponseCache(path)
    first_run.put("key", [{"country": "Brazil"}])

    for _ in range(3):
        assert first_run.get("key") == ([{"country": "Brazil"}], None)
    assert first_run.get("key") == (None, "tool response cache read capacity reached")

    second_run = ToolResponseCache(path)
    assert second_run.get("key") == ([{"country": "Brazil"}], None)


def test_cache_reads_do_not_persist_as_capacity_across_runs(tmp_path) -> None:
    path = tmp_path / "tool_response_cache.json"
    path.write_text(
        json.dumps({"key": {"response": [{"country": "Brazil"}], "reads": 3}}),
        encoding="utf-8",
    )

    cache = ToolResponseCache(path)
    assert cache.get("key") == ([{"country": "Brazil"}], None)
