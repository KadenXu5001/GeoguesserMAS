from __future__ import annotations

from pathlib import Path
from typing import Any

from geoguesser.runtime_budget import RuntimeBudget
from geoguesser.runtime_state import GeoContext


def build_runtime_context(
    *,
    budget: RuntimeBudget,
    reference_repository: Any,
    reference_version: str,
    heading_paths: dict[int, Path],
    gemini_client: Any,
    reexamine_model: str = "gemini-3-flash-preview",
    require_specialist: bool = True,
) -> GeoContext:
    if set(heading_paths) != {0, 90, 180, 270}:
        raise ValueError("runtime context requires four cardinal heading paths")
    if not reference_version:
        raise ValueError("reference_version is required")
    return {
        "geo_budget": budget,
        "reference_repository": reference_repository,
        "reference_version": reference_version,
        "heading_paths": heading_paths,
        "gemini_client": gemini_client,
        "reexamine_model": reexamine_model,
        "require_specialist": require_specialist,
        "reference_lookup_categories": set(),
    }
