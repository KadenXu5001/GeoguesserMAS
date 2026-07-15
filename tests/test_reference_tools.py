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
        }
    )


def test_specialist_tools_query_only_allowed_categories() -> None:
    assert lookup_universal_clues.func("driving_side", "road lines imply right-side traffic", runtime(), "Thailand")[0]["version"] == "reference-v1"
    assert lookup_rural_clues.func("rural_architecture", "low-density roadside homes are visible", runtime(), "Thailand")[0]["category"] == "rural_architecture"


def test_specialist_tools_batch_a_category_when_country_is_omitted() -> None:
    result = lookup_rural_clues.func("vegetation_biomes", "palms and dry grassland are visible", runtime())
    assert result[0]["category"] == "vegetation_biomes"
    assert result[0]["country"] is None


def test_specialist_tools_reject_repeated_category_lookup() -> None:
    context = runtime()
    lookup_rural_clues.func("vegetation_biomes", "palms and dry grassland are visible", context)
    result = lookup_rural_clues.func("vegetation_biomes", "palms and dry grassland are visible", context)
    assert "already looked up" in result[0]["error"]


def test_unsupported_specialist_category_returns_recoverable_tool_feedback() -> None:
    result = lookup_rural_clues.func("infrastructure", "a utility structure is visible", runtime())
    assert result[0]["error"].startswith("unsupported rural category")
    assert "rural_architecture" in result[0]["allowed_categories"]


def test_lookup_requires_evidence_justification() -> None:
    result = lookup_rural_clues.func("soil_geology", "", runtime())
    assert "justification" in result[0]["error"]
