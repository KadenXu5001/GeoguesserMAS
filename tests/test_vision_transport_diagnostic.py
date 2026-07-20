from __future__ import annotations

import importlib.util
from pathlib import Path

from PIL import Image


def load_script():
    path = Path("scripts/diagnose_vision_transport.py")
    spec = importlib.util.spec_from_file_location("diagnose_vision_transport", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_inspect_views_reports_original_jpeg_payload_without_base64_content(tmp_path: Path) -> None:
    diagnostic = load_script()
    paths = []
    for heading in (0, 90, 180, 270):
        path = tmp_path / f"view-{heading}.jpg"
        Image.new("RGB", (16, 12), "black").save(path, format="JPEG")
        paths.append(path)

    resolved, report = diagnostic.inspect_views(paths)

    assert set(resolved) == {0, 90, 180, 270}
    assert report["total_raw_bytes"] == sum(path.stat().st_size for path in paths)
    assert report["inline_base64_bytes"] > report["total_raw_bytes"]
    assert all(view["detected_format"] == "JPEG" for view in report["views"])
    assert "base64" not in str(report["views"]).lower()


def test_exception_report_distinguishes_write_timeout_from_auth_rejection() -> None:
    diagnostic = load_script()

    WriteTimeout = type("WriteTimeout", (Exception,), {})
    assert diagnostic._exception_report(WriteTimeout("slow"))["classification"] == (
        "request_body_write_timeout"
    )

    denied = RuntimeError("denied")
    denied.status_code = 403
    assert diagnostic._exception_report(denied)["classification"] == (
        "authentication_or_authorization_rejected"
    )


def test_diagnosis_isolates_mas_payload_from_direct_extraction() -> None:
    diagnostic = load_script()
    findings = diagnostic.diagnosis(
        {
            "auth": {"status": "succeeded"},
            "extraction": {"status": "succeeded"},
            "mas": {
                "status": "failed",
                "error": {
                    "classification": "request_body_write_timeout",
                    "exception_chain": [{"type": "WriteTimeout", "message": "slow"}],
                },
            },
        }
    )

    assert any("conversation replay" in finding for finding in findings)


def test_diagnosis_identifies_invalid_reexamination_as_workflow_failure() -> None:
    diagnostic = load_script()
    findings = diagnostic.diagnosis(
        {
            "auth": {"status": "succeeded"},
            "extraction": {"status": "succeeded"},
            "mas": {
                "status": "failed",
                "error": {
                    "classification": "application_or_provider_error",
                    "exception_chain": [
                        {
                            "type": "ValueError",
                            "message": "re-examination requires competing signals within 10 confidence points",
                        }
                    ],
                },
            },
        }
    )

    assert any("workflow validation" in finding for finding in findings)
    assert not any("conversation replay" in finding for finding in findings)


def test_auth_only_success_does_not_claim_all_transport_probes_succeeded() -> None:
    diagnostic = load_script()

    findings = diagnostic.diagnosis({"auth": {"status": "succeeded"}})

    assert any("small request path" in finding for finding in findings)
    assert not any("All three probes" in finding for finding in findings)
