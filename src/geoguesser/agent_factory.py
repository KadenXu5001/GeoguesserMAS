from __future__ import annotations

from pydantic import BaseModel, Field

from deepagents import (
    GeneralPurposeSubagentProfile,
    HarnessProfile,
    create_deep_agent,
    register_harness_profile,
)


FLASH_MODEL = "google_genai:gemini-3-flash-preview"


class SpecialistResult(BaseModel):
    candidates: list[str] = Field(max_length=5)
    evidence: list[str]
    contradictions: list[str]
    confidence: int = Field(ge=0, le=100)


class CountryPrediction(BaseModel):
    country: str
    confidence: int = Field(ge=0, le=100)
    alternatives: list[str] = Field(max_length=3)
    evidence: list[str]


HUMAN_CLUE_SUBAGENT = {
    "name": "human-clue-specialist",
    "description": (
        "Analyze language, signs, vehicles, plates, roads, bollards, utility poles, "
        "and other human-made infrastructure when those clues are decisive."
    ),
    "system_prompt": (
        "You are a country-geolocation specialist for human-made clues. Use only the "
        "structured extraction and supplied reference tools. Return concise ranked "
        "country candidates with evidence, contradictions, and calibrated confidence."
    ),
    "tools": [],
    "model": FLASH_MODEL,
    "response_format": SpecialistResult,
}


ENVIRONMENTAL_SUBAGENT = {
    "name": "environmental-specialist",
    "description": (
        "Analyze terrain, climate, vegetation, architecture, and settlement patterns "
        "when environmental clues are decisive."
    ),
    "system_prompt": (
        "You are a country-geolocation specialist for environmental clues. Use only "
        "the structured extraction and supplied reference tools. Return concise ranked "
        "country candidates with evidence, contradictions, and calibrated confidence."
    ),
    "tools": [],
    "model": FLASH_MODEL,
    "response_format": SpecialistResult,
}


ORCHESTRATOR_PROMPT = """You are the GeoGuessr supervisor.
Use the built-in todo tool on every run. Reason only from the structured extraction and
tool results; never request hidden location metadata. You may answer directly or delegate
exactly one task to either human-clue-specialist or environmental-specialist. Never call
both specialists. Use at most one targeted re-examination. Emit exactly one worldwide
country prediction with concise evidence and calibrated confidence."""


def register_cost_controlled_profile(model: str = FLASH_MODEL) -> None:
    """Register the Deep Agents harness profile used by the project.

    Registration is process-global. Re-registering the same key is harmless in the
    supported Deep Agents release, but this helper remains isolated for easy testing.
    """
    register_harness_profile(
        model,
        HarnessProfile(
            excluded_tools=frozenset(
                {"ls", "read_file", "write_file", "edit_file", "glob", "grep"}
            ),
            excluded_middleware=frozenset({"SummarizationMiddleware"}),
            general_purpose_subagent=GeneralPurposeSubagentProfile(enabled=False),
        ),
    )


def create_geoguesser_agent(model: str = FLASH_MODEL):
    """Construct the official LangChain Deep Agents supervisor graph.

    Cost-enforcement middleware and production tools are added in the core-build phase.
    This factory already constrains the available subagent set and output schemas,
    and hides filesystem tools plus summarization behavior that this short inference
    path does not need. FilesystemMiddleware itself remains enabled because Deep
    Agents requires it as subagent scaffolding.
    """
    register_cost_controlled_profile(model)
    return create_deep_agent(
        model=model,
        tools=[],
        system_prompt=ORCHESTRATOR_PROMPT,
        subagents=[HUMAN_CLUE_SUBAGENT, ENVIRONMENTAL_SUBAGENT],
        response_format=CountryPrediction,
        name="geoguesser-supervisor",
    )
