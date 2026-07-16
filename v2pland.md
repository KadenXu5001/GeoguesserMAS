# GeoGuessr Minimal Multi-Agent System — Build Plan

## Objective

Build a defensible multi-agent system (MAS) with LangChain's **Deep Agents framework** that predicts the country of a Mapillary panorama while remaining cheaper than a single Opus baseline on the same visual input. Deep Agents uses the LangGraph runtime underneath, but the orchestrator must be created with `deepagents.create_deep_agent`, not a custom ReAct graph.

The success gate is measured over the frozen evaluation set:

- complete mean inference cost at least **10% lower than Opus**;
- exact country accuracy no more than **5 percentage points below Opus**;
- report image-token cost separately, but use complete inference cost for the pass/fail decision;
- report country-centroid haversine loss as a secondary measure, so geographically close mistakes receive less loss than distant mistakes.

This is not a training project. No model is fine-tuned.

## Core architecture decision

The system is deliberately small:

1. **One extraction preprocessor (not an agent).** One Gemini Flash multimodal call receives four 1024×1024 perspective images rendered from a Mapillary panorama at headings 0°, 90°, 180°, and 270°, each with a 90° field of view. It extracts all visible signals once.
2. **One Deep Agents orchestrator.** A multimodal agent built with `create_deep_agent` reads the extraction and images, uses the framework's built-in `TodoListMiddleware`, and delegates through the framework's `task` tool to at least one and at most the two configured specialists.
3. **Two custom Deep Agents subagents.** An urban subagent covers architecture, poles, signage, addresses, businesses, sidewalks, and transit. A rural subagent covers soil, geology, vegetation, terrain, climate, agriculture, rural architecture, and roadside infrastructure. Both also receive universal lookup tools and return structured responses.
4. **Conditional targeted re-perception.** The orchestrator may request at most one padded crop re-examination when a high-value clue is illegible or decisive candidates remain tied.

The extraction preprocessor and supervisor receive the four images. Specialists receive the supervisor's compact description and evidence, not image bytes. The optional re-examination call receives only one targeted crop.

This is defensibly multi-agent because the Deep Agents supervisor selectively delegates an unresolved subproblem through `task` to an isolated custom subagent with its own prompt, role, tools, and structured response, then integrates the returned conclusion. The extractor and deterministic tools are not counted as agents.

Deep Agents normally supplies an automatic `general-purpose` subagent. Disable it with a harness profile using `GeneralPurposeSubagentProfile(enabled=False)` so only the two explicitly designed specialists are available and the framework cannot silently expand call count. Keep required `FilesystemMiddleware` scaffolding, but hide its `ls`, `read_file`, `write_file`, `edit_file`, `glob`, and `grep` tools. Exclude optional `SummarizationMiddleware`. Keep `TodoListMiddleware` and `SubAgentMiddleware` enabled.

## Cost-control contract

The MAS is allowed to exist only if it can preserve the cost advantage over Opus. Enforce these constraints in code rather than relying on prompts:

- exactly one full-scene extraction call containing the four headings;
- at least one and at most two specialist invocations per panorama, with each configured specialist used at most once;
- reference-tool responses persisted in the local Deep Agents filesystem cache, with no more than three total cache reads per run; specialist calls are never replaced by cache hits;
- immediate warning/suggestion termination with no further API calls after three minutes or $0.50;
- specialists and orchestrator receive text only;
- at most one crop re-examination per panorama;
- hard agent-iteration and output-token limits;
- compact structured extraction and specialist responses;
- universal, urban, and rural reference tables loaded behind ordinary lookup tools, not copied wholesale into prompts or delegated to more subagents;
- identical four-heading inputs for the Opus baseline;
- complete cost includes extraction, every orchestrator turn, specialist calls, re-examination, and all input/output tokens.

Start with Gemini Flash for extraction, specialists, and the orchestrator. Run a Gemini Pro orchestrator only as an ablation if Flash cannot meet the accuracy gate.

## Phase 0 cost gate

Before pipeline implementation, build `docs/cost_model.md` with current model IDs, image-token rules, and prices. Model at least these paths:

| System/path | Visual calls | Text-agent calls |
| --- | --- | --- |
| Opus baseline | Four headings in one call | None |
| MAS easy path | Four headings in one Flash extraction | Short orchestrator path; no specialist |
| MAS delegated path | Four headings in one Flash extraction | Orchestrator + one Flash specialist + final orchestration |
| MAS hard path | Full extraction + one crop | Orchestrator + one or two specialists + final orchestration |
| Single-agent ablation | Four headings in one Flash extraction | One deep agent; no specialists |

Use complete dollar cost per panorama as the primary cost figure. Also report image tokens, text input/output tokens, call count, and latency. If modeled normal-path MAS cost is not at least 10% below Opus, simplify before building.

## Deep Agents architecture

```text
Mapillary panorama
        |
        v
Render four 1024x1024 cardinal headings
        |
        v
Extraction preprocessor (one Flash vision call; not an agent)
        |
        v
Deep Agents orchestrator (multimodal, built-in todolist middleware)
        |
        +---- answer directly -------------------------------+
        |                                                    |
        +---- delegate to one or both specialists             |
        |       |                                            |
        |       +-- Human-clue agent (text-only)              |
        |       +-- Environmental agent (text-only)           |
        |                                                    |
        +---- optional one crop re-examination                |
        |                                                    |
        +----------------------------------------------------+
                                                             v
                                                   country prediction
```

The orchestrator must delegate to at least one specialist, may call both when their clue families are independently useful, and records the choices in the trace. Each task names the extraction signal, visible observation, and unresolved question that justify the delegation. Specialists must justify every reference lookup from that evidence. It must never call the same specialist twice. Custom middleware must enforce the two-specialist maximum and one total `reexamine_region` call; prompt instructions alone are insufficient.

## Shared state

```python
from typing import Annotated, TypedDict
from operator import add
from langgraph.graph import add_messages

class GeoState(TypedDict):
    panorama_id: str
    panorama_path: str
    heading_paths: list[str]
    extraction_output: dict
    agent_todolist: dict
    specialists_used: list[str]
    specialist_results: list[dict]
    reexamine_results: Annotated[list, add]
    final_prediction: dict
    messages: Annotated[list, add_messages]
    usage: Annotated[list, add]
```

Deep Agents' `TodoListMiddleware` owns planning state, and the orchestrator must use it during every run. Runtime context/state carries extraction data, usage, selected specialist, and crop results to tools and subagents. `emit_prediction` writes the final country prediction and terminates successfully. Custom middleware enforces delegation, crop, iteration, and token budgets around framework model/tool calls.

## Extraction preprocessor

The extractor receives all four cardinal views together and returns arrays for object categories so multiple detected signs, plates, bollards, or other objects are preserved. It then produces a consolidated `signal` per category representing the model's best interpretation of all detected instances.

Each detected object contains:

- heading and bounding box;
- raw observation;
- confidence;
- legibility;
- optional text transcription.

Each category contains `objects: [...]` plus a consolidated `signal`. Distinguish `not_present`, `not_detected`, and `present_but_illegible`. Normalize all boxes to one documented coordinate convention and pad crops by approximately 25%.

The extraction schema covers at least:

- driving side and road markings;
- signs and written language;
- vehicles and plates;
- bollards, utility poles, and infrastructure;
- terrain, vegetation, and climate;
- architecture and settlement character.

## Agents

### Orchestrator

The `create_deep_agent` orchestrator owns the framework todolist and final answer. It:

1. reads the consolidated extraction;
2. applies hard geographic constraints;
3. decides whether it can answer directly;
4. invokes at least one and at most two custom specialists through the built-in `task` tool for deeper reasoning, with each specialist used at most once;
5. optionally requests one crop re-examination if a decisive clue is illegible or candidates are tied;
6. emits one country, confidence, alternatives, and concise evidence.

The model may predict any country worldwide; it is not shown a closed candidate list.

### Urban subagent

Reasons over extracted urban architecture, utility poles, signage, addresses, businesses, sidewalks, and transit, with access to universal clues. It may query curated GeoTips/GeoHints-derived reference tables. It returns ranked country candidates, evidence, contradictions, and confidence.

### Rural subagent

Reasons over extracted soil, geology, vegetation, terrain, climate, agriculture, rural architecture, and roadside infrastructure, with access to universal clues. It may query curated rural reference tables. It returns ranked country candidates, evidence, contradictions, and confidence.

### Re-examination

`reexamine_region` crops one object from one heading, pads the box by approximately 25%, and asks one specific visual question. It is a tool-backed perception call, not another agent. The hard budget is one invocation per panorama.

## Reference data

Build curated, versioned reference tables from GeoTips and <https://geohints.com/meta>. Record source URLs and retrieval dates. Do not copy entire sites into prompts. Normalize information into compact tables for indicators such as:

- bollards and delineators;
- plate formats;
- road markings and driving side;
- utility poles;
- language/script and sign conventions;
- architecture, vegetation, and environmental indicators.

Freeze the reference-data version before the final evaluation run.

## Dataset

### Source and rendering

Use only Mapillary records where `is_pano=true` at the image level. Download the panorama, then render four 1024×1024 perspective images with 90° field of view at headings 0°, 90°, 180°, and 270°.

Mapillary latitude/longitude remains evaluation metadata and must never enter model-facing payloads. Determine the ground-truth country from coordinates using a geocoder or geographic boundary lookup. Preserve the original coordinates for haversine scoring.

### Country selection and sample counts

Select at least 20 countries across at least five continents using a coverage-driven scan. A country qualifies only if the pipeline can collect at least:

- 10 development panoramas;
- 5 evaluation panoramas;
- all retained panoramas at least 10 km apart.

This produces a minimum of 300 panoramas and 1,200 rendered heading images. Keep every panorama and all four of its headings within one split. No Mapillary sequence may cross splits.

Before collecting the full dataset, build a production-shaped pilot for France, Thailand, and Brazil. Apply the final rules without relaxation: collect exactly 10 development and 5 evaluation panoramas per pilot country, replace every rejected or failed candidate, maintain 10 km separation, and prevent sequence leakage across splits. Review this 45-panorama pilot before expanding collection to the full frozen taxonomy.

Store ingestion and dataset metadata in local MongoDB, configured with `MONGODB_URI` so the same repository layer can later target MongoDB Atlas. Keep panorama files and rendered headings on disk; MongoDB stores paths, checksums, source metadata, validation history, split membership, and dataset-version records. Resolve coordinate ground truth with a pinned offline country-boundary dataset rather than a network geocoder.

Create independently stratified, reproducible files:

- `dev_v1.csv`: 10 panoramas per country for prompt and policy tuning;
- `eval_c1.csv`: 5 panoramas per country, frozen before tuning and used only for final evaluation.

After distance and sequence deduplication, a seeded random allocation is acceptable; separate geographic regions between splits are not required. Never use `eval_c1.csv` for prompt/schema development.

## Evaluation

### Primary metrics and gates

- **Exact country accuracy:** primary quality metric.
- **Complete mean inference cost per panorama:** primary cost metric and success gate.
- **Country-centroid haversine loss:** distance from the predicted country's chosen centroid to the ground-truth coordinates; secondary metric rewarding geographically closer errors.
- **Image-token cost:** separately reported diagnostic.
- **Latency, call count, specialist-use rate, and re-examination rate:** operational diagnostics.

The MAS succeeds if it is at least 10% cheaper than Opus in complete mean inference cost and is within five percentage points of Opus exact country accuracy. Larger cost savings and smaller accuracy loss are better.

### Baselines and ablations

All visual baselines receive the exact same four 1024×1024 headings:

1. single Flash multimodal call;
2. single Gemini Pro multimodal call;
3. single Opus multimodal call (the external cost/accuracy target);
4. single deep-agent system using the same extractor but no specialist agents;
5. minimal MAS;
6. minimal MAS without re-examination;
7. optional minimal MAS with a Pro orchestrator, only if Flash accuracy is inadequate.

Use the same country-output schema and prompt requirements across direct multimodal baselines where possible. Do not create visual-signal evaluation subsets in v1. Signals and selected specialists may be logged as diagnostics, but they are not ground-truth annotations.

## Build order

### Phase 0 — Validate economics and image handling

- Confirm current model IDs, availability, tokenization, and pricing.
- Build the complete cost model and enforce the 10%-below-Opus gate.
- Confirm panorama download and four-heading rendering.
- Confirm bbox format and crop accuracy on development-only samples.
- Run a Mapillary coverage scan and freeze the 20+ country taxonomy.

### Phase 1 — Build the dataset

- Implement local MongoDB collections, indexes, validation, and dataset-version records; keep image bytes on disk.
- Implement Mapillary pagination, tiling, backoff, downloads, and MongoDB-backed failure history.
- Resolve coordinates to country labels with a pinned offline boundary dataset.
- Enforce 10 km separation and sequence isolation.
- Render four cardinal views per panorama.
- First create the strict France/Thailand/Brazil pilot with 10 development and 5 evaluation panoramas per country; replace invalid samples until all 45 slots are filled.
- Review the pilot before expanding to all 20 countries and creating final `dev_v1.csv` and frozen `eval_c1.csv` manifests.
- Verify metadata cannot leak into model payloads.

### Phase 2 — Build the minimal MAS

- Add and pin `deepagents`; validate `create_deep_agent` with the Gemini integration.
- Implement runtime context, usage accounting, and cost middleware around the Deep Agents graph.
- Implement and validate the multi-object extraction schema.
- Build and freeze curated reference tables.
- Configure the two text-only custom subagents with narrow tools and structured response schemas.
- Create the orchestrator with `create_deep_agent`, built-in todo middleware, the two custom subagents, and no automatic general-purpose subagent.
- Add custom middleware enforcing at most one `task` delegation, one crop, two orchestrator turns, and the runtime cost cutoff.
- Add the one-call crop re-examination tool.
- Verify via traces that no specialist receives images and both hard budgets hold.

### Phase 3 — Evaluate

- Implement identical-input direct baselines.
- Implement country accuracy, country-centroid haversine loss, and complete cost accounting.
- Tune only on `dev_v1.csv`.
- Freeze prompts, models, policies, and reference data.
- Run each final system once over `eval_c1.csv` and compare gates.

### Phase 4 — Polish

- Add a CLI that shows the todolist, chosen specialist, re-examination count, country prediction, cost, and LangSmith trace URL.
- Document setup, dataset creation, evaluation, limitations, and measured results.
- Defer the web UI until after the evaluation gates pass.

## Resolved decisions

- Minimal MAS: one multimodal Deep Agents orchestrator plus two possible custom text-only subagents.
- Use the `deepagents` Python package and `create_deep_agent`; do not substitute a hand-built ReAct loop.
- Disable Deep Agents' automatic general-purpose subagent.
- Hide unused filesystem tools and disable summarization while retaining the required filesystem, todo, and subagent middleware scaffolding.
- At least one specialist is invoked per panorama; both configured specialists may be used once when their clue families are independently useful.
- Specialist calls are never cached or replaced. Only deterministic reference-tool responses may be cached and read no more than three times.
- One non-agent extraction call sees four cardinal headings together.
- One optional targeted crop call is allowed.
- Predictions are worldwide and country-level.
- Dataset uses 10 dev and 5 eval panoramas per country across 20+ countries and 5+ continents.
- Panoramas are at least 10 km apart; sequences cannot cross splits.
- Exact country accuracy is primary; centroid-based haversine loss is secondary.
- Complete inference cost determines the cost gate; image-token cost is also reported.
- Signal-subset annotation is deferred from v1.

## Remaining empirical decisions

These do not block planning and must be settled from the cost model or development experiments:

- exact model IDs and provider prices;
- orchestrator iteration and output-token caps;
- precise trigger for selecting one or both specialists and one re-examination;
- country list after the Mapillary coverage scan;
- country centroid dataset used for secondary scoring;
- whether the optional Pro-orchestrator ablation is necessary.

## Resume / interview framing

Target claim, filled only with measured results:

> Built a cost-gated geolocation MAS with LangChain's Deep Agents framework: one multimodal perception pass, a built-in-todolist supervisor, selective `task` delegation to one of two isolated text-only subagents, and one conditional crop re-examination. On N held-out Mapillary panoramas across C countries, it achieved X% country accuracy at Y% lower complete inference cost than an identical-input Opus baseline.

The honest engineering story is that multi-agent fan-out was rejected. The system uses the smallest architecture that is genuinely multi-agent while preventing specialists from duplicating expensive image processing.
