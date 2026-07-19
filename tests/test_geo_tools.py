import json
from types import SimpleNamespace

from langchain_core.messages import ToolMessage
from langgraph.graph import END

from geoguesser.geo_tools import emit_prediction, extract_visual_evidence
from geoguesser.geo_tools import reexamine_region
from geoguesser.runtime_budget import RuntimeBudget


def extraction_payload() -> dict:
    category = {"status": "not_detected", "signal": "", "objects": []}
    return {
        "driving_side_and_markings": category,
        "signs_and_language": category,
        "vehicles_and_plates": category,
        "infrastructure": category,
        "terrain_vegetation_and_climate": category,
        "architecture_and_settlement": category,
    }


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


class ExtractionModels:
    def __init__(self):
        self.calls = 0

    def generate_content(self, **kwargs):
        self.calls += 1
        return SimpleNamespace(
            text=json.dumps(extraction_payload()),
            usage_metadata={"prompt_token_count": 10, "candidates_token_count": 5},
        )


def test_visual_extraction_is_first_class_single_use_tool(tmp_path) -> None:
    from PIL import Image

    paths = {}
    for heading in (0, 90, 180, 270):
        path = tmp_path / f"view-{heading}.jpg"
        Image.new("RGB", (16, 16), "black").save(path)
        paths[heading] = path
    models = ExtractionModels()
    runtime = SimpleNamespace(
        context={
            "geo_budget": RuntimeBudget(opus_cost_usd=1.0),
            "heading_paths": paths,
            "gemini_client": SimpleNamespace(models=models),
            "extraction_attempted": False,
            "orchestration_phase": "extraction",
            "scan_allowed_categories": set(),
            "scan_objects": {},
        },
        state={},
        tool_call_id="extract-1",
    )

    result = extract_visual_evidence.func(runtime=runtime)

    assert result.update["extraction_status"] == "succeeded"
    assert models.calls == 1
    assert runtime.context["orchestration_phase"] == "specialist"
    assert runtime.context["extraction_attempted"] is True
    assert runtime.context["geo_budget"].usage_events[0]["component"] == "extraction"


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
