from pathlib import Path

import pytest

from geoguesser.agent_runtime import build_runtime_context
from geoguesser.runtime_budget import RuntimeBudget


def test_build_runtime_context_keeps_operational_values_in_context() -> None:
    repository = object()
    context = build_runtime_context(
        budget=RuntimeBudget(opus_cost_usd=1.0),
        reference_repository=repository,
        reference_version="reference-v1",
        heading_paths={heading: Path(f"h{heading}.jpg") for heading in (0, 90, 180, 270)},
        gemini_client=object(),
    )

    assert context["reference_repository"] is repository
    assert set(context["heading_paths"]) == {0, 90, 180, 270}


def test_build_runtime_context_requires_all_headings() -> None:
    with pytest.raises(ValueError, match="four cardinal"):
        build_runtime_context(
            budget=RuntimeBudget(opus_cost_usd=1.0),
            reference_repository=object(),
            reference_version="reference-v1",
            heading_paths={0: Path("h0.jpg")},
            gemini_client=object(),
        )
