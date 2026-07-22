# Phase 0 Cost Model

Last verified: 2026-07-10. Prices are standard, synchronous, global API list prices in USD. Recheck before the frozen evaluation because model IDs and prices change.

## Compared systems

- Gemini extraction and text agents: `gemini-3-flash-preview`.
- Opus baseline: `claude-opus-4-8` (use the latest available Opus release at evaluation time if this ID is unavailable).
- Every multimodal system receives the same four 1024×1024 views at headings 0°, 90°, 180°, and 270°.
- Batch discounts, caching discounts, free tiers, and US-only Anthropic inference premiums are excluded.

## Verified prices and token rules

| Model | Input / 1M tokens | Output / 1M tokens | Image accounting |
| --- | ---: | ---: | --- |
| Gemini 3 Flash Preview | $0.50 | $3.00 | Gemini 3 `media_resolution_high`: budget up to 1,120 tokens per image |
| Claude Opus 4.8 | $5.00 | $25.00 | 28×28 visual patches; 1024×1024 is `ceil(1024/28)^2 = 1,369` tokens |

Primary sources:

- Gemini API pricing: <https://ai.google.dev/gemini-api/docs/pricing>
- Gemini token counting and media resolution: <https://ai.google.dev/gemini-api/docs/tokens>
- Anthropic API pricing: <https://platform.claude.com/docs/en/about-claude/pricing>
- Anthropic vision token calculation: <https://platform.claude.com/docs/en/build-with-claude/vision>

The model uses conservative high-resolution Gemini accounting. Actual usage metadata replaces estimates in experimental reports.

## Recorded benchmark observations

Recorded on 2026-07-22. These observations are evidence, not replacements for the locked evaluation
required by the constitution.

| System | Accuracy | Total cost | Mean cost / run | Provenance |
| --- | ---: | ---: | ---: | --- |
| Direct Gemini 3 Flash Preview baseline | 80% (12/15) | $0.068931 | $0.0045954 | Measured on the reproducible 15-country `worldwide_v2` diverse local subset; 15/15 calls succeeded |
| Production MAS | approximately 87% | Not supplied | $0.033 (3.3 cents) | User-reported testing result; dataset and run count not yet recorded |

The Flash baseline used `gemini-3-flash-preview` with one four-image call per panorama and no MAS,
reference lookup, retry, or LangSmith trace. Its measured usage was 66,390 input tokens, 1,645 visible
output tokens, and 10,267 reasoning tokens, for 78,302 total tokens. The local artifacts are
`.artifacts/gemini-3-flash-worldwide-diverse-15.jsonl` and
`.artifacts/gemini-3-flash-worldwide-diverse-15-summary.json`.

The user-reported MAS mean cost is $0.033 per run, equivalent to 3.3 cents per panorama.

## Assumptions

These are budgets, not measured results. Each path must log actual prompt, output, thinking, cached, and modality token counts.

| Call | Text input | Image input | Output (including thinking where billed) |
| --- | ---: | ---: | ---: |
| Flash extraction | 600 | 4 × 1,120 | 1,200 |
| Flash orchestrator decision | 2,400 | 0 | 400 |
| Flash specialist | 2,000 | 0 | 500 |
| Flash orchestrator finalization | 3,200 | 0 | 400 |
| Flash orchestrator review/re-examination decision | 2,400 | 0 | 400 |
| Flash crop re-examination | 300 | 1,120 | 350 |
| Opus direct baseline | 600 | 4 × 1,369 | 600 |

The extraction output is the main text-context risk. Keep it compact and do not paste entire reference tables into prompts.

## Estimated standard-path costs

Computed by `python -m geoguesser.cost_model`:

| Path | Estimated cost / panorama | Savings vs Opus |
| --- | ---: | ---: |
| Opus direct baseline | $0.045380 | — |
| MAS easy (extract → orchestrator answer) | $0.008540 | 81.18% |
| MAS delegated (extract → orchestrator → one specialist → final) | $0.013840 | 69.50% |
| MAS hard (delegated + one crop) | $0.018000 | 60.33% |
| Single deep-agent budget | $0.013340 | 70.60% |

Under these conservative budgets, all MAS paths clear the requirement of at least 10% savings. The gate is provisional until measured token usage exists.

## Enforceable v1 budgets

- Full-scene extraction calls: exactly 1.
- Specialist calls: at least 1 and at most 2; each configured specialist may be called once.
- Global capacity: stop with a warning and no further API calls at 180 seconds or $0.50.
- Crop re-examination calls: at most 1.
- Orchestrator model calls: at most 3 (delegation decision, review/re-examination decision, and finalization).
- Flash extraction output: at most 1,200 billed output/thinking tokens.
- Flash specialist output: at most 500 billed output/thinking tokens.
- Each orchestrator turn: at most 400 billed output/thinking tokens.
- Crop answer: at most 350 billed output/thinking tokens.
- If accumulated estimated cost reaches 90% of the current Opus budget, force immediate final prediction without further delegation or re-examination.

The 90% runtime cutoff preserves the contractual 10% savings. Use current prices and actual usage metadata in the cutoff calculation.

## Evaluation accounting

For each panorama and each system, store:

- model ID and price-table version/date;
- text, image, cached, thinking, and output tokens per call;
- dollar cost per call and total cost;
- call count and latency;
- specialist and crop usage;
- exact country result and centroid-based haversine loss.

Report the mean complete cost over `eval_c1.csv`. The MAS passes only if mean cost is no more than 90% of the Opus mean and exact country accuracy is within five percentage points.

## Remaining validation

- Confirm the chosen Gemini and Opus IDs are accessible with project credentials.
- Run token-count endpoints on the exact four-image payload and replace image-token budgets with observed counts.
- Measure output/thinking usage on `dev_v1.csv`; reduce limits if quality permits.
- Recheck prices immediately before final evaluation.
