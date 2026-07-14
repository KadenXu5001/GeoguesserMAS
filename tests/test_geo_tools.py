from types import SimpleNamespace

from langchain_core.messages import ToolMessage
from langgraph.graph import END

from geoguesser.geo_tools import emit_prediction
from geoguesser.geo_tools import reexamine_region
from geoguesser.runtime_budget import RuntimeBudget


def test_emit_prediction_writes_state_and_terminates() -> None:
    runtime = SimpleNamespace(
        context={"geo_budget": RuntimeBudget(opus_cost_usd=1.0)},
        state={},
        tool_call_id="call-1",
    )
    result = emit_prediction.func(
        country="France",
        confidence=82,
        alternatives=["Belgium"],
        evidence=["French road sign appearance"],
        runtime=runtime,
    )

    assert result.goto == END
    assert result.update["final_prediction"]["country"] == "France"
    assert isinstance(result.update["messages"][0], ToolMessage)


class FakeModels:
    def generate_content(self, **kwargs):
        return SimpleNamespace(text="The sign is too blurred to read, but its shape is visible.")


class FakeClient:
    models = FakeModels()


def test_reexamine_region_uses_context_path_and_updates_text_only(tmp_path) -> None:
    from PIL import Image

    view = tmp_path / "view.jpg"
    Image.new("RGB", (100, 100), "white").save(view)
    runtime = SimpleNamespace(
        context={
            "geo_budget": RuntimeBudget(opus_cost_usd=1.0),
            "heading_paths": {90: view},
            "gemini_client": FakeClient(),
        },
        state={},
        tool_call_id="call-2",
    )

    result = reexamine_region.func(
        heading=90,
        bbox=[250, 250, 750, 750],
        question="Can any text on this sign be read?",
        signal_a="France",
        score_a=70,
        signal_b="Belgium",
        score_b=65,
        runtime=runtime,
    )

    assert result.update["reexamine_results"][0]["answer"].startswith("The sign")
    assert "view.jpg" not in result.update["messages"][0].content
