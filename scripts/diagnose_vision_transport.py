"""Diagnose Gemini/MAS image transport without exposing credentials or image bytes."""
from __future__ import annotations

import argparse
import base64
import hashlib
import importlib.metadata
import json
import mimetypes
import os
import platform
import sys
from pathlib import Path
from time import perf_counter
from typing import Any, Callable

from dotenv import load_dotenv
from google.genai import types
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

CARDINAL_HEADINGS = (0, 90, 180, 270)
MODEL = "gemini-3-flash-preview"
PACKAGE_NAMES = (
    "google-genai",
    "langchain-google-genai",
    "langchain",
    "langgraph",
    "deepagents",
    "httpx",
    "httpcore",
)


class SnapshotRepository:
    """Read-only reference adapter used by the production MAS diagnostic."""

    def __init__(self, snapshot: dict[str, Any]) -> None:
        self.snapshot = snapshot

    def lookup_references(
        self, *, version: str, category: str, country: str | None = None
    ) -> list[dict[str, Any]]:
        from geoguesser.reference_data import lookup_references

        if version != self.snapshot["version"]:
            raise ValueError(f"reference version {version} is unavailable")
        return lookup_references(self.snapshot, category=category, country=country)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Separate Gemini authentication, direct image extraction, and full MAS transport. "
            "Network probes are opt-in and may incur provider charges."
        )
    )
    parser.add_argument(
        "--probe",
        choices=("runtime", "auth", "extraction", "mas", "all"),
        default="runtime",
        help="runtime is local-only; all runs the three independent network probes",
    )
    parser.add_argument(
        "--paths",
        nargs=4,
        type=Path,
        metavar=("H000", "H090", "H180", "H270"),
        help="four cardinal JPEG paths in 0, 90, 180, 270 degree order",
    )
    parser.add_argument("--model", default=MODEL)
    parser.add_argument(
        "--snapshot",
        type=Path,
        default=ROOT / "data/reference_tables/reference_v1.json",
    )
    return parser


def _package_versions() -> dict[str, str]:
    versions: dict[str, str] = {}
    for name in PACKAGE_NAMES:
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = "not-installed"
    return versions


def runtime_report() -> dict[str, Any]:
    key_source = next(
        (name for name in ("GEMINI_API_KEY", "GOOGLE_API_KEY") if os.environ.get(name)),
        None,
    )
    proxy_names = [
        name
        for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY")
        if os.environ.get(name)
    ]
    return {
        "python_executable": sys.executable,
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "packages": _package_versions(),
        "gemini_credential_configured": key_source is not None,
        "gemini_credential_source": key_source,
        "proxy_variables_present": proxy_names,
    }


def inspect_views(paths: list[Path]) -> tuple[dict[int, Path], dict[str, Any]]:
    resolved = {heading: path.resolve() for heading, path in zip(CARDINAL_HEADINGS, paths)}
    views: list[dict[str, Any]] = []
    total_bytes = 0
    for heading, path in resolved.items():
        if not path.is_file():
            raise FileNotFoundError(f"missing cardinal view for heading {heading}: {path}")
        data = path.read_bytes()
        total_bytes += len(data)
        with Image.open(path) as image:
            width, height = image.size
            detected_format = image.format
        views.append(
            {
                "heading": heading,
                "path": str(path),
                "bytes": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
                "mime_type": mimetypes.guess_type(path.name)[0],
                "detected_format": detected_format,
                "dimensions": [width, height],
            }
        )
    return resolved, {
        "views": views,
        "total_raw_bytes": total_bytes,
        "inline_base64_bytes": sum(
            len(base64.b64encode(path.read_bytes())) for path in resolved.values()
        ),
    }


def _exception_report(exc: BaseException) -> dict[str, Any]:
    chain = []
    current: BaseException | None = exc
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        chain.append({"type": type(current).__name__, "message": str(current)})
        current = current.__cause__ or current.__context__
    names = {item["type"] for item in chain}
    status = next(
        (
            getattr(item, "status_code")
            for item in (exc, exc.__cause__, exc.__context__)
            if item is not None and getattr(item, "status_code", None) is not None
        ),
        None,
    )
    if "WriteTimeout" in names:
        classification = "request_body_write_timeout"
    elif "ConnectTimeout" in names or "ConnectError" in names:
        classification = "connection_failure"
    elif "ReadTimeout" in names:
        classification = "response_read_timeout"
    elif status in {401, 403}:
        classification = "authentication_or_authorization_rejected"
    elif status is not None:
        classification = "provider_http_error"
    else:
        classification = "application_or_provider_error"
    return {"classification": classification, "http_status": status, "exception_chain": chain}


def _run_probe(name: str, operation: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    print(f"[{name}] starting", file=sys.stderr, flush=True)
    started = perf_counter()
    try:
        detail = operation()
        result = {"status": "succeeded", "latency_ms": round((perf_counter() - started) * 1000)}
        result.update(detail)
    except Exception as exc:  # diagnostic boundary intentionally records the provider exception
        result = {
            "status": "failed",
            "latency_ms": round((perf_counter() - started) * 1000),
            "error": _exception_report(exc),
        }
    print(f"[{name}] {result['status']} in {result['latency_ms']} ms", file=sys.stderr, flush=True)
    return result


def auth_probe(client: Any, model: str) -> dict[str, Any]:
    response = client.models.generate_content(
        model=model,
        contents="Transport diagnostic. Reply with exactly OK.",
        config=types.GenerateContentConfig(
            temperature=0,
            max_output_tokens=8,
            http_options=types.HttpOptions(
                timeout=30_000,
                retry_options=types.HttpRetryOptions(attempts=1),
            ),
        ),
    )
    return {
        "http_response_received": True,
        "text_part_received": bool(getattr(response, "text", None)),
    }


def extraction_probe(client: Any, views: dict[int, Path], model: str) -> dict[str, Any]:
    from geoguesser.extraction_runner import extract_cardinal_views

    events: list[tuple[Any, int]] = []
    extraction = extract_cardinal_views(
        client,
        views,
        model=model,
        max_attempts=1,
        usage_callback=lambda response, latency: events.append((response, latency)),
    )
    categories = extraction.model_dump()
    return {
        "provider_latency_ms": events[0][1] if events else None,
        "object_count": sum(
            len(value.get("objects", []))
            for value in categories.values()
            if isinstance(value, dict)
        ),
    }


def mas_probe(client: Any, views: dict[int, Path], snapshot_path: Path) -> dict[str, Any]:
    from geoguesser.langsmith_tracing import create_langsmith_tracer
    from geoguesser.mas_runner import run_mas_row
    from geoguesser.reference_data import load_reference_snapshot

    snapshot = load_reference_snapshot(snapshot_path)
    tracer = create_langsmith_tracer()
    progress: list[str] = []
    row = {
        f"view_h{heading:03d}_path": str(path)
        for heading, path in views.items()
    }
    try:
        result = run_mas_row(
            row,
            gemini_client=client,
            reference_repository=SnapshotRepository(snapshot),
            reference_version=snapshot["version"],
            root=ROOT,
            progress=lambda message: progress.append(message),
            trace_callbacks=[tracer],
        )
    finally:
        from langchain_core.tracers.langchain import wait_for_all_tracers

        wait_for_all_tracers()
    return {
        "workflow_progress": progress,
        "usage": result.get("usage", []),
        "specialists_used": result.get("specialists_used", []),
        "prediction_emitted": bool(result.get("prediction")),
        "warning": result.get("warning"),
    }


def diagnosis(probes: dict[str, dict[str, Any]]) -> list[str]:
    auth = probes.get("auth")
    extraction = probes.get("extraction")
    mas = probes.get("mas")
    findings: list[str] = []
    if auth and auth["status"] == "failed":
        classification = auth.get("error", {}).get("classification")
        findings.append(
            "The text-only probe failed; investigate credentials/model access first."
            if classification == "authentication_or_authorization_rejected"
            else "The text-only probe failed before image transfer; investigate runtime/network connectivity."
        )
    if auth and auth["status"] == "succeeded":
        findings.append(
            "The API key, selected model, DNS/TLS connection, and small request path are working."
        )
    if auth and auth["status"] == "succeeded" and extraction and extraction["status"] == "failed":
        findings.append(
            "Authentication and small requests work, but the direct four-image request fails; "
            "the fault is in large request transport or image serialization, not MongoDB."
        )
    if extraction and extraction["status"] == "succeeded" and mas and mas["status"] == "failed":
        error = mas.get("error", {})
        classification = error.get("classification")
        messages = " ".join(
            str(item.get("message", "")) for item in error.get("exception_chain", [])
        ).lower()
        if "re-examination requires" in messages:
            findings.append(
                "Image transport succeeded. The MAS failed later because it requested a "
                "re-examination that violated the close-signal policy; this is workflow validation, "
                "not authentication, MongoDB, or image upload."
            )
        elif classification == "request_body_write_timeout":
            findings.append(
                "Direct extraction works but a MAS model request timed out while writing its body; "
                "accumulated multimodal conversation replay or concurrent MAS traffic is the primary suspect."
            )
        else:
            findings.append(
                "Direct extraction and image transport work. The MAS failed later with a non-transport "
                "application/provider error; inspect its exception chain and LangSmith workflow trace."
            )
    if (
        {"auth", "extraction", "mas"}.issubset(probes)
        and all(probes[name].get("status") == "succeeded" for name in ("auth", "extraction", "mas"))
    ):
        findings.append(
            "All three probes succeeded; the reported timeout is likely intermittent or caused "
            "by concurrent browser-triggered MAS runs."
        )
    return findings


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    args = build_parser().parse_args()
    load_dotenv(ROOT / ".env")
    os.environ["LANGSMITH_TRACING"] = "false"
    os.environ["LANGCHAIN_TRACING_V2"] = "false"
    os.environ["LANGCHAIN_CALLBACKS_BACKGROUND"] = "false"

    report: dict[str, Any] = {"runtime": runtime_report(), "probes": {}}
    views: dict[int, Path] | None = None
    if args.paths:
        try:
            views, report["image_payload"] = inspect_views(args.paths)
        except Exception as exc:
            report["image_payload"] = {"status": "failed", "error": _exception_report(exc)}

    needs_images = args.probe in {"extraction", "mas", "all"}
    if needs_images and views is None:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        print("--paths H000 H090 H180 H270 is required for this probe", file=sys.stderr)
        return 2
    if args.probe == "runtime":
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    from geoguesser.gemini_client import create_gemini_client

    try:
        client = create_gemini_client()
    except Exception as exc:
        report["client"] = {"status": "failed", "error": _exception_report(exc)}
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1

    if args.probe in {"auth", "all"}:
        report["probes"]["auth"] = _run_probe(
            "auth", lambda: auth_probe(client, args.model)
        )
    if args.probe in {"extraction", "all"}:
        assert views is not None
        report["probes"]["extraction"] = _run_probe(
            "extraction", lambda: extraction_probe(client, views, args.model)
        )
    if args.probe in {"mas", "all"}:
        assert views is not None
        report["probes"]["mas"] = _run_probe(
            "mas", lambda: mas_probe(client, views, args.snapshot)
        )

    report["findings"] = diagnosis(report["probes"])
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if all(item["status"] == "succeeded" for item in report["probes"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
