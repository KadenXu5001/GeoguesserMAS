# GeoGuessr Minimal Multi-Agent System — Build Plan

## Objective

Build a defensible LangGraph multi-agent system (MAS) that predicts the country of a Mapillary panorama while remaining cheaper than a single Opus baseline on the same visual input.

The success gate is measured over the frozen evaluation set:

- complete mean inference cost at least **10% lower than Opus**;
- exact country accuracy no more than **5 percentage points below Opus**;
- report image-token cost separately, but use complete inference cost for the pass/fail decision;
- report country-centroid haversine loss as a secondary measure, so geographically close mistakes receive less loss than distant mistakes.

This is not a training project. No model is fine-tuned.

## Core architecture decision

The system is deliberately small:

1. **One extraction preprocessor (not an agent).** One Gemini Flash multimodal call receives four 1024×1024 perspective images rendered from a Mapillary panorama at headings 0°, 90°, 180°, and 270°, each with a 90° field of view. It extracts all visible signals once.
2. **One orchestrator agent.** A text-only ReAct agent reads the extraction, maintains a mandatory dynamic todolist, decides whether it can answer directly, and may delegate to at most one specialist.
3. **Two possible specialist agents.** A human-clue specialist covers language, signs, vehicles, plates, roads, and infrastructure. An environmental specialist covers terrain, climate, vegetation, and architecture. Both are text-only and use Gemini Flash plus curated reference tools.
4. **Conditional targeted re-perception.** The orchestrator may request at most one padded crop re-examination when a high-value clue is illegible or decisive candidates remain tied.

Only the extraction preprocessor normally receives images. Specialists never receive image bytes. The optional re-examination call receives only one targeted crop.

This is defensibly multi-agent because the orchestrator selectively delegates an unresolved subproblem to an autonomous specialist with its own prompt, role, and tools, then integrates the returned conclusion. The extractor and deterministic tools are not counted as agents.

## Cost-control contract

The MAS is allowed to exist only if it can preserve the cost advantage over Opus. Enforce these constraints in code rather than relying on prompts:

- exactly one full-scene extraction call containing the four headings;
- zero or one specialist invocation per panorama;
- specialists and orchestrator receive text only;
- at most one crop re-examination per panorama;
- hard agent-iteration and output-token limits;
- compact structured extraction and specialist responses;
- reference tables loaded behind lookup tools, not copied wholesale into every prompt;
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
| MAS hard path | Full extraction + one crop | Orchestrator + at most one specialist + final orchestration |
| Single-agent ablation | Four headings in one Flash extraction | One deep agent; no specialists |

Use complete dollar cost per panorama as the primary cost figure. Also report image tokens, text input/output tokens, call count, and latency. If modeled normal-path MAS cost is not at least 10% below Opus, simplify before building.

## LangGraph architecture

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
Orchestrator agent (text-only, mandatory dynamic todolist)
        |
        +---- answer directly -------------------------------+
        |                                                    |
        +---- delegate to at most one specialist             |
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

The orchestrator chooses agentically whether delegation or re-examination is warranted and records the reason in the trace. It must never call both specialists in v1.

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
    specialist_used: str | None
    specialist_result: dict | None
    reexamine_results: Annotated[list, add]
    final_prediction: dict
    messages: Annotated[list, add_messages]
    usage: Annotated[list, add]
```

Agent tools mutate injected state using `InjectedState`. The orchestrator must update its todolist during every run. `emit_prediction` writes the final country prediction and terminates the graph successfully. Enforce delegation, crop, iteration, and token budgets in nodes/tools.

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

The orchestrator owns the dynamic todolist and final answer. It:

1. reads the consolidated extraction;
2. applies hard geographic constraints;
3. decides whether it can answer directly;
4. invokes zero or one specialist if a particular clue family needs deeper reasoning;
5. optionally requests one crop re-examination if a decisive clue is illegible or candidates are tied;
6. emits one country, confidence, alternatives, and concise evidence.

The model may predict any country worldwide; it is not shown a closed candidate list.

### Human-clue specialist

Reasons over extracted language, signs, vehicles, plates, roads, bollards, utility poles, and infrastructure. It may query the curated GeoTips/GeoHints-derived reference tables. It returns ranked country candidates, evidence, contradictions, and confidence.

### Environmental specialist

Reasons over extracted terrain, vegetation, climate, architecture, and settlement patterns. It may query curated environmental and architectural reference tables. It returns ranked country candidates, evidence, contradictions, and confidence.

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

- Implement Mapillary pagination, tiling, backoff, downloads, and SQLite metadata.
- Geocode coordinates to country labels.
- Enforce 10 km separation and sequence isolation.
- Render four cardinal views per panorama.
- Create `dev_v1.csv` and frozen `eval_c1.csv` with the required per-country counts.
- Verify metadata cannot leak into model payloads.

### Phase 2 — Build the minimal MAS

- Implement state, usage accounting, and graph budgets.
- Implement and validate the multi-object extraction schema.
- Build and freeze curated reference tables.
- Implement the two text-only specialists.
- Implement the orchestrator, mandatory todolist, selective zero-or-one delegation, and terminating prediction tool.
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

- Minimal MAS: one orchestrator plus two possible text-only specialists.
- Zero or one specialist is invoked per panorama; never both in v1.
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
- precise trigger for the one specialist and one re-examination;
- country list after the Mapillary coverage scan;
- country centroid dataset used for secondary scoring;
- whether the optional Pro-orchestrator ablation is necessary.

## Resume / interview framing

Target claim, filled only with measured results:

> Built a cost-gated LangGraph multi-agent geolocation system with one multimodal perception pass, a todolist-driven orchestrator, selective delegation to one of two text-only specialists, and one conditional crop re-examination. On N held-out Mapillary panoramas across C countries, it achieved X% country accuracy at Y% lower complete inference cost than an identical-input Opus baseline.

The honest engineering story is that multi-agent fan-out was rejected. The system uses the smallest architecture that is genuinely multi-agent while preventing specialists from duplicating expensive image processing.
