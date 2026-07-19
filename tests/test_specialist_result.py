import json
from pathlib import Path

from langchain_core.messages import ToolMessage
from langgraph.types import Command

from geoguesser.specialist_result import normalize_specialist_result


def test_specialist_result_is_normalized_and_written(tmp_path) -> None:
    normalized, document = normalize_specialist_result(
        "rural-specialist",
        '{"candidates":["Brazil"],"evidence":["soil"],"contradictions":[],"confidence":80}',
        artifact_dir=tmp_path,
    )

    assert document["schema_version"] == "specialist-result-v1"
    assert normalized.content == json.dumps(document, ensure_ascii=False)
    assert normalized.name == "task"
    assert json.loads(Path(document["artifact"]).read_text()) == document


def test_specialist_command_preserves_parent_task_identity(tmp_path) -> None:
    result = Command(
        update={
            "structured_response": {
                "candidates": ["Brazil"],
                "evidence": ["soil"],
                "contradictions": [],
                "confidence": 80,
            }
        }
    )

    normalized, _ = normalize_specialist_result(
        "rural-specialist",
        result,
        artifact_dir=tmp_path,
        tool_call_id="task-call-1",
    )

    message = normalized.update["messages"][0]
    assert isinstance(message, ToolMessage)
    assert message.tool_call_id == "task-call-1"
    assert message.name == "task"
