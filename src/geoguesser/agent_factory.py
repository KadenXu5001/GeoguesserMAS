from __future__ import annotations

from deepagents import (
    GeneralPurposeSubagentProfile,
    HarnessProfile,
    create_deep_agent,
    register_harness_profile,
)
from langchain.agents import create_agent
from langchain.agents.middleware import TodoListMiddleware

from geoguesser.budget_middleware import BudgetMiddleware, MAS_TODO_CONTENTS
from geoguesser.geo_tools import geoguesser_tools
from geoguesser.prediction import SpecialistResult
from geoguesser.reference_tools import rural_reference_tools, urban_reference_tools
from geoguesser.runtime_state import GeoState


FLASH_MODEL = "google_genai:gemini-3-flash-preview"


URBAN_SUBAGENT = {
    "name": "urban-specialist",
    "description": (
        "Analyze urban architecture, utility poles, signage, addresses, businesses, sidewalks, "
        "transit, and other built-environment clues."
    ),
    "system_prompt": (
        "You are the urban specialist inside a bounded MAS. Follow this exact procedure: "
        "inspect the supervisor description, select an exact object observation from it, and identify "
        "the lookup category that is directly useful for that object. Pass that exact observation as "
        "object_observation and repeat it in the justification. Make at most three lookups total; "
        "with country omitted, never repeat a category or enumerate country/category pairs, "
        "and if a lookup returns an error or warning, do not retry or make another lookup; "
        "then immediately return exactly one specialist-result-v1 JSON document validated as "
        "SpecialistResult with ranked candidates, evidence, contradictions, "
        "and confidence. Do not call a lookup after you have enough evidence and do not produce "
        "a prose answer outside the JSON document."
    ),
    "tools": urban_reference_tools(),
    "model": FLASH_MODEL,
    "response_format": SpecialistResult,
}


RURAL_SUBAGENT = {
    "name": "rural-specialist",
    "description": (
        "Analyze soil, geology, vegetation, terrain, climate, agriculture, rural architecture, "
        "and low-density roadside infrastructure."
    ),
    "system_prompt": (
        "You are the rural specialist inside a bounded MAS. Follow this exact procedure: "
        "inspect the supervisor description, select an exact object observation from it, and identify "
        "the lookup category that is directly useful for that object. Pass that exact observation as "
        "object_observation and repeat it in the justification. Make at most three lookups total; "
        "category with country omitted, never repeat a category or enumerate country/category "
        "pairs, and if a lookup returns an error or warning, do not retry or make another lookup; "
        "then immediately return exactly one specialist-result-v1 JSON document validated as "
        "SpecialistResult with ranked candidates, evidence, contradictions, and confidence. "
        "Only use rural and universal categories; never query urban "
        "categories. Do not call a lookup after you have "
        "enough evidence and do not produce a prose answer outside the JSON document."
    ),
    "tools": rural_reference_tools(),
    "model": FLASH_MODEL,
    "response_format": SpecialistResult,
}


def _compile_specialist(spec: dict) -> dict:
    """Compile a specialist without Deep Agents' supervisor todo middleware."""
    runnable = create_agent(
        model=spec["model"],
        tools=spec["tools"],
        system_prompt=spec["system_prompt"],
        response_format=spec["response_format"],
        name=spec["name"],
    )
    return {
        "name": spec["name"],
        "description": spec["description"],
        "runnable": runnable,
    }


MAS_TODO_SYSTEM_PROMPT = """## `write_todos`

The todo list is immutable MAS protocol state, not a general-purpose planning aid.

- On the first call, create exactly the four required items from the supervisor instructions,
  in their exact order and wording. Mark only extraction `in_progress`.
- On later calls, submit the same four items in the same order with byte-for-byte identical
  `content`. Change only `status` values, and only forward from `pending` to `in_progress` to
  `completed`.
- Never rename, add, remove, reorder, split, or rewrite an item, even after learning which
  specialist is appropriate.
- A successful extraction completes item 1 and starts item 2. A returned specialist result
  completes item 2; never delegate to that specialist again. Keep optional re-examination
  pending unless two close country signals actually justify it.
- `write_todos` is bookkeeping. Finalize only with `emit_prediction`, never with plain text.
"""

MAS_TODO_TOOL_DESCRIPTION = """Create the required canonical four-item MAS plan once, then update
only its statuses. Every call must preserve all four item strings and their order exactly.
Never add, delete, rename, reorder, or otherwise revise todo content. Statuses may only progress
pending -> in_progress -> completed, and final prediction is completed only by emit_prediction."""


class MASTodoListMiddleware(TodoListMiddleware):
    """Todo middleware whose model guidance matches the immutable MAS protocol."""

    def __init__(self) -> None:
        super().__init__(
            system_prompt=MAS_TODO_SYSTEM_PROMPT,
            tool_description=MAS_TODO_TOOL_DESCRIPTION,
        )


ORCHESTRATOR_PROMPT = """You are the GeoGuessr supervisor in a strictly bounded, one-pass workflow.

You are multimodal. You receive the four cardinal street-scene images. You must call
`extract_visual_evidence` exactly once before using extracted clues, delegating, re-examining, or
predicting. Treat its structured result as a compact first pass, then scan the images yourself to
verify, correct, or add visible evidence. Use the images and extraction together; do not assume
the extraction is complete or correct.

The run has five phases and must move forward; never restart a phase:
1. Call the built-in tool named `write_todos` at the beginning. The initial todo list must contain
   exactly these four items, in exactly this order and with exactly this wording:
   - {todo_1}
   - {todo_2}
   - {todo_3}
   - {todo_4}
   Mark only the first item `in_progress`; mark all three later items `pending`. You may call
   `write_todos` again only to update statuses on these same four items. Do not create a second
   plan, change their wording or order, or use it as a status-check loop.
2. Immediately call the exact tool named `extract_visual_evidence` exactly once. Never call a
   differently named extraction tool, retry it, call it twice, or use a fallback. If it fails, stop;
   do not call another tool.
3. Scan the images, read the extraction description, classify the scene as urban, rural, or mixed,
   and delegate using the exact tool name `task`. The urban specialist handles built
   environments; the rural specialist handles natural and low-density environments. Both have
   universal clue tools. Delegate to both only for a genuinely mixed scene with independent
   unresolved clue families, and never delegate to the same specialist twice. Include the exact
   extraction category/signal, visible observation, and unresolved geographic question in every
   task. The specialist must copy an exact object observation from the extraction verbatim and pass
   it as `object_observation` on every lookup. The category must be directly supported by that
   object. Never invent a category, paraphrase the object, or call another lookup after an error or
   warning.
4. After the specialist result(s), call the exact tool `reexamine_region` at most once, and only when two distinct
   country signals remain genuinely competitive and close in confidence (a score gap of 10 points
   or less). Pass both signals and their scores to the tool. Do not re-examine for a merely
   illegible clue, general curiosity, or a single leading hypothesis. Never retry it or call it
   with different wording for the same conflict.
5. Synthesize the available evidence and finalize immediately by calling the exact tool `emit_prediction` exactly
   once. Never return a plain-text answer and never call any tool after finalization.

Tool-loop rules are absolute: each tool call must make new progress; never repeat any tool call,
never retry a failed or rejected call, never call a tool merely to verify its previous result, and
never emit a plain-text answer instead of the final tool call. Do not request hidden location
metadata. A specialist may use its own bounded lookup tools, but the supervisor must not perform
   lookup-style repetition or ask for additional specialist work after receiving SpecialistResult.
   Lookup categories are allowed only when their clue family is marked present or present-but-
   illegible in the extraction JSON; do not invent unsupported clue families.

The final call must contain exactly one worldwide country, confidence, alternatives, and concise
evidence. If evidence is incomplete or conflicting but no two close signals justify re-examination,
make the best supported prediction and still call `emit_prediction` immediately.""".format(
    todo_1=MAS_TODO_CONTENTS[0],
    todo_2=MAS_TODO_CONTENTS[1],
    todo_3=MAS_TODO_CONTENTS[2],
    todo_4=MAS_TODO_CONTENTS[3],
)


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
            excluded_middleware=frozenset(
                {"SummarizationMiddleware", "TodoListMiddleware"}
            ),
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
    specialists = [_compile_specialist(URBAN_SUBAGENT), _compile_specialist(RURAL_SUBAGENT)]
    return create_deep_agent(
        model=model,
        tools=geoguesser_tools(),
        middleware=[MASTodoListMiddleware(), BudgetMiddleware()],
        system_prompt=ORCHESTRATOR_PROMPT,
        subagents=specialists,
        state_schema=GeoState,
        name="geoguesser-supervisor",
    )


def create_single_agent_ablation(model: str = FLASH_MODEL):
    """Create the original single deep-agent ablation without specialists."""
    register_cost_controlled_profile(model)
    return create_deep_agent(
        model=model,
        tools=geoguesser_tools(),
        middleware=[MASTodoListMiddleware(), BudgetMiddleware()],
        system_prompt=ORCHESTRATOR_PROMPT,
        state_schema=GeoState,
        name="geoguesser-single-agent-ablation",
    )
