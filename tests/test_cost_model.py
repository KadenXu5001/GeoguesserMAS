from geoguesser.cost_model import OPUS_BASELINE, PATHS, claude_image_tokens


def test_claude_1024_square_token_count() -> None:
    assert claude_image_tokens(1024, 1024) == 1369


def test_all_mas_paths_clear_ten_percent_cost_gate() -> None:
    for name in ("MAS easy", "MAS delegated", "MAS hard"):
        assert PATHS[name] <= OPUS_BASELINE * 0.9
