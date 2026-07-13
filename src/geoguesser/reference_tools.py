from __future__ import annotations

from langchain.tools import ToolRuntime, tool

from geoguesser.reference_data import lookup_references


def _snapshot(runtime: ToolRuntime) -> dict:
    snapshot = runtime.context.get("reference_snapshot")
    if not isinstance(snapshot, dict):
        raise RuntimeError("reference_snapshot is required in per-run runtime context")
    return snapshot


@tool
def lookup_human_clues(category: str, country: str | None, runtime: ToolRuntime) -> list[dict]:
    """Look up compact human-made country indicators from the frozen reference snapshot."""
    allowed = {"driving_side", "license_plates", "bollards", "utility_poles", "signs"}
    if category not in allowed:
        raise ValueError(f"unsupported human-clue category: {category}")
    return lookup_references(_snapshot(runtime), category=category, country=country)


@tool
def lookup_environmental_clues(category: str, country: str | None, runtime: ToolRuntime) -> list[dict]:
    """Look up compact environmental and architecture indicators from the frozen snapshot."""
    allowed = {"architecture", "scenery", "vegetation", "climate"}
    if category not in allowed:
        raise ValueError(f"unsupported environmental category: {category}")
    return lookup_references(_snapshot(runtime), category=category, country=country)


def human_reference_tools() -> list:
    return [lookup_human_clues]


def environmental_reference_tools() -> list:
    return [lookup_environmental_clues]


def reference_tools() -> list:
    return [lookup_human_clues, lookup_environmental_clues]
