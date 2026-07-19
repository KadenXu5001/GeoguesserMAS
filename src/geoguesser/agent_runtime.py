from __future__ import annotations

from pathlib import Path
from threading import Lock
from typing import Any

from geoguesser.runtime_budget import RuntimeBudget
from geoguesser.runtime_state import GeoContext
from geoguesser.tool_response_cache import ToolResponseCache


_SCAN_CATEGORY_FAMILIES = {
    "driving_side_and_markings": {
        "driving_side", "road_markings", "chevrons_guardrails"
    },
    "vehicles_and_plates": {"vehicles", "license_plates"},
    "signs_and_language": {"language_script", "country_domains", "urban_signage"},
    "infrastructure": {
        "bollards", "urban_utility_poles", "rural_utility_poles", "rural_roadside_features"
    },
    "terrain_vegetation_and_climate": {
        "soil_geology", "vegetation_biomes", "terrain_scenery", "climate", "agriculture_land_use"
    },
    "architecture_and_settlement": {
        "urban_architecture", "street_names_addresses", "businesses_domains",
        "sidewalks_curbs", "public_transit", "rural_architecture"
    },
}


def _scan_allowed_categories(extraction: Any) -> set[str]:
    if not isinstance(extraction, dict):
        return set()
    allowed: set[str] = set()
    for family, categories in _SCAN_CATEGORY_FAMILIES.items():
        category_data = extraction.get(family)
        if isinstance(category_data, dict) and category_data.get("status") in {
            "present", "present_but_illegible"
        }:
            allowed.update(categories)
    return allowed


def _scan_objects(extraction: Any) -> dict[str, set[str]]:
    """Index exact extracted object observations by the lookup category they support."""
    if not isinstance(extraction, dict):
        return {}
    family_categories = {
        "driving_side_and_markings": {"driving_side", "road_markings", "chevrons_guardrails"},
        "vehicles_and_plates": {"vehicles", "license_plates"},
        "signs_and_language": {"language_script", "country_domains", "urban_signage"},
        "infrastructure": {
            "bollards", "urban_utility_poles", "rural_utility_poles", "rural_roadside_features"
        },
        "terrain_vegetation_and_climate": {
            "soil_geology", "vegetation_biomes", "terrain_scenery", "climate", "agriculture_land_use"
        },
        "architecture_and_settlement": {
            "urban_architecture", "street_names_addresses", "businesses_domains",
            "sidewalks_curbs", "public_transit", "rural_architecture"
        },
    }
    objects: dict[str, set[str]] = {}
    for family, categories in family_categories.items():
        family_data = extraction.get(family)
        if not isinstance(family_data, dict):
            continue
        for item in family_data.get("objects", []):
            if isinstance(item, dict) and isinstance(item.get("observation"), str):
                for category in categories:
                    objects.setdefault(category, set()).add(item["observation"])
    return objects


def apply_extraction_context(context: dict[str, Any], extraction: dict[str, Any]) -> None:
    """Install validated extraction indexes for specialist authorization in this run."""
    context["scan_allowed_categories"] = _scan_allowed_categories(extraction)
    context["scan_objects"] = _scan_objects(extraction)


def build_runtime_context(
    *,
    budget: RuntimeBudget,
    reference_repository: Any,
    reference_version: str,
    heading_paths: dict[int, Path],
    gemini_client: Any,
    extraction: dict[str, Any] | None = None,
    reexamine_model: str = "gemini-3-flash-preview",
    require_specialist: bool = True,
    tool_response_cache: ToolResponseCache | None = None,
    progress: Any | None = None,
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
        "reference_lookup_details": [],
        "scan_allowed_categories": _scan_allowed_categories(extraction),
        "scan_objects": _scan_objects(extraction),
        "active_specialist": None,
        "specialist_tool_calls": {},
        "todo_plan": [],
        "tool_response_cache": tool_response_cache or ToolResponseCache(),
        "progress": progress or (lambda message: None),
        "orchestration_phase": "todo",
        "extraction_attempted": False,
        "final_prediction": None,
        "decision_log": [],
        "decision_log_lock": Lock(),
    }
