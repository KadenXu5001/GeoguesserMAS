# Picture data pipeline

The pipeline stores panorama and rendered image files on disk and stores their metadata,
checksums, validation history, and split membership in local MongoDB. Expiring Mapillary
image URLs are fetched only immediately before a download and are not persisted.

## Start local services

```powershell
docker compose up -d mongodb
.\.runtime-win\Scripts\python.exe main.py init-mongodb
```

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

Accepted originals are written under `data/panoramas/<ISO2>/`. Four 1024×1024 cardinal
views are written under `data/rendered/<ISO2>/<IMAGE_ID>/`. Re-running the command skips
images already downloaded or rendered.

## Inspect and view the results

```powershell
.\.runtime-win\Scripts\python.exe main.py list-pictures --status rendered
.\.runtime-win\Scripts\python.exe main.py contact-sheet <IMAGE_ID>
```

Contact sheets are written under `.artifacts/contact-sheets/` unless `--output` is given.
They contain headings 0, 90, 180, and 270 degrees in a 2×2 image.

## Continue collection deliberately

Increase `--limit` only after inspecting the first contact sheet. Choose the split explicitly:

```powershell
.\.runtime-win\Scripts\python.exe main.py ingest-pictures --country TH --split development --limit 10
.\.runtime-win\Scripts\python.exe main.py ingest-pictures --country BR --split evaluation --limit 5
```

MongoDB rejects retained panoramas within 10 km of an existing panorama in the same country
and rejects any Mapillary sequence that would cross development/evaluation splits. Rejected
and failed attempts remain in `ingestion_attempts` for auditing.
