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
    todos = [
        {"content": "Extract visual evidence with extract_visual_evidence", "status": "completed"},
        {"content": "Delegate to urban-specialist or rural-specialist with task", "status": "completed"},
        {"content": "Optionally reexamine_region only for two close country signals", "status": "pending"},
        {"content": "Emit final country prediction with emit_prediction", "status": "pending"},
    ]
    runtime = SimpleNamespace(
        context={
            "geo_budget": RuntimeBudget(opus_cost_usd=1.0),
            "todo_plan": todos,
            "orchestration_phase": "finalizing",
            "decision_log": [],
        },
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
    assert result.update["todos"][-1]["status"] == "completed"
    assert runtime.context["final_prediction"] == result.update["final_prediction"]
    assert runtime.context["todo_plan"][-1]["status"] == "completed"
    assert runtime.context["orchestration_phase"] == "done"
    assert result.update["decision_log"][-1]["event"] == "prediction_finalized"
    assert isinstance(result.update["messages"][0], ToolMessage)


class ExtractionModels:
    def __init__(self):
        self.calls = 0
        self.last_config = None

    def generate_content(self, **kwargs):
        self.calls += 1
        self.last_config = kwargs["config"]
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
            "decision_log": [],
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
    assert [event["event"] for event in result.update["decision_log"]][-2:] == [
        "extraction_started",
        "extraction_completed",
    ]
    config = models.last_config
    assert config.http_options.timeout == 30_000
    assert config.http_options.retry_options.attempts == 1


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
            "todo_plan": [
                {"content": "Extract", "status": "completed"},
                {"content": "Delegate", "status": "completed"},
                {"content": "Reexamine", "status": "in_progress"},
                {"content": "Emit", "status": "pending"},
            ],
            "decision_log": [],
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
    assert result.update["todos"][2]["status"] == "completed"
    assert "view.jpg" not in result.update["messages"][0].content
