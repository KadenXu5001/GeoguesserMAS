from __future__ import annotations

from langchain.tools import ToolRuntime, tool

from geoguesser.decision_log import record_decision
from geoguesser.runtime_state import GeoContext, GeoState
from geoguesser.tool_response_cache import ToolResponseCache

import json
from typing import Literal


UniversalCategory = Literal[
    "driving_side", "license_plates", "road_markings", "language_script",
    "country_domains", "bollards", "chevrons_guardrails", "vehicles",
]
UrbanCategory = Literal[
    "urban_architecture", "urban_utility_poles", "urban_signage",
    "street_names_addresses", "businesses_domains", "sidewalks_curbs", "public_transit",
]
RuralCategory = Literal[
    "soil_geology", "vegetation_biomes", "terrain_scenery", "climate",
    "agriculture_land_use", "rural_architecture", "rural_utility_poles", "rural_roadside_features",
]


def _repository(runtime: ToolRuntime[GeoContext, GeoState]):
    repository = runtime.context.get("reference_repository")
    if repository is None:
        raise RuntimeError("reference_repository is required in per-run runtime context")
    return repository


def _version(runtime: ToolRuntime[GeoContext, GeoState]) -> str:
    version = runtime.context.get("reference_version")
    if not isinstance(version, str) or not version:
        raise RuntimeError("reference_version is required in per-run runtime context")
    return version


def _claim_category(runtime: ToolRuntime[GeoContext, GeoState], family: str, category: str) -> str | None:
    """Allow one broad lookup per category for each tool family."""
    context = runtime.context
    seen = context.setdefault("reference_lookup_categories", set())
    key = f"{family}:{category}"
    if key in seen:
        return f"category already looked up: {category}; stop calling this tool and return your SpecialistResult"
    seen.add(key)
    return None


def _lookup(
    *, category: str, allowed: set[str], family: str, runtime: ToolRuntime[GeoContext, GeoState], country: str | None,
    justification: str, object_observation: str,
) -> list[dict]:
    specialist = runtime.context.get("active_specialist") or "unknown-specialist"
    record_decision(
        runtime.context,
        "reference_lookup_requested",
        "Specialist requested bounded reference knowledge for visible evidence.",
        tool=f"lookup_{family}_clues",
        specialist=specialist,
        category=category,
        object_observation=object_observation,
        justification=justification.strip(),
        reason_code="specialist_evidence_question",
    )

    def rejected(payload: dict, reason_code: str) -> list[dict]:
        record_decision(
            runtime.context,
            "reference_lookup_rejected",
            "Runtime rejected a reference lookup that violated its evidence contract.",
            tool=f"lookup_{family}_clues",
            specialist=specialist,
            category=category,
            reason_code=reason_code,
            result=payload,
        )
        return [payload]

    tool_counts = runtime.context.setdefault("specialist_tool_calls", {})
    count = int(tool_counts.get(specialist, 0))
    if count >= 3:
        return rejected(
            {"warning": f"{specialist} lookup cap reached (3 tools); stop and return SpecialistResult"},
            "specialist_lookup_cap",
        )
    tool_counts[specialist] = count + 1
    if not justification.strip() or len(justification.strip()) < 12:
        return rejected(
            {"error": "lookup requires a specific evidence-based justification of at least 12 characters"},
            "justification_too_short",
        )
    progress = runtime.context.get("progress")
    if category not in allowed:
        return rejected(
            {"error": f"unsupported {family} category: {category}", "allowed_categories": sorted(allowed)},
            "unsupported_category",
        )
    observations = runtime.context.get("scan_objects", {}).get(category, set())
    if object_observation not in observations:
        return rejected({
            "error": "lookup must cite an exact object observation from the supervisor extraction",
            "category": category,
            "allowed_objects": sorted(observations),
        }, "object_not_in_extraction")
    if object_observation.casefold() not in justification.casefold():
        return rejected({
            "error": "lookup justification must explicitly explain why the exact object observation is worth this lookup",
            "object_observation": object_observation,
        }, "justification_missing_exact_object")
    scan_allowed = runtime.context.get("scan_allowed_categories", set())
    if scan_allowed and category not in scan_allowed:
        return rejected({
            "error": f"category {category} is not supported by the initial extraction scan",
            "scan_allowed_categories": sorted(scan_allowed),
        }, "category_not_present_in_extraction")
    duplicate = _claim_category(runtime, family, category)
    if duplicate:
        return rejected({"error": duplicate}, "duplicate_category")
    lookup_detail = {
        "specialist": specialist,
        "tool": f"lookup_{family}_clues",
        "category": category,
        "object_observation": object_observation,
        "justification": justification.strip(),
    }
    version = _version(runtime)
    cache = runtime.context.get("tool_response_cache")
    key = json.dumps(
        {"version": version, "family": family, "category": category, "country": country},
        sort_keys=True,
        ensure_ascii=False,
    )
    if isinstance(cache, ToolResponseCache):
        cached, cache_error = cache.get(key)
        if cache_error:
            if callable(progress):
                progress(f"{family} lookup {category}: cache capacity reached")
            return rejected(
                {"warning": cache_error, "category": category},
                "cache_read_capacity",
            )
        if cached is not None:
            if callable(progress):
                progress(f"{family} lookup {category}: cache hit")
            runtime.context.setdefault("reference_lookup_details", []).append(lookup_detail)
            record_decision(
                runtime.context,
                "reference_lookup_completed",
                "Specialist received deterministic cached reference rows.",
                tool=f"lookup_{family}_clues",
                specialist=specialist,
                category=category,
                object_observation=object_observation,
                source="per_run_cache",
                row_count=len(cached),
                reason_code="validated_cache_hit",
            )
            return cached
    if callable(progress):
        progress(f"{family} lookup {category}: querying reference database")
    response = _repository(runtime).lookup_references(
        version=version, category=category, country=country
    )
    runtime.context.setdefault("reference_lookup_details", []).append(lookup_detail)
    if isinstance(cache, ToolResponseCache):
        cache.put(key, response)
    record_decision(
        runtime.context,
        "reference_lookup_completed",
        "Specialist received deterministic versioned reference rows.",
        tool=f"lookup_{family}_clues",
        specialist=specialist,
        category=category,
        object_observation=object_observation,
        source="reference_repository",
        row_count=len(response),
        reason_code="validated_reference_query",
    )
    return response


@tool
def lookup_universal_clues(
    category: UniversalCategory,
    justification: str,
    object_observation: str,
    runtime: ToolRuntime[GeoContext, GeoState],
    country: str | None = None,
) -> list[dict]:
    """Look up a universal clue category shared by urban and rural specialists."""
    return _lookup(
        category=category,
        allowed={"driving_side", "license_plates", "road_markings", "language_script", "country_domains", "bollards", "chevrons_guardrails", "vehicles"},
        family="universal",
        runtime=runtime,
        country=country,
        justification=justification,
        object_observation=object_observation,
    )


@tool
def lookup_urban_clues(
    category: UrbanCategory,
    justification: str,
    object_observation: str,
    runtime: ToolRuntime[GeoContext, GeoState],
    country: str | None = None,
) -> list[dict]:
    """Look up one complete urban-built-environment category."""
    return _lookup(
        category=category,
        allowed={"urban_architecture", "urban_utility_poles", "urban_signage", "street_names_addresses", "businesses_domains", "sidewalks_curbs", "public_transit"},
        family="urban",
        runtime=runtime,
        country=country,
        justification=justification,
        object_observation=object_observation,
    )


@tool
def lookup_rural_clues(
    category: RuralCategory,
    justification: str,
    object_observation: str,
    runtime: ToolRuntime[GeoContext, GeoState],
    country: str | None = None,
) -> list[dict]:
    """Look up one complete rural landscape and low-density-settlement category."""
    return _lookup(
        category=category,
        allowed={"soil_geology", "vegetation_biomes", "terrain_scenery", "climate", "agriculture_land_use", "rural_architecture", "rural_utility_poles", "rural_roadside_features"},
        family="rural",
        runtime=runtime,
        country=country,
        justification=justification,
        object_observation=object_observation,
    )


def urban_reference_tools() -> list:
    return [lookup_universal_clues, lookup_urban_clues]


def rural_reference_tools() -> list:
    return [lookup_universal_clues, lookup_rural_clues]


def reference_tools() -> list:
    return [lookup_universal_clues, lookup_urban_clues, lookup_rural_clues]


# Compatibility aliases for older callers; production agents use the explicit urban/rural names.
lookup_human_clues = lookup_urban_clues
lookup_environmental_clues = lookup_rural_clues
human_reference_tools = urban_reference_tools
environmental_reference_tools = rural_reference_tools
