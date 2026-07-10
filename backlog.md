# Backlog — GeoGuessr Deep-Agent System

Derived from [v2pland.md](v2pland.md). Organized by phase; each task is scoped to be a single sitting. Check items off as completed. Open questions from the plan are folded in as decisions to make before the task that depends on them.

---

## Phase 0 — Setup & validation (nothing else starts until this is done)

- [x] `.env` with `MAPILLARY_ACCESS_TOKEN`, `GEMINI_API_KEY`, `LANGCHAIN_API_KEY`, `LANGCHAIN_PROJECT=geoguessr-deepagent`, `LANGCHAIN_TRACING_V2=true`
- [x] Add `.env` to `.gitignore` (verify it's not already tracked — `git status` first)
- [x] `pyproject.toml`/`requirements.txt` with pinned versions: `langgraph`, `langsmith`, `langchain-google-genai`, `requests`, `mercantile`, `haversine`, `pillow`, `python-dotenv`
- [x] Register Mapillary app, get access token
- [x] Register/confirm LangSmith project, get API key
- [x] Look up current Gemini 3.x model IDs (Flash + Pro) and confirm both are available via `langchain-google-genai`
- [ ] **Token cost model spreadsheet/notebook** (`docs/cost_model.md` or a notebook): image tokens per full-frame heading, image tokens per cropped/upscaled region, expected calls per image (easy vs. hard), text-token estimate for reference tables + JSON + reasoning. Compute and compare the three totals in the plan's table (lean agent / single Pro / single Opus).
  - [ ] **Gate:** if the lean design isn't clearly cheaper than a single Pro call on easy images, stop and rethink before writing pipeline code.
- [ ] Small standalone script: send one test image to Gemini 3.x, request a bbox for a described object, inspect the raw response to confirm coordinate convention (normalized 0–1000 vs. pixels; `[x1,y1,x2,y2]` vs `[ymin,xmin,ymax,xmax]`)
- [ ] Crop-accuracy sanity check: take 3–5 images, get bboxes from the model, crop with ~25% padding, visually confirm the target object survives the crop
- [ ] Define target-country/region taxonomy for the eval set (needed before the sampler) — write to `data/taxonomy.py` or `taxonomy.json`

---

## Phase 1 — Data pipeline

- [ ] `data/db.py` — SQLite schema: images table (`id`, `local_path`, `lat`, `lng`, `country`, `region`, `captured_at`, `sequence_id`, `downloaded_at`)
- [ ] `data/mapillary_client.py` — wrapper for Mapillary API: bbox query (image-level `is_pano=true` filter, since sequences mix pano/non-pano), cursor pagination, exponential backoff on 429/5xx
- [ ] `data/ingest.py` — `ingest_region(country, bbox, target_count)` using `mercantile.tiles(*bbox, zooms=14)` to stay under Mapillary's ~0.01° bbox cap; fetches `thumb_original_url` fresh per download (don't cache the URL, it expires); writes metadata to SQLite; logs every failure to a file
- [ ] Dry run: 5–10 images for 2–3 regions, verify files land correctly and metadata rows are correct
- [ ] Pano-density check per target region in the taxonomy — query counts before committing to per-region targets
- [ ] Decide + document fallback policy for sparse regions (drop the region / accept lower count / relax to single-frame) based on the density check
- [ ] Run full ingestion (~500 images), stratified by continent/country per the taxonomy
- [ ] Build `eval_v1.csv` (image id, local path, ground-truth lat/lng, country, region) — freeze it, no further edits
- [ ] Upload `eval_v1.csv` to LangSmith as a dataset
- [ ] Verification pass: confirm no lat/lng/timestamp field is ever included in a model-facing payload (grep the codebase for where image metadata is assembled into prompts)

---

## Phase 2 — Core pipeline (LangGraph)

### 2.1 State & scaffolding

- [ ] `geo_agent/state.py` — `GeoState` TypedDict with reducers (`Annotated[list, add]` for `reexamine_results`, `Annotated[list, add_messages]` for `messages`)
- [ ] `geo_agent/config.py` — loads `.env`, exposes model IDs/constants in one place (so Phase-0's pricing lookup only needs updating here)
- [ ] `geo_agent/graph.py` — skeleton graph: extraction node → deep agent node → END, no tools wired yet

### 2.2 Extraction node (Node 1, not an agent)

- [ ] `geo_agent/nodes/extraction.py` — single Gemini Flash call, structured prompt requesting all signals (driving_side, road_markings, bollard, plate, text, terrain, architecture) each with `value`, `confidence`, `bbox`, `legible`
- [ ] Pydantic/JSON-schema model for the extraction output; validate the raw LLM response against it, with a repair/retry path on malformed JSON
- [ ] Apply the bbox padding decision from Phase 0 (pad ~20–30%) as a shared util (`geo_agent/bbox.py`) used by both extraction validation and `reexamine_region`
- [ ] Run on a handful of eval images, inspect traces in LangSmith, confirm schema holds

### 2.3 Reference tables

- [ ] `geo_agent/reference_data/bollards.json` (seed from the plan's excerpt, extend)
- [ ] `geo_agent/reference_data/plate_formats.json`
- [ ] `geo_agent/reference_data/road_markings.json`
- [ ] `geo_agent/reference_data/utility_poles.json`
- [ ] Loader util that reads these into memory once at startup (not re-read per call)

### 2.4 Deep agent node (Node 2, the real agent)

- [ ] `geo_agent/tools/lookup_regional_indicator.py` — text-only lookup against the reference tables
- [ ] `geo_agent/tools/cross_reference_candidates.py` — narrows a candidate list against a stated constraint
- [ ] `geo_agent/tools/update_todolist.py` — reads/writes `agent_todolist` in state (use `InjectedState` or node-level state passing per the plan's guidance — pick one convention and apply consistently)
- [ ] `geo_agent/tools/emit_prediction.py` — writes `final_prediction`; enforce point-estimate-not-centroid in the tool's docstring/schema (require `lat_lng_estimate` at admin-region/city granularity)
- [ ] `geo_agent/nodes/deep_agent.py` — ReAct loop (Gemini Pro, LangGraph prebuilt `create_react_agent` or hand-rolled loop) wired to the four tools above, seeded with the initial todolist text from the plan
- [ ] Confirm in LangSmith traces: todolist item count/order actually varies across a handful of test images (this is the thing that makes it a "deep agent" and not a for-loop — verify it, don't assume it)
- [ ] Confirm no image bytes are sent in this node's default path (only JSON + text reference data)

### 2.5 Re-examination (the one genuinely agentic decision)

- [ ] `geo_agent/tools/reexamine_region.py` — crop image to padded bbox, optional upscale (Pillow), re-send crop + question to Gemini, return observation; append result via the `reexamine_results` reducer
- [ ] Wire `reexamine_region` into the deep agent's tool list
- [ ] **Decision to make before/while building:** re-look budget cap per image (start with e.g. 2, tune later) — enforce it in the tool or node, not just via prompting
- [ ] **Decision to make:** trigger condition — `legible: false` alone, candidate tie alone, or both — implement whichever the ablation (Phase 2.7) will test
- [ ] Confirm via traces that it fires only on illegible/tied cases across a mixed batch of easy/hard test images, not on every image

### 2.6 Baselines (needed for comparison, build alongside the agent)

- [ ] `eval/baselines.py` — `run_single_call(model, image)` for a bare single-image-in, JSON-out prediction (no agent loop)
- [ ] Wire up `baseline-flash`, `baseline-pro`, `baseline-opus` as three configs of the same function
- [ ] Register each as a LangSmith experiment target

### 2.7 Eval harness

- [ ] `eval/metrics.py` — country accuracy, continent accuracy, haversine distance error (point estimate vs. ground truth)
- [ ] `eval/harness.py` — runs a system (baseline or full agent) over `eval_v1.csv`, logs predictions + metrics to LangSmith
- [ ] Run `baseline-flash`, `baseline-pro`, `baseline-opus` over the eval set, record results
- [ ] Run full agent as `deepagent-v1`, confirm it beats Flash and narrows the gap to Pro
- [ ] Stratify results into the four subsets from the plan (legible text/script, hard prior legible, illegible high-value signal, no strong signal) and build the comparison table
- [ ] Ablation run: `deepagent-no-relook` (same agent, `reexamine_region` disabled) vs `deepagent-v1`, compare on the illegible-signal subset specifically
- [ ] Decide, from the ablation, whether to keep `reexamine_region` as currently triggered/budgeted, or adjust the Phase 2.5 decisions and re-run

---

## Phase 3 — Polish

- [ ] Clean up reasoning-chain formatting for demo output (strip internal tool-call noise, keep the narrative)
- [ ] `geo_agent/cli.py` — `python -m geo_agent <image_path>` → prints todolist trace, re-looks used, final point prediction, LangSmith trace URL
- [ ] README: setup steps, how to run ingestion, how to run eval, how to run a single image through the CLI
- [ ] (Later, not blocking) web UI with streamed reasoning + live todolist

---

## Open decisions to resolve during the build (not before)

These are called out in the plan as things to tune empirically rather than guess up front — don't block on them, resolve via the ablation/sweeps in Phase 2.7:

- [ ] Re-look budget cap (1 vs 3) — tune against illegible-signal subset results
- [ ] Re-look trigger condition (legibility / tie / both) — decide via ablation
- [ ] Extraction image resolution — sweep against the Phase 0 cost model and re-look frequency
- [ ] Crop upscale method (resize vs. none) — check whether it changes model reads or just adds tokens
- [ ] Heading strategy (single heading vs. 0/90/180/270, static vs. agent-requested) — weigh against cost model
