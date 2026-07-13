from types import SimpleNamespace

from geoguesser.reference_tools import lookup_human_clues, lookup_environmental_clues


def runtime() -> SimpleNamespace:
    return SimpleNamespace(
        context={
            "reference_snapshot": {
                "rows": [
                    {"category": "driving_side", "country": "Thailand", "indicator": "left"},
                    {"category": "architecture", "country": "Thailand", "indicator": "raised homes"},
                ]
            }
        }
    )


def test_specialist_tools_query_only_allowed_categories() -> None:
    assert lookup_human_clues.func("driving_side", "Thailand", runtime())[0]["indicator"] == "left"
    assert lookup_environmental_clues.func("architecture", "Thailand", runtime())[0]["indicator"] == "raised homes"
