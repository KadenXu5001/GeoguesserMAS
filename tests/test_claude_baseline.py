from pathlib import Path

import pytest
from PIL import Image

from geoguesser.baselines import run_claude_opus_baseline
from geoguesser.cost_model import Pricing


def _views(tmp_path: Path) -> dict[int, Path]:
    result = {}
    for heading in (0, 90, 180, 270):
        path = tmp_path / f"h{heading}.jpg"
        Image.new("RGB", (8, 8), (heading % 255, 10, 20)).save(path)
        result[heading] = path
    return result


def test_claude_baseline_sends_four_images_and_records_measured_cost(tmp_path: Path) -> None:
    class Client:
        def create_message(self, payload):
            self.payload = payload
            return {
                "model": "claude-test",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            '{"country":"France","confidence":82,'
                            '"alternatives":["Belgium"],"evidence":["road markings"]}'
                        ),
                    }
                ],
                "usage": {"input_tokens": 1000, "output_tokens": 100},
            }

    client = Client()
    result = run_claude_opus_baseline(
        client,
        _views(tmp_path),
        model="claude-test",
        pricing=Pricing(2.0, 10.0),
    )

    blocks = client.payload["messages"][0]["content"]
    assert sum(block["type"] == "image" for block in blocks) == 4
    assert client.payload["output_config"]["format"]["type"] == "json_schema"
    assert result.prediction.country == "France"
    assert result.usage["input_tokens"] == 1000
    assert result.usage["output_tokens"] == 100
    assert result.usage["cost_usd"] == pytest.approx(0.003)


def test_claude_baseline_requires_a_structured_text_result(tmp_path: Path) -> None:
    class Client:
        def create_message(self, payload):
            return {"content": [{"type": "thinking", "thinking": "France"}], "usage": {}}

    with pytest.raises(RuntimeError, match="structured text"):
        run_claude_opus_baseline(Client(), _views(tmp_path))
