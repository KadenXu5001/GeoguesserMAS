from __future__ import annotations

import os
import re
import threading
from typing import Any

from langchain_core.tracers.langchain import LangChainTracer, wait_for_all_tracers
from langsmith import Client


_DATA_IMAGE = re.compile(r"data:image/[^;]+;base64,[A-Za-z0-9+/=]+")
OBSERVABILITY_FAILURE_PREFIX = "LANGSMITH_OBSERVABILITY_FAILURE"
DEFAULT_FLUSH_TIMEOUT_SECONDS = 30.0
_TRACE_DELIVERY_ERRORS: list[Exception] = []
_TRACE_DELIVERY_ERRORS_LOCK = threading.Lock()


def _record_trace_delivery_error(error: Exception) -> None:
    with _TRACE_DELIVERY_ERRORS_LOCK:
        _TRACE_DELIVERY_ERRORS.append(error)


def _take_trace_delivery_errors() -> list[Exception]:
    with _TRACE_DELIVERY_ERRORS_LOCK:
        errors = list(_TRACE_DELIVERY_ERRORS)
        _TRACE_DELIVERY_ERRORS.clear()
    return errors


def redact_image_inputs(value: Any) -> Any:
    """Preserve trace structure while replacing image bytes in inputs or outputs."""
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


def flush_langsmith_traces(
    *,
    tracer: LangChainTracer | None = None,
    timeout_seconds: float = DEFAULT_FLUSH_TIMEOUT_SECONDS,
    waiter: Any | None = None,
) -> None:
    """Synchronously flush traces without allowing observability to hang the process forever."""
    if timeout_seconds <= 0:
        raise ValueError("LangSmith flush timeout must be greater than zero")

    client = tracer.client if tracer is not None else None
    selected_waiter = waiter or (client.flush if client is not None else wait_for_all_tracers)
    completed = threading.Event()
    errors: list[BaseException] = []

    def wait() -> None:
        try:
            selected_waiter()
        except BaseException as exc:  # Preserve SDK failures as observability failures.
            errors.append(exc)
        finally:
            completed.set()

    thread = threading.Thread(target=wait, name="langsmith-trace-flush", daemon=True)
    thread.start()
    try:
        if not completed.wait(timeout_seconds):
            raise RuntimeError(
                f"{OBSERVABILITY_FAILURE_PREFIX}: mandatory trace flush exceeded "
                f"{timeout_seconds:g} seconds; the MAS prediction completed but trace delivery did not"
            )
        if errors:
            raise RuntimeError(
                f"{OBSERVABILITY_FAILURE_PREFIX}: mandatory trace flush failed: {errors[0]}"
            ) from errors[0]
        delivery_errors = _take_trace_delivery_errors()
        if delivery_errors:
            raise RuntimeError(
                f"{OBSERVABILITY_FAILURE_PREFIX}: LangSmith rejected a trace upload: "
                f"{delivery_errors[0]}"
            ) from delivery_errors[0]
    finally:
        # The explicit client owns non-daemon uploader resources. Closing it is
        # required for the Python child process to emit its close event to Node.
        if client is not None:
            client.close(timeout=0)


def create_langsmith_tracer() -> LangChainTracer:
    api_key = os.environ.get("LANGSMITH_API_KEY") or os.environ.get("LANGCHAIN_API_KEY")
    if not api_key:
        raise RuntimeError("LangSmith tracing requires LANGSMITH_API_KEY")
    client = Client(
        api_url=os.environ.get("LANGSMITH_ENDPOINT") or os.environ.get("LANGCHAIN_ENDPOINT"),
        api_key=api_key,
        hide_inputs=redact_image_inputs,
        hide_outputs=redact_image_inputs,
        timeout_ms=(10_000, 60_000),
        tracing_error_callback=_record_trace_delivery_error,
    )
    return LangChainTracer(
        project_name=os.environ.get("LANGSMITH_PROJECT", "geoguesser"),
        client=client,
    )
