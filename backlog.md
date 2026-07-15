# Backlog

## Current Objective

Run and inspect the frozen France/Thailand/Brazil pilot through the complete MAS path before tuning prompts or considering expansion to the worldwide taxonomy. Keep local MongoDB/reference data and disk-backed images separated from model-facing extraction payloads.

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
- [x] Visually validate padded crops on 3–5 development-only panoramas with the production Gemini model (five development-only samples validated successfully on 2026-07-13; one additional candidate exhausted retries with a recorded 503).
- [x] Scan Mapillary coverage and select at least 20 qualifying countries across at least five continents.
- [x] Record the selected country taxonomy and continent mapping in `data/taxonomy.json`.
- [x] Install and pin `deepagents==0.6.12`; validate `create_deep_agent` against the pinned LangGraph/LangChain-Google dependencies.
- [x] Create a minimal Deep Agents construction smoke test using Gemini without invoking a paid model call.
- [x] Select France, Thailand, and Brazil as the representative three-country pilot.
- [x] Choose local MongoDB metadata storage with disk-backed image files and an Atlas-compatible `MONGODB_URI`.
- [x] Choose a versioned offline country-boundary dataset for ground-truth validation.
- [x] Implement MongoDB collections, validation rules, indexes, and dataset-version records.
- [x] Add local MongoDB startup configuration and environment settings.
- [x] Add a pilot dataset definition with 10 development and 5 evaluation slots per country.
- [x] Run one real France panorama through offline validation, MongoDB, download, four-view rendering, and contact-sheet generation.

## Next

- [x] Implement the Mapillary client with image-level `is_pano=true`, cursor pagination, tiling, retry/backoff, and failure logging.
- [x] Download panorama files and fetch expiring image URLs only when needed.
- [x] Resolve latitude/longitude to ground-truth country using pinned Natural Earth 5.1.1 offline boundaries.
- [x] Enforce at least 10 km separation between retained panoramas within each country.
- [x] Prevent any Mapillary sequence from crossing dev/eval splits.
- [x] Collect the strict 45-panorama pilot: 10 development and 5 evaluation panoramas each for France, Thailand, and Brazil.
- [x] Add panorama quality validation for complete 2:1 equirectangular coverage, horizontal wrap continuity, severe stitching artifacts, blur, occlusion, and excessive camera/operator visibility.
- [x] Record quantitative and manual quality-review results in MongoDB; strictly replace sources that fail the acceptance threshold.
- [x] Generate an ordered `0 | 90 | 180 | 270` strip preview for rapid continuity review alongside the 2x2 contact sheet.
- [x] Render and store four cardinal views for every retained panorama.
- [x] Create independently stratified `dev_v1.csv` with 10 panoramas per country.
- [x] Create and freeze `eval_c1.csv` with 5 panoramas per country.
- [x] Add an automated recursive model-payload audit that rejects latitude, longitude, coordinates, timestamps, image identifiers, filenames, checksums, country labels, split metadata, and related location clues.
- [ ] Review pilot ingestion results, then authorize or revise expansion to all 20 qualified countries.
- [x] Structurally review frozen pilot manifests: 30 development and 15 evaluation rows, 10/5 per country, with all four rendered views present.
- [x] Define Deep Agents runtime context/state for extraction, usage, delegation, re-examination, and final prediction.
- [x] Implement custom Deep Agents middleware for at-least-one and at-most-two `task` delegations (each specialist at most once), one crop call, three bounded orchestrator turns on the delegated-plus-crop path, output-token limits, and the 90%-of-Opus cutoff.
- [x] Implement the extraction preprocessor: one Flash call containing all four headings.
- [x] Define and validate the extraction schema with arrays of detected objects plus one consolidated signal per category.
- [x] Distinguish `not_present`, `not_detected`, and `present_but_illegible`; normalize bbox coordinates.
- [x] Add bounded malformed-output repair/retry behavior.
- [x] Implement compact lookup tools for human and environmental indicators.
- [x] Configure the human-clue custom subagent with a narrow prompt, tools, and structured response.
- [x] Configure the environmental custom subagent with a narrow prompt, tools, and structured response.
- [x] Implement the orchestrator with `create_deep_agent`, built-in `TodoListMiddleware`, and agent-decided delegation to at least one and at most two specialists.
- [x] Disable the automatic `general-purpose` subagent with `GeneralPurposeSubagentProfile(enabled=False)`.
- [x] Keep required filesystem/todo/subagent middleware, hide unused filesystem tools, and exclude summarization middleware in the harness profile.
- [x] Make Deep Agents tools use per-run runtime context consistently for budget, heading paths, and model clients.
- [x] Implement `emit_prediction` to write one worldwide country prediction and terminate successfully.
- [x] Implement one-call `reexamine_region` with heading-aware padded cropping and a specific visual question.
- [X] Verify in LangSmith that specialists and the orchestrator never receive full image bytes.
- [x] Run one live MAS panorama and inspect its LangSmith trace for image-free specialist/orchestrator inputs.
- [x] Verify in tests that both delegation and re-examination hard caps cannot be exceeded.
- [x] Implement direct Gemini Flash and Gemini Pro baselines using identical four-heading inputs.
- [x] Add an end-to-end MAS runner connecting manifest rows, Flash extraction, Deep Agents orchestration, and JSONL results.
- [ ] Ensure Gemini completes through the MAS tool path; a text-only completion must fail rather than bypass delegation and tool execution.
- [x] Make specialist reference lookups category-batched: omit country to retrieve all indicators for one category in a single tool call.
- [x] Add a JSONL result summarizer for exact accuracy, complete cost, image tokens, latency, call count, specialist rate, and re-examination rate.
- [x] Require at least one specialist, persist each specialist result in the local Deep Agents cache, cap cache reads at three, and stop with a warning after three minutes or $0.50.
- [x] Implement the original single deep-agent ablation without specialists.
- [x] Implement exact country accuracy, country-centroid haversine loss, complete cost, image-token cost, latency, and call-count metrics.
- [ ] Tune prompts and policies only on `dev_v1.csv`.
- [ ] Freeze prompts, models, policies, and reference tables before final evaluation.
- [ ] Run all frozen systems over `eval_c1.csv` and determine whether the MAS passes both gates.

## Later

- [ ] Expand the worldwide `reference-v1` bootstrap rows from GeoTips and GeoHints into the complete frozen reference table before evaluation.
- [ ] Run the MAS without re-examination as an ablation.
- [ ] Run a Gemini Pro orchestrator ablation only if the Flash orchestrator misses the accuracy gate.
- [ ] Add a CLI showing todolist, selected specialist, re-examination count, country, confidence, cost, and LangSmith trace URL.
- [x] Add a standalone Gemini Pro baseline script with JSONL output and LangSmith tracing.
- [ ] Document setup, ingestion, evaluation, limitations, and measured results in the README.
- [ ] Build a streamed web UI only after the cost and accuracy gates pass.
- [ ] Consider manually annotated visual-signal subsets in a later evaluation version.

## Blocked

- [ ] Production-model bbox visual validation — blocked by temporary 503 responses from both Gemini 3 Flash endpoints; panorama download/rendering and crop math are already verified.
- [ ] Final iteration and token budgets — blocked on measured development-set token usage; initial caps are documented.
- [ ] Final specialist/re-examination triggers — blocked on development-set experiments.
- [ ] Pro-orchestrator decision — blocked until the Flash-orchestrator accuracy is measured.

## Decisions

- 2026-07-10: Use a minimal MAS with one orchestrator and two possible specialists; invoke at least one and at most two specialists per panorama, each at most once.
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
- 2026-07-13: The live Deep Agents tool loop requires up to three meaningful orchestrator calls when both the one-specialist and one-crop caps are used; retain the 90%-of-Opus cutoff and model the extra review call explicitly.
- 2026-07-10: Coverage scan qualified 20 countries across six continents using 15 panoramic sequences at least 10 km apart per country; freeze them in `data/taxonomy.json`.
- 2026-07-10: Keep the coverage-driven taxonomy despite its Europe-heavy distribution; reconsider balancing only in a later dataset version.
- 2026-07-10: First real Mapillary/Gemini bbox sample used the documented convention correctly; all four 25%-padded crops retained their detected targets, though wide model boxes produced wide crops.
- 2026-07-10: Use LangChain's `deepagents` Python framework and `create_deep_agent` for the orchestrator; retain LangGraph only as the underlying runtime.
- 2026-07-10: Use built-in todo and subagent middleware, disable the automatic general-purpose subagent, and enforce one total `task` delegation with custom middleware.
- 2026-07-10: Keep required filesystem scaffolding, hide its unused file tools, and exclude optional summarization middleware to minimize prompt/tool overhead.
- 2026-07-12: Build a representative pilot before full collection, using France, Thailand, and Brazil.
- 2026-07-12: Require strict replacement until every pilot country has exactly 10 valid development and 5 valid evaluation panoramas.
- 2026-07-12: Validate ground-truth countries with a versioned offline boundary dataset rather than an online geocoder.
- 2026-07-12: Store metadata in local MongoDB through `MONGODB_URI`; keep panorama and rendered image bytes on disk and store paths/checksums in MongoDB. Preserve the option to move to Atlas later.
- 2026-07-12: Pin Natural Earth 5.1.1 Admin-0 Countries at 1:10m for offline coordinate validation.
- 2026-07-12: Keep expiring Mapillary URLs ephemeral; persist only local paths, dimensions, byte counts, and SHA-256 checksums.
- 2026-07-12: Treat Mapillary `thumb_original_url` panorama files as already-stitched equirectangular sources; the pipeline must not pretend to reconstruct raw camera feeds.
- 2026-07-12: Accept ordinary source-camera seams, but reject incomplete horizontal coverage or severe stitching, blur, occlusion, or camera/operator artifacts under the pilot's strict-replacement policy.
- 2026-07-12: The first France smoke-test panorama has correct 360° wrap and aligned cardinal projections, but visible source stitching and camera/operator artifacts make it a useful quality-policy calibration sample rather than an automatic quality pass.
- 2026-07-12: Use `panorama-quality-v1` automatic checks for 2:1 aspect, minimum 4096x2048 source size, horizontal wrap continuity, blur, and clipped-pixel fraction; require manual approval before a panorama becomes `rendered`.
- 2026-07-12: Rejected panorama candidates stay rejected and are skipped by later ingestion runs so strict replacement advances to later Mapillary candidates.
- 2026-07-13: Use boundary-filtered supplemental coverage scans when strict replacement exhausts the original 15-row pilot evidence pool.
- 2026-07-13: Freeze the three-country pilot manifests as `data/datasets/dev_v1.csv` and `data/datasets/eval_c1.csv`; keep image bytes on local disk and metadata/review state in MongoDB.
- 2026-07-13: Enforce model-input metadata isolation with a recursive payload auditor and 15 tests covering safe structured extraction plus forbidden metadata at nested paths.
- 2026-07-13: Define `extraction-v1` Pydantic output models and additive runtime state for Deep Agents; validate normalized bboxes, multi-object categories, detection statuses, and usage events with focused tests.
- 2026-07-13: Use Gemini structured JSON output for the four-view extractor with one bounded malformed-response retry; add a runtime budget policy enforcing three orchestrator turns on the hard path, at least one and at most two specialists, one re-examination, and the 90%-of-Opus cutoff.
- 2026-07-13: Store the runtime budget in per-run context under `geo_budget`; the Deep Agents middleware reads that context so concurrent panorama runs cannot share cap state.
- 2026-07-13: Add `emit_prediction` as a real tool using injected `ToolRuntime`; it validates the worldwide prediction, updates `final_prediction`, returns a tool message, and routes to `END`.
- 2026-07-13: Add `reexamine_region` as a single-call tool using only per-run heading paths and Gemini client context; return text-only visual findings with no image path or bytes in the tool result.
- 2026-07-13: Fetch GeoTips and current GeoHints worldwide route catalog; freeze a provenance-aware `reference-v1` bootstrap snapshot and give each specialist only its own lookup-tool family. Expand the normalized rows before evaluation.
- 2026-07-13: Persist reference rows in local MongoDB collection `reference_rows`; inference lookups require `reference_repository` and `reference_version` in per-run context. Add `seed-references` for explicit offline snapshot import.
- 2026-07-13: Defer expansion of the worldwide reference-row bootstrap to `Later`; continue MAS implementation on the frozen three-country pilot.
- 2026-07-13: Keep graph state (`GeoState`) separate from per-run operational context (`GeoContext`), including Mongo reference repository, reference version, budget, heading paths, and Gemini client.
- 2026-07-13: Enforce model output caps and record provider usage metadata in per-run budget state; reject delegation/re-examination beyond hard limits.
- 2026-07-13: Add single-agent ablation construction and evaluation summaries for accuracy, centroid loss, complete cost, image tokens, latency, call count, specialist rate, and re-examination rate.
- 2026-07-13: Implement direct Gemini Flash and Gemini Pro baseline runners over the canonical four-heading payload; keep the live Pro call opt-in.
- 2026-07-13: Add `scripts/run_gemini_pro.py` for one-row or full-`dev_v1` runs, JSONL result output, and one LangSmith trace per panorama.
- 2026-07-13: Add `src/geoguesser/mas_runner.py` and `scripts/run_mas.py`; the supervisor receives only audited extraction JSON while image paths and MongoDB/reference access remain in per-run context.
- 2026-07-13: Adapt the Gemini extraction response schema to avoid the SDK's integer-enum conversion bug; Pydantic retains strict cardinal-heading validation after provider parsing.
- 2026-07-13: Gemini can return a text-only supervisor completion despite ToolStrategy; treat that as a MAS failure rather than bypassing the required tools and subagents.
- 2026-07-14: Bare ToolRuntime annotations caused context serializer warnings; parameterize tools with GeoContext/GeoState. A tracing-enabled one-row run did not complete within the sandbox timeout, so LangSmith end-to-end verification remains open.
- 2026-07-14: Specialist lookup tools now batch by category; broad vegetation/architecture/etc. lookups omit country, preventing repeated country/category enumeration. MAS runs require at least one specialist and permit both focused specialists when evidence warrants it.
- 2026-07-13: Add a bounded `INVALID_ARGUMENT` fallback from provider-enforced extraction schema to JSON MIME mode with local Pydantic validation, preserving the extraction contract across Gemini SDK/API variants.
- 2026-07-13: Label structured-schema and JSON-only extraction failures separately so provider `INVALID_ARGUMENT` causes can be isolated deterministically.
- 2026-07-13: Normalize only known Gemini extraction aliases (`1.0` → `extraction-v1`, `legible` → `clear`) before strict Pydantic validation.
- 2026-07-13: Map the Deep Agents output cap to Gemini's `max_output_tokens` setting while retaining `max_tokens` for non-Gemini providers.
- 2026-07-13: Exclude the required `write_todos` continuation from the two meaningful orchestrator-turn counter; retain its usage/cost accounting and reserve the cap for decision/finalization turns.
- 2026-07-13: Use validated `emit_prediction` as the sole supervisor finalization path; remove redundant Gemini native `CountryPrediction` structured output that failed during provider parsing.
- 2026-07-13: Make specialist lookup category mistakes recoverable tool feedback and explicitly constrain the environmental specialist away from human-clue categories.
- 2026-07-13: Use explicit LangChain `ToolStrategy(CountryPrediction)` for provider-compatible structured finalization; retain validated `emit_prediction` as the preferred terminating tool.
- 2026-07-13: Count extraction attempts in the same per-run `RuntimeBudget` as orchestrator calls so complete MAS cost includes extraction retries.
- 2026-07-13: Add `scripts/summarize_results.py` so development/evaluation JSONL runs can be scored without exposing evaluation metadata to model prompts.
- 2026-07-13: Replace retired `gemini-3-pro-preview` with Google's current `gemini-3.1-pro-preview` in the direct Pro baseline.
- 2026-07-13: Add a versioned development tuning harness that accepts only `dev_v1`, logs JSONL experiment records, and selects the highest-accuracy eligible configuration under a cost constraint; defer paid Flash/Pro experiments until authorized.

## Open Questions / Dependencies

- Recheck production model IDs, tokenization behavior, and provider prices immediately before the frozen evaluation.
- Select a versioned country-centroid dataset for haversine scoring.
- Define the seeded split procedure after coverage, distance, and sequence filtering.
- GeoTips/GeoHints reference extraction must preserve source attribution and be frozen before final evaluation.

## Last Updated

2026-07-13 - Completed five production-model bbox validations on development-only samples. The validator now checkpoints each sample, retries transient 429/5xx errors with exponential backoff and jitter, processes sequentially, records failures, and uses a larger JSON output budget; one extra candidate exhausted retries with a Gemini 503.

2026-07-13 - Added the automated model-payload metadata audit; all 15 focused tests pass.

2026-07-13 - Added and validated the extraction-v1 schema and runtime state; the focused payload/schema suite passes 17 tests.

2026-07-13 - Implemented the four-view extraction runner and initial hard-budget policy; focused extraction and budget tests pass 22 tests.

2026-07-13 - Wired per-run budget middleware into the Deep Agents factory; the full repository suite passes 50 tests.

2026-07-13 - Wired and tested `emit_prediction` with runtime context and graph termination; the full repository suite passes 51 tests.

2026-07-13 - Implemented and tested `reexamine_region` with 25%-padded heading-aware crops; the full repository suite passes 52 tests.

2026-07-13 - Added fetched reference snapshot loading and narrow human/environmental lookup tools; focused reference tests pass.

2026-07-13 - Moved reference lookup to MongoDB-backed repository queries and added the explicit seed command; full suite passes 56 tests.

2026-07-13 - Wired specialist configuration and the `create_deep_agent` orchestrator to typed graph state plus per-run context; full suite passes 58 tests.

2026-07-13 - Completed hard-cap middleware, ablation construction, and offline evaluation metrics; live baseline/evaluation runs remain pending model/price confirmation.

2026-07-13 - Prepared the development tuning harness without paid model calls; full suite passes 66 tests.
2026-07-13 - Added tested Gemini Flash and Gemini Pro direct baseline adapters; local verification was limited to bytecode compilation because the checked-in Python environments are unavailable on this machine.
2026-07-13 - Added the first end-to-end MAS execution path and payload-isolation tests; live MAS execution remains dependent on local MongoDB/reference seeding and available Gemini credentials.
2026-07-13 - Audited the MAS runner against the backlog, added extraction usage accounting, and verified frozen manifests contain 30 dev/15 eval rows with all 180 rendered view files present.
2026-07-13 - Added the offline JSONL evaluation summarizer; live tuning/evaluation is waiting on a working project Python interpreter, MongoDB, Gemini credentials, and LangSmith access.
2026-07-13 - MongoDB initialization and reference seeding succeeded; the first MAS attempt reached schema construction and exposed the integer-heading provider-schema issue, which is now fixed.
2026-07-13 - A second live MAS attempt still returned Gemini `INVALID_ARGUMENT`; added a provider-schema fallback and regression test, ready for the next one-row retry.
2026-07-13 - The next live extraction succeeded but returned two canonicalization aliases; added bounded alias normalization and regression coverage before supervisor execution.
2026-07-13 - The next live run reached supervisor construction and exposed a provider setting mismatch; added Gemini-specific output-token mapping and a regression test.
2026-07-13 - Live MAS reached the supervisor but exhausted the turn cap on the required todo continuation; adjusted cap accounting and added a regression test.
2026-07-13 - Live MAS reached finalization but Gemini native structured-output parsing returned empty JSON; removed the redundant response-format layer and kept schema validation in `emit_prediction`.
2026-07-13 - Live MAS reached the environmental specialist; an invalid `infrastructure` lookup aborted the run, so lookup tools now return corrective feedback instead of raising.
2026-07-13 - Native sandbox run returned plain text without a tool call; required-tool binding hung with the Google adapter, so switched to explicit ToolStrategy for structured tool-call finalization.

2026-07-13 - Completed the strict 45-panorama France/Thailand/Brazil pilot, exported `dev_v1.csv` and `eval_c1.csv`, and added boundary-filtered replacement scan support.

2026-07-12 - Implemented automatic panorama quality metrics, MongoDB manual quality review, ordered strip previews, and rejected-candidate skipping for strict replacement.

2026-07-12 - Reviewed the first pilot-quality samples: approved one development panorama each for France, Thailand, and Brazil; rejected one Thailand candidate for excessive foreground occlusion.

2026-07-12 — Added explicit panorama completeness/stitching quality gates and strict replacement requirements after inspecting the first live Mapillary panorama.

2026-07-12 — Replanned Phase 1 around a strict France/Thailand/Brazil pilot, local MongoDB metadata, disk-backed images, and offline boundary validation.

2026-07-10 — Completed Phase 0 economics/data checks, adopted LangChain Deep Agents 0.6.12, and validated a cost-constrained `create_deep_agent` supervisor factory with only the two named subagents.
