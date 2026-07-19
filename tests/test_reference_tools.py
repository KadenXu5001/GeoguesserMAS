from types import SimpleNamespace

from geoguesser.reference_tools import lookup_rural_clues, lookup_universal_clues


def runtime() -> SimpleNamespace:
    class Repository:
        def lookup_references(self, *, version, category, country=None):
            return [{"version": version, "category": category, "country": country}]

    return SimpleNamespace(
        context={
            "reference_repository": Repository(),
            "reference_version": "reference-v1",
            "scan_objects": {
                "driving_side": {"double yellow center line"},
                "rural_architecture": {"low-density roadside homes"},
                "vegetation_biomes": {"palms and dry grassland"},
                "soil_geology": {"visible soil"},
            },
            "active_specialist": "rural-specialist",
            "specialist_tool_calls": {},
        }
    )


def test_specialist_tools_query_only_allowed_categories() -> None:
    context = runtime()
    assert lookup_universal_clues.func("driving_side", "double yellow center line implies right-side traffic", "double yellow center line", context, "Thailand")[0]["version"] == "reference-v1"
    assert context.context["reference_lookup_details"] == [{
        "specialist": "rural-specialist",
        "tool": "lookup_universal_clues",
        "category": "driving_side",
        "object_observation": "double yellow center line",
        "justification": "double yellow center line implies right-side traffic",
    }]
    assert lookup_rural_clues.func("rural_architecture", "low-density roadside homes are visible", "low-density roadside homes", runtime(), "Thailand")[0]["category"] == "rural_architecture"


def test_specialist_tools_batch_a_category_when_country_is_omitted() -> None:
    result = lookup_rural_clues.func("vegetation_biomes", "palms and dry grassland are visible", "palms and dry grassland", runtime())
    assert result[0]["category"] == "vegetation_biomes"
    assert result[0]["country"] is None


def test_specialist_tools_reject_repeated_category_lookup() -> None:
    context = runtime()
    lookup_rural_clues.func("vegetation_biomes", "palms and dry grassland are visible", "palms and dry grassland", context)
    result = lookup_rural_clues.func("vegetation_biomes", "palms and dry grassland are visible", "palms and dry grassland", context)
    assert "already looked up" in result[0]["error"]


def test_unsupported_specialist_category_returns_recoverable_tool_feedback() -> None:
    result = lookup_rural_clues.func("infrastructure", "a utility structure is visible", "visible utility structure", runtime())
    assert result[0]["error"].startswith("unsupported rural category")
    assert "rural_architecture" in result[0]["allowed_categories"]


def test_lookup_requires_evidence_justification() -> None:
    result = lookup_rural_clues.func("soil_geology", "", "visible soil", runtime())
    assert "justification" in result[0]["error"]


def test_lookup_rejects_object_not_in_supervisor_extraction() -> None:
    result = lookup_rural_clues.func(
        "soil_geology", "this object supports a soil lookup", "power pylon", runtime()
    )
    assert "exact object observation" in result[0]["error"]


def test_specialist_lookup_cap_is_three_tools() -> None:
    context = runtime()
    for observation in ("visible soil", "palms and dry grassland", "low-density roadside homes"):
        lookup_rural_clues.func("soil_geology" if observation == "visible soil" else "vegetation_biomes" if observation == "palms and dry grassland" else "rural_architecture", "specific evidence supports this lookup", observation, context)
    result = lookup_rural_clues.func("soil_geology", "specific evidence supports this lookup", "visible soil", context)
    assert "cap reached" in result[0]["warning"]
