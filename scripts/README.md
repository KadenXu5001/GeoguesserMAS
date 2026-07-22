# Baseline scripts

## Local MAS accuracy

The local evaluator reads the versioned reference JSON directly; MongoDB does not need to be
running and the snapshot does not need to be seeded. With the rendered evaluation images present,
run the held-out set and summarize it with:

```powershell
python scripts\run_mas.py --dataset data\datasets\eval_c1.csv --limit 0 --output .artifacts\mas-eval-c1.jsonl
python scripts\summarize_results.py .artifacts\mas-eval-c1.jsonl
```

The MAS still requires `GEMINI_API_KEY` and the mandatory LangSmith settings from `.env`.

From the repository root, activate the project virtual environment and run:

```powershell
& .\.venv\Scripts\Activate.ps1
python scripts\run_gemini_pro.py --limit 1
```

Run the complete development manifest with:

```powershell
python scripts\run_gemini_pro.py --dataset data\datasets\dev_v1.csv --limit 0
```

The script uses Google's current `gemini-3.1-pro-preview` model. Each panorama is written as one JSONL record under `.artifacts/`. MAS LangSmith
tracing is enabled for debugging. Uploads are synchronous because the trace
contains four multimodal inputs and must finish before the process exits.
`gemini-pro-baseline` run in the configured project.

## Claude Opus versus MAS

Set `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, and the required LangSmith variables in `.env`, then run
the paired comparison over the same dataset rows:

```powershell
python scripts\compare_claude_opus_mas.py --limit 10
```

Use `--limit 0` for the complete dataset. The runner defaults to `OPUS_MODEL` from `.env` and writes
row-level JSONL plus a JSON summary under `.artifacts/`. The summary includes attempted and successful
runs, country accuracy (failures count as incorrect), paired accuracy, input/output token totals,
total cost, mean cost, and cost per correct answer. Opus pricing defaults to $5 input / $25 output
per million tokens and can be overridden with `--opus-input-price` and `--opus-output-price`.

## Direct Gemini 3 Flash baseline

Run one direct four-image Gemini call per held-out panorama, without MAS components or LangSmith:

```powershell
python scripts\run_gemini_flash.py --dataset data\datasets\eval_c1.csv --limit 0
```

The runner resolves the checksum-validated original views from the local object store and writes
row-level predictions plus an accuracy/token/cost summary under `.artifacts/`.

## Reference clue snapshot

Download each country section from its GeoTips regional page and build one self-contained HTML file
per active `worldwide_v2` country with:

```powershell
node scripts\download_country_hint_files.mjs
```

The regional pages contain complete country sections, and their map/navigation links jump to those
sections. The command extracts each complete section, embeds its available images as data URLs,
and records page, file, and image hashes in `countryhintsfiles/manifest.json`. It follows
`reference_generation` exclusions, so Morocco is omitted while its temporary hold is active. Use
`--country TN` for a one-country run or `--skip-images` for smaller HTML files that retain remote
image URLs. Images are normalized from GeoTips' lazy-loading attributes into ordinary eager `src`
attributes so standalone viewers do not display transparent placeholders. Repair an existing
download without fetching it again with
`node scripts\download_country_hint_files.mjs --repair-existing`. Generated source material is
ignored by Git and is not used for live inference.

Inspect the GeoTips section mapping and relevant-image count without changing the snapshot with:

```powershell
node scripts\update_reference_clues.mjs --dry-run
```

Regenerate all mapped universal, urban, and rural GeoTips clues and transiently inspect each
distinct relevant image with Gemini:

```powershell
node scripts\update_reference_clues.mjs --analyze-images
```

The generator reads `temporary_exclusions` from `worldwide_v2`, fetches each active country's
GeoTips continent page, maps every supported section into the existing specialist categories, and
records retrieval dates and source-page SHA-256 digests. Flags, capitals, subdivisions, Google
car/camera/coverage metadata, and unmapped sections are reported but never silently forced into an
unrelated tool. Relevant images are held only in memory, deduplicated by SHA-256, sent to the model
configured by `GEMINI_REFERENCE_MODEL`, and discarded. The snapshot retains only normalized visual
descriptions, source URLs, hashes, model ID, and prompt version. `--max-images` defaults to 600 and
causes a fail-closed exit before Gemini calls when the source exceeds that bound.

For the local-only production handoff, regenerate the 29 country JSON files from the downloaded
HTML and then build the versioned runtime snapshot with:

```powershell
node scripts\generate_country_reference_files.mjs
node scripts\build_reference_snapshot.mjs
python main.py seed-references --snapshot data\reference_tables\reference_v2.json
```

This path performs no network or model API calls. `reference-v2` replaces GeoTips-derived rows
with the country-file rows, keeps one deterministic category per clue, and is the default snapshot
for the website MAS and command-line MAS. MongoDB reference-row identity includes country so the
same normalized indicator can be retained independently for every country.
