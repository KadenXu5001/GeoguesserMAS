# Backlog

## Current Objective

Build and evaluate the smallest defensible GeoGuessr MAS using LangChain's Deep Agents framework: one non-agent Flash extraction call over four cardinal panorama views, one `create_deep_agent` orchestrator with built-in todo middleware, selective `task` delegation to at most one of two custom text-only subagents, and at most one targeted crop re-examination. The final system must cost at least 10% less than an identical-input Opus baseline while remaining within five percentage points of its exact country accuracy.

## Now

- [x] Configure `.env` with Mapillary, Gemini, and LangSmith credentials.
- [x] Add `.env` to `.gitignore` and verify it is not tracked.
- [x] Pin the initial Python dependencies.
- [x] Register the Mapillary app and LangSmith project.
- [x] Confirm candidate Gemini model availability through `langchain-google-genai`.
- [x] Create `docs/cost_model.md` using current model IDs, tokenization rules, and prices.
- [x] Model complete per-panorama cost for Opus, MAS easy/delegated/hard paths, and the single-agent ablation.
- [x] Set initial enforceable orchestrator iteration/output-token caps from the cost model.
- [x] **Modeled gate:** normal, delegated, and hard MAS paths estimate at least 10% below identical-input Opus; revalidate with measured usage.
- [x] Build a standalone panorama renderer for four 1024×1024, 90° FOV views at headings 0°, 90°, 180°, and 270°.
- [x] Confirm Gemini bbox convention as normalized `[ymin, xmin, ymax, xmax]` from current official documentation.
- [ ] Visually validate padded crops on 3–5 development-only panoramas with the production Gemini model (1/3 inspected successfully; remaining calls blocked by temporary 503s).
- [x] Scan Mapillary coverage and select at least 20 qualifying countries across at least five continents.
- [x] Record the selected country taxonomy and continent mapping in `data/taxonomy.json`.
- [x] Install and pin `deepagents==0.6.12`; validate `create_deep_agent` against the pinned LangGraph/LangChain-Google dependencies.
- [x] Create a minimal Deep Agents construction smoke test using Gemini without invoking a paid model call.

## Next

- [ ] Implement the SQLite image/panorama metadata schema.
- [ ] Implement the Mapillary client with image-level `is_pano=true`, cursor pagination, tiling, retry/backoff, and failure logging.
- [ ] Download panorama files and fetch expiring image URLs only when needed.
- [ ] Resolve latitude/longitude to ground-truth country using a geographic boundary lookup or geocoder.
- [ ] Enforce at least 10 km separation between retained panoramas within each country.
- [ ] Prevent any Mapillary sequence from crossing dev/eval splits.
- [ ] Collect 10 development and 5 evaluation panoramas per qualifying country.
- [ ] Render and store four cardinal views for every retained panorama.
- [ ] Create independently stratified `dev_v1.csv` with 10 panoramas per country.
- [ ] Create and freeze `eval_c1.csv` with 5 panoramas per country.
- [ ] Verify no latitude, longitude, timestamp, filename clue, or other metadata reaches model-facing inputs.
- [ ] Define Deep Agents runtime context/state for extraction, usage, delegation, re-examination, and final prediction.
- [ ] Implement custom Deep Agents middleware for zero-or-one `task` delegation, one crop call, two orchestrator turns, output-token limits, and the 90%-of-Opus cutoff.
- [ ] Implement the extraction preprocessor: one Flash call containing all four headings.
- [ ] Define and validate the extraction schema with arrays of detected objects plus one consolidated signal per category.
- [ ] Distinguish `not_present`, `not_detected`, and `present_but_illegible`; normalize bbox coordinates.
- [ ] Add bounded malformed-output repair/retry behavior.
- [ ] Build versioned reference tables from GeoTips and GeoHints with source URLs and retrieval dates.
- [ ] Implement compact lookup tools for human and environmental indicators.
- [ ] Configure the human-clue custom subagent with a narrow prompt, tools, and structured response.
- [ ] Configure the environmental custom subagent with a narrow prompt, tools, and structured response.
- [ ] Implement the orchestrator with `create_deep_agent`, built-in `TodoListMiddleware`, and agent-decided zero-or-one `task` delegation.
- [x] Disable the automatic `general-purpose` subagent with `GeneralPurposeSubagentProfile(enabled=False)`.
- [x] Keep required filesystem/todo/subagent middleware, hide unused filesystem tools, and exclude summarization middleware in the harness profile.
- [ ] Make Deep Agents tools use runtime context/state consistently.
- [ ] Implement `emit_prediction` to write one worldwide country prediction and terminate successfully.
- [ ] Implement one-call `reexamine_region` with heading-aware padded cropping and a specific visual question.
- [ ] Verify in LangSmith that specialists and the orchestrator never receive full image bytes.
- [ ] Verify in tests/traces that both delegation and re-examination hard caps cannot be exceeded.
- [ ] Implement direct Flash, Gemini Pro, and Opus baselines using identical four-heading inputs.
- [ ] Implement the original single deep-agent ablation without specialists.
- [ ] Implement exact country accuracy, country-centroid haversine loss, complete cost, image-token cost, latency, and call-count metrics.
- [ ] Tune prompts and policies only on `dev_v1.csv`.
- [ ] Freeze prompts, models, policies, and reference tables before final evaluation.
- [ ] Run all frozen systems over `eval_c1.csv` and determine whether the MAS passes both gates.

## Later

- [ ] Run the MAS without re-examination as an ablation.
- [ ] Run a Gemini Pro orchestrator ablation only if the Flash orchestrator misses the accuracy gate.
- [ ] Add a CLI showing todolist, selected specialist, re-examination count, country, confidence, cost, and LangSmith trace URL.
- [ ] Document setup, ingestion, evaluation, limitations, and measured results in the README.
- [ ] Build a streamed web UI only after the cost and accuracy gates pass.
- [ ] Consider manually annotated visual-signal subsets in a later evaluation version.

## Blocked

- [ ] Production-model bbox visual validation — blocked by temporary 503 responses from both Gemini 3 Flash endpoints; panorama download/rendering and crop math are already verified.
- [ ] Final iteration and token budgets — blocked on measured development-set token usage; initial caps are documented.
- [ ] Final specialist/re-examination triggers — blocked on development-set experiments.
- [ ] Pro-orchestrator decision — blocked until the Flash-orchestrator accuracy is measured.

## Decisions

- 2026-07-10: Use a minimal MAS with one orchestrator and two possible specialists; invoke zero or one specialist per panorama.
- 2026-07-10: Treat extraction and re-examination as perception components, not agents.
- 2026-07-10: Send four 1024×1024 cardinal views together in one Flash extraction call.
- 2026-07-10: Allow no more than one targeted crop re-examination.
- 2026-07-10: Keep all specialist and orchestrator paths text-only.
- 2026-07-10: Predict one country worldwide rather than selecting from a disclosed closed list.
- 2026-07-10: Select 20+ coverage-qualified countries across 5+ continents, with 10 dev and 5 eval panoramas per country.
- 2026-07-10: Keep panoramas at least 10 km apart and prevent sequence leakage across splits.
- 2026-07-10: Use `dev_v1.csv` for tuning and frozen `eval_c1.csv` for final evaluation.
- 2026-07-10: Use exact country accuracy as the primary quality metric and country-centroid haversine loss as a secondary metric.
- 2026-07-10: Require complete inference cost at least 10% below Opus and country accuracy within five percentage points; report image-token cost separately.
- 2026-07-10: Skip ground-truth visual-signal subset annotation in v1.
- 2026-07-10: Initial conservative cost model estimates the delegated MAS path at $0.013840 versus $0.045380 for Opus; treat this as provisional until measured.
- 2026-07-10: Cap v1 at two orchestrator calls, one specialist, and one crop; force finalization at 90% of the current Opus cost budget.
- 2026-07-10: Coverage scan qualified 20 countries across six continents using 15 panoramic sequences at least 10 km apart per country; freeze them in `data/taxonomy.json`.
- 2026-07-10: Keep the coverage-driven taxonomy despite its Europe-heavy distribution; reconsider balancing only in a later dataset version.
- 2026-07-10: First real Mapillary/Gemini bbox sample used the documented convention correctly; all four 25%-padded crops retained their detected targets, though wide model boxes produced wide crops.
- 2026-07-10: Use LangChain's `deepagents` Python framework and `create_deep_agent` for the orchestrator; retain LangGraph only as the underlying runtime.
- 2026-07-10: Use built-in todo and subagent middleware, disable the automatic general-purpose subagent, and enforce one total `task` delegation with custom middleware.
- 2026-07-10: Keep required filesystem scaffolding, hide its unused file tools, and exclude optional summarization middleware to minimize prompt/tool overhead.

## Open Questions / Dependencies

- Recheck production model IDs, tokenization behavior, and provider prices immediately before the frozen evaluation.
- Select a versioned country-centroid dataset for haversine scoring.
- Define the seeded split procedure after coverage, distance, and sequence filtering.
- GeoTips/GeoHints reference extraction must preserve source attribution and be frozen before final evaluation.

## Last Updated

2026-07-10 — Completed Phase 0 economics/data checks, adopted LangChain Deep Agents 0.6.12, and validated a cost-constrained `create_deep_agent` supervisor factory with only the two named subagents.
