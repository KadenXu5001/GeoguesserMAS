# GeoGuessr Multi-Agent System

A cost-controlled, multimodal country geolocation system built with Gemini, LangChain Deep
Agents, LangGraph, MongoDB, and LangSmith. Try it out at https://geo-trainer.com/!

The system converts a Mapillary panorama into four cardinal street views, extracts structured
visual evidence, delegates the unresolved geographic question to an urban or rural specialist,
and emits one country prediction. Runtime middleware enforces the workflow, tool limits, privacy
rules, and capacity limits in code.

## Benchmark snapshot

| System                        |          Country accuracy | Mean cost per panorama | Evidence               |
| ----------------------------- | ------------------------: | ---------------------: | ---------------------- |
| Direct Gemini 3 Flash Preview |               80% (12/15) |      $0.004595 (0.46¢) | Measured run           |
| GeoGuessr MAS                 |              ~87% (27/31) |          $0.033 (3.3¢) | Current project result |
| Claude Opus 4.8               | ≈94% (14/15; 93.3% exact) |        $0.0365 (3.65¢) | External measured run  |

At the reported operating points, the MAS improves on the direct Gemini baseline by about
7 percentage points while costing about 7.2 times more per panorama. The external Opus run adds
about 6.3 percentage points over the MAS at a similar cost: approximately 10.6% more per panorama
than the reported MAS result.

These results are a progress snapshot, not yet a controlled three-system comparison. The Gemini
result is reproduced by a recorded 15-country run in this repository. The MAS result is the
current project figure accumulated across training, while the Opus values come from an actual
15-attempt run performed on a separate server with Anthropic access. Its row-level artifacts are
not stored in this repository.
See [the benchmark notes](docs/BENCHMARK_README.md) and
[cost model](docs/cost_model.md) for the existing evidence and accounting assumptions.

## How it works

```text
Mapillary panorama
        |
        v
Four 1024x1024 views (0°, 90°, 180°, 270°)
        |
        v
Structured visual extraction
        |
        v
Multimodal supervisor scans the images and extraction
        |
        +--> urban specialist --> bounded local clue lookups
        |
        +--> rural specialist --> bounded local clue lookups
        |
        +--> optional one-shot regional re-examination
        |
        v
One structured country prediction
```

The production path is deliberately finite:

1. The supervisor creates the canonical four-item todo list.
2. `extract_visual_evidence` processes all four views exactly once.
3. The supervisor inspects the images and delegates to at least one specialist.
4. `reexamine_region` may run once only when two country signals remain within 10 confidence
   points.
5. `emit_prediction` returns one country and terminates the run.

The urban specialist handles built-environment clues such as road markings, signs, vehicles,
utilities, and architecture. The rural specialist handles terrain, vegetation, soil, climate, and
low-density settlement clues. Both use versioned local reference data; inference does not browse
the web.

## Runtime and safety guarantees

The rules in [CONSTITUTION.md](CONSTITUTION.md) are enforced by prompts, schemas, and runtime
middleware:

- all four cardinal images and the validated extraction reach the multimodal supervisor;
- at least one, and at most two, configured specialists run per panorama;
- a specialist can run only once and has bounded, evidence-justified reference lookups;
- hidden evaluation metadata, coordinates, labels, image IDs, filenames, and raw paths are
  rejected from model-facing payloads;
- extraction is single-use and fail-closed;
- execution stops at three minutes or $0.50, whichever comes first;
- the supervisor has a four-turn ceiling including extraction; and
- LangSmith tracing is mandatory and synchronously flushed, with raw base64 image data redacted
  from uploaded traces.

Each result includes a compact decision log for observable routing, tool authorization, budget
state, specialist output, and final evidence. It does not store hidden chain-of-thought.

## Repository layout

| Path                           | Purpose                                                                    |
| ------------------------------ | -------------------------------------------------------------------------- |
| `src/geoguesser/`              | Dataset, vision, MAS runtime, tools, budgets, tracing, and evaluation code |
| `scripts/run_mas.py`           | End-to-end batch MAS runner                                                |
| `scripts/run_gemini_pro.py`    | Direct Gemini Pro baseline runner                                          |
| `scripts/summarize_results.py` | Accuracy, cost, latency, and tool-use summary                              |
| `data/datasets/`               | Development and frozen pilot evaluation manifests                          |
| `data/reference_tables/`       | Versioned local clue snapshots and country rows                            |
| `data/dataset_definitions/`    | Dataset scope, split, and quality contracts                                |
| `web/`                         | React panorama and evidence inspector with a Node/MongoDB backend          |
| `tests/`                       | Unit and integration coverage for the pipeline and runtime invariants      |
| `docs/`                        | Benchmark, cost, pipeline, inspector, and decision-log documentation       |
| `backlog.md`                   | Detailed completed work, next steps, and blockers                          |

## Project progress

### Implemented

- Mapillary panorama discovery, download, retry handling, and offline country validation
- Local content-addressed media storage with MongoDB metadata
- Panorama quality checks, manual review state, and strict replacement behavior
- Four 1024×1024 cardinal renders, contact sheets, and strip previews
- A 45-panorama France/Thailand/Brazil pilot with 30 development and 15 evaluation rows
- A draft 30-country worldwide definition targeting 450 panoramas
- Recursive model-payload safety audits
- Structured Gemini extraction with validated objects, signals, and bounding boxes
- Extraction-first Deep Agents supervisor with urban and rural specialists
- Versioned, bounded universal and specialist reference lookup tools
- Optional evidence-gated regional re-examination
- Runtime turn, tool, token, time, and cost enforcement
- Direct baseline runners, JSONL results, and evaluation summaries
- Synchronous LangSmith tracing and a redacted decision log
- A React panorama inspector for extraction and informed-evidence overlays

### In progress

- Record the reported MAS and Opus benchmarks on the same frozen manifest as Gemini
- Ensure every live Gemini response completes through the required tool path
- Tune only on the development split, then freeze prompts, models, policies, and references
- Run the final paired evaluation and the no-re-examination ablation
- Replace provisional token and iteration budgets with measured development-set usage
- Review the pilot before completing the 30-country dataset expansion
- Add a concise terminal UI for todos, specialists, confidence, cost, and trace links

## Requirements

- Python 3.11 or newer
- Docker, or another reachable MongoDB instance
- Node.js and npm for the web inspector
- Gemini, Mapillary, and LangSmith credentials for live ingestion and MAS runs

Copy `.env.example` to `.env` and fill in the credentials needed for the operation you plan to
run. Never commit `.env`, provider credentials, private keys, raw private panorama assets, or
generated result artifacts.

## Setup

Create a virtual environment and install the Python project:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
```

Start MongoDB, initialize its schema, and seed the current reference snapshot:

```powershell
docker compose up -d mongodb
python main.py init-mongodb
python main.py seed-references
```

Useful setup and dataset commands are available through:

```powershell
python main.py --help
```

## Run the MAS

Run one development panorama:

```powershell
python scripts\run_mas.py --limit 1
```

Run a complete manifest and choose the JSONL output path:

```powershell
python scripts\run_mas.py `
  --dataset data\datasets\eval_c1.csv `
  --limit 0 `
  --output .artifacts\mas-eval-c1.jsonl
```

Live runs make paid provider calls and require seeded MongoDB reference data. The runner compiles
the graph once for the batch, uses a fresh budget for each panorama, writes one JSON object per
row, and flushes LangSmith traces before exiting.

Summarize a result file:

```powershell
python scripts\summarize_results.py .artifacts\mas-eval-c1.jsonl
```

The summary reports exact country accuracy, complete cost, image-token accounting, latency, call
count, specialist rate, and re-examination rate.

## Run the web inspector

With MongoDB running and the Python environment configured:

```powershell
cd web
npm install
npm start
```

Open `http://localhost:3000`. The inspector selects panoramas from the same manifests used by the
MAS, persists browser-safe analysis in MongoDB, and displays extracted bounding boxes and selected
evidence without revealing the answer to the browser. More detail is in
[docs/vision_inspector.md](docs/vision_inspector.md).

## Tests

Run the Python suite:

```powershell
python -m pytest
```

Run the web tests and production build:

```powershell
cd web
npm test
npm run build
```

The tests cover dataset integrity, image processing, payload privacy, extraction, specialist
contracts, reference data, budget middleware, tool ordering, tracing, evaluation, and the web
reference pipeline.

## Known limitations

- The headline benchmarks do not yet share one frozen, paired evaluation dataset.
- The worldwide dataset definition is still marked `draft`.
- Final prompt, model, reference, and runtime-budget versions have not been frozen.
- Production-model bounding-box validation has encountered temporary Gemini 503 responses.
- The direct Gemini measurement is based on only 15 panoramas and should be expanded.
- Cost varies with model pricing, reasoning-token usage, and output length; recheck provider prices
  before publishing a final comparison.

The detailed work queue and current blockers are maintained in [backlog.md](backlog.md).
