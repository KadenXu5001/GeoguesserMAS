# GeoGuessr Accuracy and Cost Benchmarks

This document records the current country-prediction accuracy and inference cost observations for
the direct Gemini 3 Flash baseline, the GeoGuessr multi-agent system (MAS), and a Claude Opus 4.8 benchmark.

## Headline results

| System                        |         Country accuracy |  Mean cost per run | Evidence status        |
| ----------------------------- | -----------------------: | -----------------: | ---------------------- |
| Direct Gemini 3 Flash Preview |              80% (12/15) | $0.0045954 (0.46¢) | Measured run           |
| GeoGuessr MAS                 |        Approximately 87% |      $0.033 (3.3¢) | Current project result |
| Claude Opus 4.8               | 94% (14/15; 93.3% exact) |    $0.0365 (3.65¢) | External measured run  |

Based on these observations, the MAS has a reported accuracy advantage of approximately 7
percentage points and costs approximately 7.18 times as much per panorama as Flash. The external
Opus run improves on the reported MAS accuracy by about 6.3 percentage points while costing
about 10.6% more per panorama.

These figures are not yet a controlled paired comparison. The Flash result comes from the recorded
15-country subset below. The Opus result comes from an actual run on a separate server with
Anthropic access, but its row-level outputs, provider usage, configuration, and traces are not
stored in this repository. The MAS result also lacks a shared, repository-recorded manifest with
the two baselines.

## Direct Gemini 3 Flash benchmark

The measured baseline used `gemini-3-flash-preview`. Each panorama received exactly one direct API
call containing four locally rendered 1024x1024 views at headings 0, 90, 180, and 270 degrees. It
did not use the MAS supervisor, extraction phase, specialists, reference data, MongoDB, retries, or
LangSmith.

The subset contains one deterministic local panorama from each of 15 countries across six
continents:

- Europe: Germany, United Kingdom, Spain
- North America: United States, Mexico
- South America: Argentina, Chile
- Asia: Japan, South Korea, India, Indonesia
- Africa: South Africa, Kenya
- Oceania: Australia, New Zealand

All 15 calls returned valid structured responses. The three incorrect predictions were:

| Ground truth | Prediction | Confidence |
| ------------ | ---------- | ---------: |
| Chile        | Argentina  |         90 |
| India        | Nepal      |         98 |
| New Zealand  | Australia  |         75 |

### Flash token and cost accounting

| Metric                      |       Value |
| --------------------------- | ----------: |
| Attempts                    |          15 |
| Correct                     |          12 |
| Input tokens                |      66,390 |
| Visible output tokens       |       1,645 |
| Reasoning tokens            |      10,267 |
| Total tokens                |      78,302 |
| Total cost                  |   $0.068931 |
| Mean cost per attempt       |  $0.0045954 |
| Cost per correct prediction | $0.00574425 |

The cost includes reported reasoning tokens at the configured Gemini output-token price.

## Claude Opus 4.8 benchmark

The Opus comparison is an actual 15-attempt run performed on a separate server, matching the Flash
attempt count. It did not require a separately purchased Anthropic API key for this repository.
Because its row-level predictions, provider usage, configuration, and traces are not available
locally, this document records it as an external measured result rather than a
repository-reproduced result.

| Metric                 | Flash baseline |                                    Opus 4.8 |
| ---------------------- | -------------: | ------------------------------------------: |
| Attempts               |             15 |                                          15 |
| Correct                |             12 |                                          14 |
| Accuracy               |            80% |             93.3% exact (approximately 94%) |
| Confidence calibration |       Moderate |                                      Higher |
| Hallucination rate     |            Low |                                    Very low |
| Reasoning tokens       |         10,267 | Approximately 31,000, depending on settings |
| Total cost             |      $0.068931 |                                     $0.5475 |
| Mean cost per attempt  |     $0.0045954 |                                     $0.0365 |

Confidence calibration and hallucination rate are qualitative assessments from the external run,
not metrics derived by the repository summarizer. The external Opus total is about
7.94 times the measured Flash total.

### Flash artifacts

- Selection manifest: `.artifacts/worldwide-diverse-15-selection.json`
- Evaluation CSV: `.artifacts/worldwide-diverse-15.csv`
- Row-level predictions: `.artifacts/gemini-3-flash-worldwide-diverse-15.jsonl`
- Summary: `.artifacts/gemini-3-flash-worldwide-diverse-15-summary.json`

The `worldwide_v2` definition is currently marked `draft`. This subset is reproducible from the
local content-addressed store, but it is not the final locked worldwide evaluation split.

## MAS observation

The current MAS observation is user-reported:

- Country accuracy: approximately 87%
- Mean cost: $0.033 per run, or 3.3 cents per panorama

The MAS runtime still follows the repository constitution: four cardinal images, mandatory visual
extraction, at least one specialist, bounded reference lookup, single-pass phase ordering, hard
runtime and cost limits, and synchronous LangSmith tracing. The reported figure should be augmented
with its dataset manifest, model ID, sample count, row-level predictions, token usage, and trace IDs
before it is used as formal benchmark evidence.

## Reproduce the Flash baseline

With `GEMINI_API_KEY` configured and the local worldwide views available:

```powershell
python scripts\run_gemini_flash.py `
  --dataset .artifacts\worldwide-diverse-15.csv `
  --limit 0 `
  --output .artifacts\gemini-3-flash-worldwide-diverse-15.jsonl `
  --summary .artifacts\gemini-3-flash-worldwide-diverse-15-summary.json
```

The baseline makes one provider call per row and counts a failed or malformed response as an
incorrect attempt.

## Next controlled comparison

For a defensible comparison:

1. Freeze a worldwide evaluation manifest before any system sees its labels.
2. Run direct Gemini 3 Flash, the MAS, and Opus exactly once on every row.
3. Count failures as incorrect for every system.
4. Record input, visible output, reasoning, cached, and image tokens from provider metadata.
5. Compare paired country accuracy, mean complete cost, latency, and cost per correct prediction.

Pricing assumptions and the longer-term evaluation gate are documented in
[`cost_model.md`](cost_model.md).
