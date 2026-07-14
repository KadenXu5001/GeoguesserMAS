from pathlib import Path
from types import SimpleNamespace

from PIL import Image

from geoguesser.baselines import GEMINI_PRO_MODEL, run_gemini_baseline, run_gemini_pro_baseline


def views(tmp_path: Path) -> dict[int, Path]:
    paths = {}
    for heading in (0, 90, 180, 270):
        path = tmp_path / f"h{heading}.jpg"
        Image.new("RGB", (8, 8), (heading % 255, 10, 20)).save(path)
        paths[heading] = path
    return paths


def test_gemini_baseline_sends_all_four_views_once(tmp_path: Path) -> None:
    response = SimpleNamespace(
        parsed={"country": "France", "confidence": 80, "alternatives": [], "evidence": ["road"]},
        usage_metadata=SimpleNamespace(prompt_token_count=10, candidates_token_count=4),
    )

    class Models:
        def __init__(self):
            self.call = None

        def generate_content(self, **kwargs):
            self.call = kwargs
            return response

    models = Models()
    result = run_gemini_baseline(SimpleNamespace(models=models), views(tmp_path), model="flash")
    assert result.prediction.country == "France"
    assert len(models.call["contents"]) == 5
    assert result.usage["input_tokens"] == 10


def test_gemini_pro_uses_the_same_four_view_contract(tmp_path: Path) -> None:
    class Models:
        def generate_content(self, **kwargs):
            self.call = kwargs
            return SimpleNamespace(
                parsed={"country": "Thailand", "confidence": 75, "alternatives": [], "evidence": ["road"]},
                usage_metadata={},
            )

    models = Models()
    result = run_gemini_pro_baseline(SimpleNamespace(models=models), views(tmp_path))
    assert result.prediction.country == "Thailand"
    assert models.call["model"] == GEMINI_PRO_MODEL
    assert len(models.call["contents"]) == 5


def test_gemini_baseline_retries_truncated_json(tmp_path: Path) -> None:
    class Models:
        def __init__(self):
            self.calls = 0

        def generate_content(self, **kwargs):
            self.calls += 1
            if self.calls == 1:
                return SimpleNamespace(text='{"country":"France"')
            return SimpleNamespace(
                parsed={"country": "France", "confidence": 80, "alternatives": [], "evidence": ["road"]},
                usage_metadata={},
            )

    models = Models()
    result = run_gemini_baseline(
        SimpleNamespace(models=models), views(tmp_path), model="gemini-test"
    )
    assert result.prediction.country == "France"
    assert models.calls == 2
