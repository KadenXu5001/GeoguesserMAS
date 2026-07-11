# Backlog

## Current Objective

Build and evaluate the smallest defensible GeoGuessr MAS: one non-agent Flash extraction call over four cardinal panorama views, one todolist-driven orchestrator, selective delegation to at most one of two text-only specialists, and at most one targeted crop re-examination. The final system must cost at least 10% less than an identical-input Opus baseline while remaining within five percentage points of its exact country accuracy.

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
- [ ] Implement `GeoState` with message, usage, and re-examination reducers.
- [ ] Implement hard budgets for zero-or-one specialist delegation, one crop call, iterations, and output tokens.
- [ ] Implement the extraction preprocessor: one Flash call containing all four headings.
- [ ] Define and validate the extraction schema with arrays of detected objects plus one consolidated signal per category.
- [ ] Distinguish `not_present`, `not_detected`, and `present_but_illegible`; normalize bbox coordinates.
- [ ] Add bounded malformed-output repair/retry behavior.
- [ ] Build versioned reference tables from GeoTips and GeoHints with source URLs and retrieval dates.
- [ ] Implement compact lookup tools for human and environmental indicators.
- [ ] Implement the human-clue specialist for language, signs, vehicles, plates, roads, and infrastructure.
- [ ] Implement the environmental specialist for terrain, climate, vegetation, and architecture.
- [ ] Implement the orchestrator with a mandatory dynamic todolist and agent-decided zero-or-one specialist delegation.
- [ ] Make agent tools mutate injected state consistently.
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

## Open Questions / Dependencies

- Recheck production model IDs, tokenization behavior, and provider prices immediately before the frozen evaluation.
- Select a versioned country-centroid dataset for haversine scoring.
- Define the seeded split procedure after coverage, distance, and sequence filtering.
- GeoTips/GeoHints reference extraction must preserve source attribution and be frozen before final evaluation.

## Last Updated

2026-07-10 — Completed the Phase 0 cost model, tested panorama renderer/bbox utilities, passed the Mapillary coverage gate, and froze a 20-country taxonomy spanning six continents.
