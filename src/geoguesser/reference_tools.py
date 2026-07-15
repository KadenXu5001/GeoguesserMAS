from __future__ import annotations

from langchain.tools import ToolRuntime, tool

from geoguesser.runtime_state import GeoContext, GeoState
from geoguesser.tool_response_cache import ToolResponseCache

import json


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
    justification: str,
) -> list[dict]:
    if not justification.strip() or len(justification.strip()) < 12:
        return [{"error": "lookup requires a specific evidence-based justification of at least 12 characters"}]
    progress = runtime.context.get("progress")
    if category not in allowed:
        return [{"error": f"unsupported {family} category: {category}", "allowed_categories": sorted(allowed)}]
    scan_allowed = runtime.context.get("scan_allowed_categories", set())
    if scan_allowed and category not in scan_allowed:
        return [{
            "error": f"category {category} is not supported by the initial extraction scan",
            "scan_allowed_categories": sorted(scan_allowed),
        }]
    duplicate = _claim_category(runtime, family, category)
    if duplicate:
        return [{"error": duplicate}]
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
            return [{"warning": cache_error, "category": category}]
        if cached is not None:
            if callable(progress):
                progress(f"{family} lookup {category}: cache hit")
            return cached
    if callable(progress):
        progress(f"{family} lookup {category}: querying reference database")
    response = _repository(runtime).lookup_references(
        version=version, category=category, country=country
    )
    if isinstance(cache, ToolResponseCache):
        cache.put(key, response)
    return response


@tool
def lookup_universal_clues(
    category: str,
    justification: str,
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
    )


@tool
def lookup_urban_clues(
    category: str,
    justification: str,
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
    )


@tool
def lookup_rural_clues(
    category: str,
    justification: str,
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
