# Picture data pipeline

The pipeline stores panorama and rendered image files in a local content-addressed object
store and stores their metadata, checksums, validation history, quality-review state, and split
membership in local MongoDB. Expiring Mapillary image URLs are fetched only immediately before
a download and are not persisted.

Set `LOCAL_OBJECT_STORE_ROOT` to choose the storage root. The default is the ignored
`.local-data/` directory. Original panoramas are curator-only objects under the
`source-private` namespace. Sanitized cardinal views are separate `runtime-private` objects:

```text
.local-data/
  source-private/countries/<ISO2>/objects/<sha256-prefix>/<sha256>.<ext>
  runtime-private/countries/<ISO2>/objects/<sha256-prefix>/<sha256>.<ext>
```

Country folders use stable ISO codes (`FR`, `GB`, and so on), while display names and user-facing
aliases stay in versioned dataset metadata. The reserved future subdivision layout is
`countries/GB/subregions/GB-ENG/...`, allowing a selector such as France plus England to resolve
`FR` and `GB-ENG` without renaming or duplicating the existing country-level collection.

MongoDB retains a transitional local `path` for current tools and also records the portable
`storage_namespace` and `object_key`, plus SHA-256, CRC32C, byte count, and media type. Cloud
uploaders can map the same namespace and object key to a bucket without rewriting dataset
identity. Existing pilot files under `data/panoramas/` and `data/rendered/` remain readable and
are not moved or modified.

## Start local services

```powershell
docker compose up -d mongodb
.\.runtime-win\Scripts\python.exe main.py init-mongodb
```

Register the frozen 30-country collection definition before worldwide ingestion:

```powershell
.\.runtime-win\Scripts\python.exe main.py register-dataset --dataset worldwide_v2
```

The versioned definition is stored at `data/dataset_definitions/worldwide_v2.json`. It is
checksum-bound to the reviewed Mapillary coverage report and records the selected countries,
split targets, split seed, quality policy, and storage policy. Its dataset status remains `draft`
while the country selection itself is frozen; the dataset becomes `frozen` only after collection,
manual review, manifest export, and integrity validation are complete.

## Migrate the frozen pilot into the object store

Run the manifest-driven migration before collecting `worldwide_v2`:

```powershell
.\.runtime-win\Scripts\python.exe main.py migrate-local-assets --dataset pilot_v1
```

The migration verifies every panorama and cardinal-view SHA-256 against `dev_v1.csv` and
`eval_c1.csv`, writes the 225 assets into their `FR`, `TH`, or `BR` object-store folders, enriches
the matching MongoDB records, and writes `data/migrations/pilot_v1_object_store.json`. After the
entire replacement set is verified, it removes the legacy media files. The frozen manifest bytes,
labels, splits, quality results, and review decisions remain unchanged. The frontend resolves its
media through the completed server-only migration report, so country folders and filesystem paths
remain hidden before a guess.

Production MAS runs also resolve each manifest image identity through that completed migration
report and reconstruct the four local paths from the `runtime-private` object keys. They do not
use the frozen legacy path columns after migration, and they fail closed if a migrated identity,
object, or manifest checksum is inconsistent.

Use `--keep-legacy` only for a non-destructive dry migration that retains the old media files.

## Install the pinned offline boundaries

```powershell
.\.runtime-win\Scripts\python.exe main.py download-boundaries
```

This downloads Natural Earth 5.1.1 Admin-0 Countries at 1:10m resolution into the ignored
`data/boundaries/` directory. A candidate is retained only when this offline lookup agrees
with its expected pilot country.

## Download and render a safe test sample

The default limit is one candidate. Use a country filter to make the test deterministic:

```powershell
.\.runtime-win\Scripts\python.exe main.py ingest-pictures --country FR --limit 1
```

Accepted originals and their four 1024x1024 cardinal views are written into the object-store
namespaces above. Automatic quality checks run after download; passing panoramas are rendered
and moved to `quality_review` for manual approval. Re-running the command skips images already
downloaded, rejected, under review, or rendered.

## Inspect and review the results

```powershell
.\.runtime-win\Scripts\python.exe main.py list-pictures --status quality_review
.\.runtime-win\Scripts\python.exe main.py contact-sheet <IMAGE_ID>
.\.runtime-win\Scripts\python.exe main.py strip-preview <IMAGE_ID>
.\.runtime-win\Scripts\python.exe main.py assess-quality <IMAGE_ID>
```

Contact sheets are written under `.artifacts/contact-sheets/` unless `--output` is given.
They contain headings 0, 90, 180, and 270 degrees in a 2x2 image. Strip previews are
written under `.artifacts/strip-previews/` and show the same headings in order from left to
right for faster continuity review.

After inspecting the previews, approve or reject the panorama:

```powershell
.\.runtime-win\Scripts\python.exe main.py review-quality <IMAGE_ID> approve --notes "clear 360 coverage"
.\.runtime-win\Scripts\python.exe main.py review-quality <IMAGE_ID> reject --notes "severe camera/operator artifact"
```

## Continue collection deliberately

Increase `--limit` only after inspecting the first contact sheet and strip preview. Choose
the split explicitly:

```powershell
.\.runtime-win\Scripts\python.exe main.py ingest-pictures --country TH --split development --limit 10
.\.runtime-win\Scripts\python.exe main.py ingest-pictures --country BR --split evaluation --limit 5
```

MongoDB rejects retained panoramas within 10 km of an existing panorama in the same country
and rejects any Mapillary sequence that would cross development/evaluation splits. Automatic
quality failures and manual rejections remain rejected, so strict replacement runs continue
to later candidates. Rejected and failed attempts remain in `ingestion_attempts` for auditing.

## Generate replacement coverage pools

When the original 15-row coverage pool for a country is exhausted, generate a larger
country-specific replacement scan with the same offline boundary filter used by ingestion:

```powershell
.\.runtime-win\Scripts\python.exe -m geoguesser.coverage --country TH --target 40 --max-tiles 80 --boundary-filter --output data\coverage_scan_TH_replacements.json
.\.runtime-win\Scripts\python.exe main.py ingest-pictures --country TH --split evaluation --limit 5 --coverage-path data\coverage_scan_TH_replacements.json
```

## Export the pilot manifests

After every retained panorama is manually approved, export the split manifests:

```powershell
.\.runtime-win\Scripts\python.exe main.py export-pilot-manifests --output-dir data\datasets
```

The exporter validates exact pilot counts before writing:

- `data/datasets/dev_v1.csv`: 10 development panoramas per pilot country.
- `data/datasets/eval_c1.csv`: 5 evaluation panoramas per pilot country.

The manifests include labels, local image paths, image dimensions, and checksums. They do
not include latitude, longitude, capture timestamp, or Mapillary expiring URLs.
