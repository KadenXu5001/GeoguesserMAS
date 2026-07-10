# GeoGuessr Deep-Agent System — Build Plan

## What this is

A geolocation system that analyzes a street-level image and predicts where it was taken. Built with LangGraph, using **one genuine deep agent** (a ReAct tool-calling loop with a variable todolist and a conditional re-perception tool) sitting on top of a cheap perception preprocessor. Gemini 3.x for multimodal reasoning, LangSmith for full observability.

The design goal is **accuracy-per-token**: match a frontier monolithic model (Gemini Pro, and as a stretch, Opus) on high-signal images at a fraction of the token cost, and be honest about where it falls short.

This is not a training project. No model is fine-tuned. The "dataset" is a small eval set (~300–500 images) used purely to measure system performance.

### The core design decision (read this first)

An earlier version of this plan had seven agents: an orchestrator, five parallel specialists, an aggregator, and an escalation agent. Modeling the token cost killed that design. The dominant cost in a vision pipeline is **image tokens**, and a fan-out of specialists that each re-send the image (often across multiple tool-calling iterations) spends far more image tokens than a single monolithic call — while adding no accuracy over a single well-prompted reasoning step operating on already-extracted signals.

The lean paradigm concentrates cost where it belongs and concentrates "agentic" behavior where it's _real_:

1. **Perception happens once.** A single structured vision pass extracts all signals (driving side, markings, bollards, plates, text, terrain) into a JSON object, plus a rough bounding box and a legibility flag per signal. The image is encoded and sent **one time**.
2. **Inference is one deep agent.** A ReAct tool-calling loop reasons from that JSON + text-only reference tables to a location. Its tools do real work: text reference lookups (cheap) and, critically, **on-demand region re-examination** — cropping and upscaling a specific bounding box for a closer, higher-resolution second look.
3. **A second image call happens only when warranted.** The agent decides — based on evidence (an illegible plate, a tie between two countries) — whether to spend more perception budget. Most images resolve from the single extraction pass. Hard images trigger a targeted re-look. This runtime compute-spending decision is the genuinely agentic part of the system.

This is the whole thing: **one extraction call, one deep agent, conditional targeted re-perception.** Two to three nodes. It is honestly describable as "a LangGraph deep agent with a tool-calling harness," it is cheaper than both the seven-agent design and a monolithic model that always processes the full image at full resolution, and the "I removed the agents I couldn't justify and kept the one I could" narrative is stronger than "I wired up seven agents."

---

## Step 0 (before any building) — Token cost model

The entire premise is cost. Validate it on paper before writing code.

Build a back-of-envelope spreadsheet estimating, per image:

- **Image tokens per full-frame heading** at the resolution you'll actually send (look up how Gemini 3.x tiles/tokenizes images at your target dimensions — don't guess).
- **Image tokens per cropped-and-upscaled region** (the re-perception tool's payload).
- **Expected number of LLM calls per image**, split by easy vs. hard: easy = 1 extraction + 1 reasoning pass with 0 re-looks; hard = extraction + reasoning + 1–3 re-looks.
- **Text tokens** for reference tables, extracted-JSON, and reasoning — cheap, but count them.

Then compute three totals and compare:

| System                      | Image-token spend per image      | Notes                           |
| --------------------------- | -------------------------------- | ------------------------------- |
| Lean deep agent (this plan) | ~1 full frame + occasional crops | Crops only on hard cases        |
| Single Gemini Pro call      | 1 full frame                     | The clean architecture baseline |
| Single Opus call            | 1 full frame                     | The stretch target              |

If the lean design isn't clearly cheaper than a single Pro call on the easy-case majority, stop and rethink before building. Get **current per-token pricing for Gemini 3.x and Opus** and plug in real numbers — the resume bullet's cost claim should be a measured figure, not a hope.

---

## LangGraph architecture

### Graph shape

```
                    ┌─────────────────────┐
   image ──────────▶│  Extraction Node    │   single structured vision pass
                    │  (NOT an agent)     │   image encoded + sent ONCE
                    └──────────┬──────────┘
                               │  writes signals JSON (+ bbox + legible per signal)
                               ▼
                    ┌─────────────────────┐
                    │  Deep Agent Node    │   ReAct tool-calling loop
                    │  (the harness)      │   variable todolist
                    │                     │
                    │  tools:             │
                    │  - lookup_indicator │   text-only, cheap
                    │  - cross_reference  │   text-only, cheap
                    │  - reexamine_region │   crops+upscales a bbox → 2nd image call
                    │  - update_todolist  │
                    │  - emit_prediction  │
                    └──────────┬──────────┘
                               │
                               ▼
                              END
```

There is no upfront "spotter" stage and no parallel fan-out. The extraction pass already localizes every signal it describes (a model that can describe a bollard can report roughly where it is in the same pass, for the same image-token cost). A separate localization call would pay the full-image cost twice to learn what one pass already knows. Cropping only helps when a _closer_ look reveals something the first pass couldn't resolve — and that is exactly what `reexamine_region` does, on demand.

### Shared state (`GeoState`)

Note the reducers. Any key that could be written by concurrent branches, or accumulated across a loop, needs an explicit reducer or LangGraph raises `InvalidUpdateError`. Even in this lean (mostly sequential) graph, the message history and any accumulated re-look results want reducers.

```python
from typing import TypedDict, Annotated
from operator import add
from langgraph.graph import add_messages

class GeoState(TypedDict):
    image_path: str                      # input image
    image_b64: str                       # base64 full-frame heading(s)
    extraction_output: dict              # signals JSON from the extraction node
    reexamine_results: Annotated[list, add]   # accumulated crop re-looks (append, don't overwrite)
    agent_todolist: dict                 # the deep agent's checklist, updated in-loop
    final_prediction: dict               # the answer
    messages: Annotated[list, add_messages]   # full history for LangSmith
```

If you later add any parallel work, give its target key an `Annotated[..., reducer]` merge function up front.

### Reading state inside tools

Tools cannot receive graph state through an ordinary argument. A signature like `def review(state: GeoState)` will not get the live state. Use one of:

- **`InjectedState`** — annotate the parameter so LangGraph injects state without exposing it to the model:

  ```python
  from langgraph.prebuilt import InjectedState
  from typing import Annotated

  @tool
  def read_extraction(state: Annotated[dict, InjectedState]) -> dict:
      """Return the extraction JSON from current state."""
      return state["extraction_output"]
  ```

- **Or** read state in the node function and pass plain values into the tool call. Simpler, and preferred where the tool doesn't strictly need the whole state object.

### LangSmith tracing

```python
# .env — never hardcode
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=<your-langsmith-key>
LANGCHAIN_PROJECT=geoguessr-deepagent
```

Tracing is automatic once the env vars are set. What it buys here:

- Full trace tree per image: extraction → deep-agent loop → (re-look calls) → prediction.
- The **variable todolist** at each loop iteration — this is where "deep agent" is visible: on easy images the loop resolves in zero tool calls; on hard ones you see it decide to re-examine, and why.
- Per-node latency and token usage — confirm image tokens are spent once by default.
- Side-by-side run comparison for prompt tuning.
- Native eval dataset management (see Evaluation).

---

## Node 1 — Extraction (single structured pass)

### Role

One vision call. Image in once, structured JSON out. This is plumbing, not an agent — no loop, no todolist, and that's correct. Don't dress it up as an agent; the honest system description is "one deep agent plus a perception preprocessor," which is a better answer to "how many agents?" than an inflated count.

### What it extracts

A single prompt asks for every signal at once, because the model has to look at the image anyway. Per signal, it returns the observation, a rough bounding box, and a legibility/confidence flag so the deep agent knows what's worth a closer look.

```python
extraction_output = {
    "driving_side": {"value": "left", "confidence": 90, "bbox": null},
    "road_markings": {"value": "white dashed centerline", "confidence": 85, "bbox": [x1,y1,x2,y2]},
    "bollard":   {"value": "short white cylinder, red band", "confidence": 70,
                  "bbox": [x1,y1,x2,y2], "legible": true},
    "plate":     {"value": "present but unreadable", "confidence": 40,
                  "bbox": [x1,y1,x2,y2], "legible": false},   # ← re-look candidate
    "text":      {"value": "sign, script unclear", "confidence": 35,
                  "bbox": [x1,y1,x2,y2], "legible": false},   # ← re-look candidate
    "terrain":   {"value": "rolling green hills, tile-roof houses", "confidence": 80, "bbox": null},
    "architecture": {"value": "red hip-roof rural homes", "confidence": 75, "bbox": null},
}
```

`legible: false` (or low confidence) on a signal that carries high locational value is the trigger the deep agent watches for.

**Bounding-box caveat.** Vision-model boxes are decent but not pixel-perfect, and coordinate conventions differ (normalized 0–1000 vs. absolute pixels; some models return `[ymin,xmin,ymax,xmax]` rather than `[x1,y1,x2,y2]`). Before relying on crops: confirm the exact box format Gemini 3.x returns, and **pad every bbox generously (~20–30%)** before cropping so a slightly-off box doesn't clip the thing you wanted. Do a quick empirical check that boxes are good enough to crop on before leaning on the feature.

**Model:** Gemini Flash (3.x). Perception is pattern extraction, not open-ended reasoning.

---

## Node 2 — Deep Agent (the harness)

### Role

The one real agent. A ReAct tool-calling loop that reasons from the extraction JSON + text reference tables to a location, and decides when to spend more perception budget. The loop is genuinely variable: some images resolve with zero tool calls, some trigger several re-looks. That variability — not a fixed checklist — is what distinguishes this from a for-loop, and it's visible in LangSmith.

### Todolist (dynamic, not a fixed script)

Initialized loosely and adapted in-loop. The point is that item count and order vary by image:

```
[ ] Read extraction JSON; note any signal with high locational value but low legibility
[ ] Apply hard constraints (driving side, script) to prune the candidate set
[ ] Look up reference indicators for the strongest legible signals
[ ] If two+ candidates remain tied AND a decisive signal is illegible → reexamine that region
[ ] Re-apply constraints with any newly legible signal
[ ] Emit point-estimate prediction with confidence and reasoning
```

Only the items that apply to _this_ image actually fire.

### Tools

```python
@tool
def lookup_regional_indicator(indicator_type: str, description: str) -> dict:
    """Look up countries/regions associated with a described visual indicator,
    using a pre-loaded text reference DB (bollards, plate formats, markings, etc.).
    Text-only, cheap. Injects knowledge rather than trusting training memory."""

@tool
def cross_reference_candidates(candidates: list[str], constraint: str) -> dict:
    """Narrow candidate countries against a constraint
    (e.g. 'left-hand traffic', 'Cyrillic script', 'tropical climate')."""

@tool
def reexamine_region(bbox: list[int], question: str, upscale: bool = True) -> dict:
    """Crop the image to bbox (padded ~25%), optionally upscale, and re-read it
    with a specific question in mind. This is the ONLY tool that spends a second
    image call. The agent calls it only when a high-value signal is illegible or
    candidates are tied. Returns the closer-look observation."""

@tool
def update_todolist(item: str, status: str) -> dict:
    """Tick a todolist item in GeoState as reasoning progresses."""

@tool
def emit_prediction(
    region_guess: str,
    confidence: int,
    lat_lng_estimate: list[float],
    reasoning: str,
    candidate_alternatives: list[str],
) -> dict:
    """Write the final prediction. Emit a point estimate at the FINEST granularity
    the evidence supports (city/admin region if possible), NOT the country centroid."""
```

`reexamine_region` is the crop-and-upscale idea done demand-driven: the full accuracy upside of a high-resolution look at small signals (plates, signage), with none of the always-on cost. It fires on hard cases only.

### Output

```python
final_prediction = {
    "region_guess": "Shimane Prefecture, Japan",
    "confidence": 84,
    "lat_lng_estimate": [35.1, 132.7],   # admin-region / city centroid, NOT country centroid
    "reasoning": "Left-hand traffic (conf 90) constrains to LHT countries. Bollard "
                 "(short white cylinder, red band → Japan, conf 70) is consistent. Plate "
                 "was illegible in extraction; reexamine_region on the plate bbox returned a "
                 "green-on-white passenger format consistent with Japan, breaking the "
                 "Japan/other-LHT tie. Terrain (rolling hills, tile-roof homes) narrows "
                 "within Japan toward the San'in region.",
    "reexaminations_used": 1,
    "candidate_alternatives": ["South Korea"],
}
```

**Point estimate, not country centroid.** The headline metric is mean distance error (km). If the agent always emits the country centroid, it is structurally handicapped on that metric — for large countries the centroid sits 500–1500 km from most real points, and a monolithic model asked to name a _city_ will win on km-error even when it names the wrong country. Emit the finest-granularity point the evidence supports. Keep country-classification accuracy as a separate primary metric; treat km-error as secondary and label it as such.

**Model:** Gemini Pro (3.x). This is the reasoning-heavy step, and — importantly — **no image rides along by default** (it reasons over extracted JSON), so a stronger model here is cheap. Image tokens only enter when `reexamine_region` fires.

---

## Reference tables (injected, text-only)

Reference lookups inject knowledge the model may not surface reliably from memory, and they cost almost nothing because they're text. Keep them curated and small so they don't bloat context. Example excerpt:

```
BOLLARD REFERENCE (match the description):
- Short white cylinder, red reflector band → Japan
- Yellow/black flexible delineator post → Netherlands, Belgium
- Red/white diagonal stripe, rigid → Poland, Czech Republic, Romania
- Blue circular top, white shaft → Sweden
- Tall yellow flexible post, no markings → Australia
- Black/yellow concrete, square → Germany
- Green flexible post → Ireland
```

Extend with plate-format, road-marking-color, and utility-pole tables. These live behind `lookup_regional_indicator`, not baked into every prompt.

---

## Tech Stack

| Layer            | Choice                         | Notes                                                                                                  |
| ---------------- | ------------------------------ | ------------------------------------------------------------------------------------------------------ |
| Orchestration    | LangGraph                      | Typed `GeoState` with reducers; conditional edge for the loop; `InjectedState` for state-reading tools |
| Agent pattern    | ReAct tool-calling loop        | One deep agent with a variable todolist and real tools                                                 |
| Observability    | LangSmith                      | Traces every node/tool/LLM call; eval dataset mgmt; run comparison                                     |
| Extraction model | Gemini Flash (3.x)             | Cheap structured perception, image sent once                                                           |
| Deep-agent model | Gemini Pro (3.x)               | Reasoning over JSON; image enters only via re-look                                                     |
| Language         | Python 3.11+                   | LangGraph native                                                                                       |
| Image source     | Mapillary API (`is_pano=true`) | CC BY-SA; skewed toward EU/US (see Data)                                                               |
| Metadata store   | SQLite                         | Right-sized for 300–500 images                                                                         |
| Phase 1 deploy   | Local CLI                      | No UI needed to test the pipeline                                                                      |
| Phase 2 deploy   | Web demo (later)               | Streamed agent reasoning + live todolist                                                               |

Nail down the exact model IDs early — the cost argument depends on current Gemini 3.x per-token pricing.

---

## Data Pipeline

### Source: Mapillary (360° panoramas only)

Chosen over Street View for licensing (CC BY-SA permits bulk download + local storage; Street View ToS restricts caching at scale).

- Filter `is_pano: true` at the **image level** (sequences mix pano and non-pano frames).
- Bbox queries capped at ~0.01° square (Mapillary limit) — tile with `mercantile` at zoom 14.
- Cursor-based pagination; exponential backoff on 429/5xx.
- `thumb_original_url` expires — fetch fresh per download run, don't cache the URL.
- Log every failure to a file.

### Two coverage cautions

1. **Mapillary coverage is heavily skewed toward Europe and the US**, and sparse elsewhere — exactly the regions where geolocation is hardest. Random sampling will bias the eval toward easy regions. **Stratify deliberately** by continent/country rather than sampling at random, and check pano density per target region _before_ committing to counts. If sparse, decide the fallback early (drop the region, accept lower counts, or relax to single-frame).
2. **No metadata leak.** Mapillary carries lat/lng and a capture timestamp. None of it may reach the model — the eval must be pixels-only, or the accuracy numbers are meaningless. (The timestamp would make sun-position genuinely informative, which is one reason Sun/Shadow was dropped: using it fairly would require withholding the timestamp anyway.)

### Ingestion (high level)

```python
def ingest_region(country, bbox, target_count):
    for tile in mercantile.tiles(*bbox, zooms=14):
        for img in mapillary_query(mercantile.bounds(tile), is_pano=True):
            download_with_backoff(img)                 # backoff on 429/5xx
            write_metadata_to_sqlite(img)              # id, lat, lng, country, region
            if count_for_region(country) >= target_count:
                return
```

Freeze the stratified sample as `eval_v1.csv` before any prompt tuning. Upload to LangSmith. Tune prompts on a separate dev subset; never touch `eval_v1`.

---

## Evaluation Plan

### Metrics

- **Country classification accuracy** — primary development metric. Fast, interpretable, good for prompt-tuning feedback.
- **Continent accuracy** — coarse sanity check; if this is low, something fundamental is broken.
- **Mean distance error (km)** — headline metric for the demo. Haversine from the predicted **point estimate** (city/admin centroid, not country centroid) to ground truth.

### Baselines — isolate the variable

The critical fix from the original plan: comparing a Gemini system to Opus changes **both architecture and model family**, so a win/loss doesn't tell you what the architecture contributed. Run two comparisons and label what each proves:

1. **Single Gemini Flash call** — the floor. The deep agent must clear this.
2. **Single Gemini Pro call** — _the clean comparison._ Same model family, so the architecture is the only variable. This is the number that shows what the deep-agent structure actually buys.
3. **Single Opus call** — a _different question_: can a cheaper-model deep agent reach a frontier model? Interesting, but not an architecture-isolation test.

### Stratified comparison (the money result)

Break the eval set by which signals were detected, then compare within each subset:

| Subset                                            | Expected behavior                        | Rationale                                                                              |
| ------------------------------------------------- | ---------------------------------------- | -------------------------------------------------------------------------------------- |
| Legible text / script visible                     | Match or beat Pro; competitive with Opus | Near-deterministic signal; extraction never misses it                                  |
| Hard prior (bollard, driving side, plate) legible | Match or beat Pro                        | Reference lookup + constraint pruning is decisive                                      |
| Illegible high-value signal present               | Deep agent gains here                    | `reexamine_region` recovers signal a single pass misses — the architecture's real edge |
| No strong signal, no text                         | Frontier monolith likely wins            | Raw capability matters most; be honest about this                                      |

The illegible-signal row is where this design earns its keep: the crop-and-upscale re-look is precisely the case a single full-frame pass under-resolves. That, plus the "cheap on easy images / spends only on hard ones" cost profile, is the defensible finding.

### Ablation

The single most informative ablation: **run with `reexamine_region` disabled vs. enabled** on the same eval set. If the re-look tool doesn't move accuracy on the illegible-signal subset, the agent's one genuinely agentic behavior isn't paying off and you need to know that. LangSmith experiment comparison makes this a one-command diff.

---

## Build Order

### Phase 0 — Setup

- [ ] `.env`: `MAPILLARY_ACCESS_TOKEN`, `GEMINI_API_KEY`, `LANGCHAIN_API_KEY`, `LANGCHAIN_PROJECT=geoguessr-deepagent`, `LANGCHAIN_TRACING_V2=true`
- [ ] Add `.env` to `.gitignore` **before** the first commit
- [ ] Pin versions: `langgraph`, `langsmith`, `langchain-google-genai`, `requests`, `mercantile`, `haversine`, `pillow` (for cropping/upscaling), `python-dotenv`
- [ ] **Build the token cost model (Step 0). Do not proceed if the lean design isn't clearly cheaper than a single Pro call on easy images.**
- [ ] Confirm Gemini 3.x bbox coordinate format and do a quick crop-accuracy sanity check
- [ ] Define the target-country taxonomy (needed before the sampler)
- [ ] Register Mapillary + LangSmith apps; copy tokens to `.env`

### Phase 1 — Data

- [ ] Ingestion script: image-level `is_pano` filter, `mercantile` tiling, backoff, SQLite, failure log
- [ ] Dry run on 5–10 images/region
- [ ] Check pano density per region; set fallback policy for sparse regions
- [ ] Full ingestion (~500 images), **stratified** across continents/countries
- [ ] Freeze `eval_v1.csv`; upload to LangSmith. Verify no lat/lng/timestamp reaches model inputs.

### Phase 2 — Build

- [ ] **Step 1:** Extraction node — one structured vision pass returning the signals JSON with per-signal bbox + legibility. Validate schema in a LangSmith trace.
- [ ] **Step 2:** Deep-agent node with `lookup_regional_indicator`, `cross_reference_candidates`, `update_todolist`, `emit_prediction`. Reasoning over JSON only. Confirm the todolist varies per image in traces.
- [ ] **Step 3:** Add `reexamine_region` (crop + pad + upscale + re-read). Confirm it fires only on illegible/tied cases, not every image.
- [ ] **Step 4:** Eval harness. Run `baseline-flash`, `baseline-pro`, `baseline-opus`. Record in LangSmith.
- [ ] **Step 5:** Run full deep agent as `deepagent-v1`. Confirm it beats Flash and closes the gap to Pro. Produce the stratified table.
- [ ] **Step 6:** Ablate `reexamine_region` (`deepagent-no-relook` vs `deepagent-v1`). Keep it only if it helps the illegible-signal subset.

### Phase 3 — Polish

- [ ] Clean up reasoning-chain output for the demo
- [ ] CLI: image path → todolist trace + re-looks used + final point prediction + LangSmith trace URL
- [ ] (Later) web UI with streamed reasoning + live todolist

---

## Open Decisions

- **Re-look budget:** cap on `reexamine_region` calls per image (1? 3?). Tune against the illegible-signal subset — a runaway loop erases the cost advantage.
- **Re-look trigger:** legibility flag alone, candidate-tie alone, or both? Decide via the ablation.
- **Extraction resolution:** the resolution the full frame is sent at trades extraction quality vs. token cost — and interacts with how often re-looks are needed. Sweep it against the cost model.
- **Upscale method for crops:** simple resize vs. nothing — check whether upscaling actually improves the model's read or just adds tokens.
- **Heading strategy:** how many panorama headings to send to extraction (0/90/180/270?) and whether the agent can request a new heading as a tool call. More headings = more image tokens; weigh against the cost model.

---

## Resume / Interview Framing

**Target bullet (fill X, N with measured numbers):**

> "Built a LangGraph deep agent for image geolocation — a ReAct tool-calling loop with a variable todolist over a single-pass perception preprocessor, and a conditional crop-and-upscale re-examination tool that spends a second image call only on ambiguous inputs. Matched single-call Gemini Pro country accuracy at ~X% of the image-token cost across N held-out panoramas, and closed the gap to Opus on high-signal images."

**Talking points:**

- **Why not seven agents:** started there, modeled token cost, found the parallel specialists re-sent the image and added no accuracy over one reasoning step on extracted signals. Concentrated the agentic behavior into one loop where the compute-spending decision is real. _Removing complexity for a reason is the point._
- **What makes the loop a real agent:** the todolist and call count vary per image; the agent decides whether to spend a second image call based on evidence (illegible plate, tied candidates). That runtime compute decision — not a fixed checklist — is the agentic core, and it's visible in LangSmith.
- **Why perception is a single pass:** image tokens dominate cost; a model that can localize a signal can also read it in the same pass. Splitting "find" from "read" pays the image cost twice. Cropping only helps on a _closer_ look — hence on-demand `reexamine_region`, not an always-on spotter stage.
- **Why the clean baseline is Gemini Pro, not Opus:** same model family isolates architecture as the only variable. The Opus comparison answers a separate question (cheap-model agent vs. frontier model) and is labeled as such.
- **The honest result:** doesn't beat a frontier monolith overall on km-error. The stratified finding is the real one — on high-signal and recoverable-signal images it matches Pro (and rivals Opus) at a fraction of the token cost; on truly ambiguous images raw capability still wins.
