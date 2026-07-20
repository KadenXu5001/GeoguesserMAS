from __future__ import annotations

import threading

import pytest

from geoguesser import langsmith_tracing


def test_redacts_images_recursively_without_removing_text() -> None:
    payload = {
        "messages": [
            {
                "content": [
                    {"type": "text", "text": "keep this clue"},
                    {
                        "type": "image_url",
                        "image_url": {"url": "data:image/jpeg;base64,QUJDRA=="},
                    },
                ]
            }
        ]
    }

    redacted = langsmith_tracing.redact_image_inputs(payload)

    assert redacted["messages"][0]["content"][0]["text"] == "keep this clue"
    assert redacted["messages"][0]["content"][1]["image_url"] == "<image redacted>"
    assert "QUJDRA" not in repr(redacted)


def test_tracer_redacts_both_inputs_and_outputs(monkeypatch: pytest.MonkeyPatch) -> None:
    client_options: dict[str, object] = {}

    class FakeClient:
        def __init__(self, **kwargs: object) -> None:
            client_options.update(kwargs)

    class FakeTracer:
        def __init__(self, **kwargs: object) -> None:
            self.options = kwargs

    monkeypatch.setenv("LANGSMITH_API_KEY", "test-key")
    monkeypatch.setattr(langsmith_tracing, "Client", FakeClient)
    monkeypatch.setattr(langsmith_tracing, "LangChainTracer", FakeTracer)

    langsmith_tracing.create_langsmith_tracer()

    assert client_options["hide_inputs"] is langsmith_tracing.redact_image_inputs
    assert client_options["hide_outputs"] is langsmith_tracing.redact_image_inputs


def test_sdk_upload_callback_is_reported_by_flush(monkeypatch: pytest.MonkeyPatch) -> None:
    client_options: dict[str, object] = {}

    class FakeClient:
        def __init__(self, **kwargs: object) -> None:
            client_options.update(kwargs)

    class FakeTracer:
        def __init__(self, **kwargs: object) -> None:
            self.options = kwargs

    monkeypatch.setenv("LANGSMITH_API_KEY", "test-key")
    monkeypatch.setattr(langsmith_tracing, "Client", FakeClient)
    monkeypatch.setattr(langsmith_tracing, "LangChainTracer", FakeTracer)
    langsmith_tracing.create_langsmith_tracer()
    callback = client_options["tracing_error_callback"]
    assert callable(callback)
    callback(OSError("multipart upload failed"))

    with pytest.raises(RuntimeError, match="LANGSMITH_OBSERVABILITY_FAILURE"):
        langsmith_tracing.flush_langsmith_traces(waiter=lambda: None)


def test_flush_timeout_is_reported_as_observability_failure() -> None:
    release = threading.Event()

    with pytest.raises(RuntimeError, match="LANGSMITH_OBSERVABILITY_FAILURE"):
        langsmith_tracing.flush_langsmith_traces(
            timeout_seconds=0.01,
            waiter=lambda: release.wait(1),
        )
    release.set()


def test_flush_sdk_failure_is_reported_as_observability_failure() -> None:
    def fail() -> None:
        raise OSError("upload unavailable")

    with pytest.raises(RuntimeError, match="LANGSMITH_OBSERVABILITY_FAILURE"):
        langsmith_tracing.flush_langsmith_traces(waiter=fail)


def test_explicit_tracer_client_is_flushed_and_closed() -> None:
    calls: list[tuple[str, object]] = []

    class FakeClient:
        def flush(self) -> None:
            calls.append(("flush", None))

        def close(self, *, timeout: float) -> None:
            calls.append(("close", timeout))

    class FakeTracer:
        client = FakeClient()

    langsmith_tracing.flush_langsmith_traces(tracer=FakeTracer())

    assert calls == [("flush", None), ("close", 0)]
