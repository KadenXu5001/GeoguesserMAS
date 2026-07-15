from __future__ import annotations

import os
import re
from typing import Any

from langchain_core.tracers.langchain import LangChainTracer
from langsmith import Client


_DATA_IMAGE = re.compile(r"data:image/[^;]+;base64,[A-Za-z0-9+/=]+")


def redact_image_inputs(value: Any) -> Any:
    """Preserve prompts and tool arguments while replacing image bytes in trace inputs."""
    if isinstance(value, dict):
        if value.get("type") == "image_url" or "image_url" in value:
            return {"type": value.get("type", "image_url"), "image_url": "<image redacted>"}
        return {key: redact_image_inputs(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact_image_inputs(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_image_inputs(item) for item in value)
    if isinstance(value, str):
        return _DATA_IMAGE.sub("<image redacted>", value)
    return value


def create_langsmith_tracer() -> LangChainTracer:
    api_key = os.environ.get("LANGSMITH_API_KEY") or os.environ.get("LANGCHAIN_API_KEY")
    if not api_key:
        raise RuntimeError("LangSmith tracing requires LANGSMITH_API_KEY")
    client = Client(
        api_url=os.environ.get("LANGSMITH_ENDPOINT") or os.environ.get("LANGCHAIN_ENDPOINT"),
        api_key=api_key,
        hide_inputs=redact_image_inputs,
        hide_outputs=False,
        timeout_ms=(10_000, 60_000),
    )
    return LangChainTracer(
        project_name=os.environ.get("LANGSMITH_PROJECT", "geoguesser"),
        client=client,
    )
