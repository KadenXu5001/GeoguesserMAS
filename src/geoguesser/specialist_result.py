from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from langchain_core.messages import ToolMessage
from langgraph.types import Command

from geoguesser.prediction import SpecialistResult


SCHEMA_VERSION = "specialist-result-v1"


def _candidate_from_result(result: Any) -> Any:
    update = getattr(result, "update", None)
    if isinstance(update, dict):
        if update.get("structured_response") is not None:
            return update["structured_response"]
        for message in reversed(update.get("messages", [])):
            content = getattr(message, "content", None)
            if content:
                return content
    if isinstance(result, dict):
        if result.get("structured_response") is not None:
            return result["structured_response"]
        for message in reversed(result.get("messages", [])):
            content = getattr(message, "content", None)
            if content:
                return content
    content = getattr(result, "content", None)
    return content if content else result


def _parse_candidate(candidate: Any) -> SpecialistResult:
    if isinstance(candidate, SpecialistResult):
        return candidate
    if isinstance(candidate, dict):
        return SpecialistResult.model_validate(candidate)
    if isinstance(candidate, str) and candidate.strip():
        return SpecialistResult.model_validate_json(candidate)
    raise ValueError("specialist did not return a SpecialistResult JSON document")


def normalize_specialist_result(
    specialist: str,
    result: Any,
    *,
    artifact_dir: Path | None = None,
) -> tuple[Any, dict[str, Any]]:
    """Normalize a specialist result and preserve the framework command shape."""
    parsed = _parse_candidate(_candidate_from_result(result))
    document = {
        "schema_version": SCHEMA_VERSION,
        "specialist": specialist,
        "result": parsed.model_dump(),
    }
    target_dir = artifact_dir or Path(".deepagents") / "specialist-results"
    target_dir.mkdir(parents=True, exist_ok=True)
    artifact = target_dir / f"{specialist}-{uuid.uuid4().hex}.json"
    document["artifact"] = str(artifact)
    artifact.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")
    content = json.dumps(document, ensure_ascii=False)

    if isinstance(result, Command):
        update = dict(result.update or {})
        update["messages"] = [ToolMessage(content=content, tool_call_id="specialist-result")]
        return Command(goto=result.goto, update=update), document
    if isinstance(result, ToolMessage):
        return ToolMessage(content=content, tool_call_id=result.tool_call_id), document
    return ToolMessage(content=content, tool_call_id="specialist-result"), document
