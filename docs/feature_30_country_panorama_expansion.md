# Feature specification: 30-country panorama expansion

Status: Proposed  
Owner: GeoGuessr MAS  
Target dataset: `worldwide_v2`  
Primary imagery provider: Mapillary  
Fallback imagery provider: KartaView

## Summary

Expand the supported panorama dataset from the three-country pilot to at least 30 countries.
Mapillary remains the primary provider because the current pipeline already supports its coverage,
metadata, downloads, and licensing model. KartaView is introduced as an optional fallback for a
country only when a deeper Mapillary scan cannot produce enough qualifying panoramas.

The only geographic content required from an imagery provider is:

- the panorama capture location; and
- the panoramic image asset.

Provider identifiers, sequence identifiers, license details, and attribution are retained as
operational provenance for deduplication, split isolation, auditing, and legal compliance. They are
not country knowledge and must never be exposed to the prediction model.

## Background

The frozen pilot manifests currently contain 10 development and 5 evaluation panoramas each for
France, Thailand, and Brazil. This is a dataset limitation, not the current Mapillary coverage
limit. The existing coverage scan has already qualified 20 countries across six continents using
15 panorama sequences at least 10 km apart per country.

The original scan evaluated only 31 candidates and stopped unsuccessful candidates after four
sampled tiles. Expansion should first deepen and broaden the Mapillary scan before adding another
provider.

`worldwide_v2` retains its frozen 30-country taxonomy and 450-panorama target. A country may be
listed under `temporary_exclusions` with explicit operational scopes when its reference evidence
is under review. Such a hold does not alter qualification or the frozen target: Morocco is
temporarily excluded from play, reference generation, and evaluation while its clue enrichment is
rebuilt. Removing the hold requires updating the dataset definition and regenerating the affected
artifacts.

## Goals

- Freeze a dataset containing at least 30 coverage-qualified countries.
- Retain exactly 10 development and 5 evaluation panoramas per selected country.
- Preserve at least 10 km separation between retained panoramas within a country.
- Prevent source sequences from crossing development and evaluation splits.
- Keep all accepted inputs as complete equirectangular panoramas that can produce the four existing
  1024 x 1024 cardinal views.
- Keep collection reproducible, auditable, resumable, and provider-neutral.
- Preserve the existing quality threshold and manual approval workflow.
- Prevent coordinates, country labels, source IDs, filenames, checksums, split data, and other
  hidden evaluation metadata from entering MAS model payloads.

## Non-goals

- Replacing the four-view inference format with an interactive panorama viewer.
- Using live imagery-provider calls during MAS inference.
- Adding city, region, landmark, demographic, or cultural metadata to country records.
- Using Google Street View as a bulk dataset source.
- Changing the supervisor, specialist, extraction, re-examination, budget, or termination policies.
- Expanding or tuning the specialist reference table as part of panorama collection.
- Changing frontend layout or interaction behavior.

## Product decisions

### Provider strategy

1. Mapillary is queried first for every candidate country.
2. A country qualifies from Mapillary when the scan finds at least 15 eligible panoramic sequences
   that meet the distance and boundary rules.
3. KartaView may be queried only after the configured deep Mapillary scan is exhausted and the
   reason for fallback is recorded.
4. Panoramas from both providers may be used within one country, but a single provider is preferred
   when it can satisfy all 15 slots.
5. Google Street View is excluded because the local, frozen dataset requires persistent image
   storage and repeatable offline rendering.

### Country selection

- Start with the 20 countries already frozen in `data/taxonomy.json`.
- Expand the candidate catalog to at least 45 countries before rescanning.
- Select at least 30 countries that pass the same qualification policy.
- Preserve coverage across at least five continents.
- The final country list is coverage-driven and is frozen only after the complete scan report is
  reviewed.
- A country is not considered supported merely because one panorama is available.

### Dataset size

The minimum completed dataset contains 450 accepted panoramas:

| Split | Per country | 30-country minimum |
| --- | ---: | ---: |
| Development | 10 | 300 |
| Evaluation | 5 | 150 |
| Total | 15 | 450 |

Rejected candidates do not count toward these totals and must be replaced.

## User stories

- As a dataset curator, I can scan a large country candidate catalog and see which countries have
  enough separated panoramic coverage.
- As a dataset curator, I can resume collection without downloading or reviewing the same source
  panorama twice.
- As a reviewer, I can approve or reject panoramas using the existing contact sheet and ordered
  strip preview.
- As an evaluator, I can run the same MAS input contract against every selected country without
  exposing ground-truth metadata.
- As a maintainer, I can add another imagery provider without rewriting boundary validation,
  quality checks, rendering, storage, or manifest export.

## Functional requirements

### FR1: Provider-neutral imagery interface

Introduce an imagery-provider contract with these capabilities:

- discover panoramic candidates within a geographic area;
- fetch current metadata for one candidate;
- enumerate panoramic images belonging to a source sequence; and
- download the original panoramic asset.

The normalized candidate returned by a provider must contain:

| Field | Purpose |
| --- | --- |
| `provider` | Stable provider name such as `mapillary` or `kartaview` |
| `provider_image_id` | Provider-scoped image identity |
| `provider_sequence_id` | Provider-scoped sequence identity |
| `location` | GeoJSON point in longitude/latitude order |
| `is_panorama` | Explicit panorama eligibility flag |
| `width`, `height` | Source dimensions when available |
| `captured_at` | Optional audit metadata; never exported to model inputs |
| `quality_score` | Optional provider score; never substitutes for local quality checks |
| `license` | SPDX-compatible license identifier or recorded provider terms |
| `attribution` | Required attribution data or source URL |

Provider-specific response fields must remain inside the provider adapter.

### FR2: Stable source identity

- Use `(provider, provider_image_id)` as the unique panorama identity.
- Use `(provider, provider_sequence_id)` for split-leakage enforcement.
- Existing Mapillary records are migrated logically as `provider=mapillary` without changing their
  accepted image bytes or review decisions.
- Storage paths must avoid collisions between providers.
- Curator-facing and runtime object stores group assets under stable ISO country-code folders.
  Country folders use ISO 3166-1 alpha-2 codes rather than display names so renaming or aliasing a
  country does not move stored objects.
- The reserved hierarchy for future subdivision datasets is
  `countries/<ISO2>/subregions/<ISO-3166-2>/...`. Subdivision aliases and membership are versioned
  dataset metadata; they are not inferred from folder names and are never exposed to the model.
- Within each geographic folder, asset names remain content-addressed so repeated ingestion is
  idempotent and checksum-verifiable.

### FR3: Expanded coverage scan

- Accept a versioned country candidate catalog containing ISO 3166-1 alpha-2 code, display name,
  continent, and bounding box.
- Use adaptive tiling rather than a fixed four-tile sample.
- Validate every retained candidate against the pinned offline country boundaries.
- Deduplicate candidates by provider image and provider sequence.
- Select candidates greedily subject to the 10 km minimum separation.
- Continue scanning until the target is met or the configured per-country search budget is
  exhausted.
- Record tiles searched, candidates rejected, qualified sequence count, provider, failure reason,
  and scan configuration in the report.
- Never interpret an exhausted shallow sample as proof that a provider has no country coverage.

### FR4: Fallback-provider policy

- Run the deep Mapillary scan before KartaView fallback.
- Record one of these Mapillary outcomes before fallback: `insufficient_coverage`,
  `insufficient_panorama_coverage`, `quality_pool_exhausted`, or `provider_error`.
- Apply identical boundary, distance, sequence, image-shape, rendering, and quality rules to
  KartaView candidates.
- Record the source provider in internal metadata and collection reports.
- Do not expose the provider name to the model because capture-system artifacts may leak dataset
  construction information.

### FR5: Ingestion and quality control

- Download source URLs only when needed and do not persist expiring URLs.
- Require a plausible complete equirectangular panorama before rendering.
- Run the existing automatic quality policy for dimensions, aspect ratio, wrap continuity, blur,
  clipping, and severe defects.
- Require manual review before a panorama reaches `rendered` status.
- Retain failed and rejected attempts for audit and strict replacement.
- Render headings 0, 90, 180, and 270 degrees using the existing FOV and output dimensions.

### FR6: Split assignment

- Assign 10 approved panoramas per country to development and 5 to evaluation.
- Make split assignment deterministic from a recorded seed and the frozen eligible pool.
- Prevent a provider sequence from appearing in both splits.
- Perform distance and sequence checks before downloading whenever possible.
- Freeze the evaluation split before prompt tuning or reference-data changes based on expanded
  development results.

### FR7: Dataset manifests

- Export new versioned manifests rather than overwriting `dev_v1.csv` or `eval_c1.csv`.
- Use provider-neutral columns: `provider`, `provider_image_id`, and `provider_sequence_id` where
  the latter is needed for audit-only exports.
- Include country label, local panorama path, four local view paths, dimensions, checksums, and
  quality-policy version in the curator manifest.
- The runtime model-payload builder must continue to omit all labels and source metadata.
- Export must fail unless every selected country has the exact required split counts and all four
  view files pass integrity validation.

### FR8: Licensing and attribution

- Record the applicable imagery license and attribution source for every downloaded panorama.
- Generate a dataset-level attribution report grouped by provider and contributor when required.
- Do not admit a panorama whose reuse terms are absent, incompatible, or unresolved.
- Treat licensing checks as release blockers rather than warnings.

### FR9: Operational commands

The implementation should provide commands equivalent to:

```text
scan-coverage --candidates <path> --providers mapillary,kartaview --target 15
ingest-pictures --dataset worldwide_v2 --country <ISO2> --split <split> --limit <n>
collection-status --dataset worldwide_v2
export-manifests --dataset worldwide_v2 --output-dir data/datasets
export-attribution --dataset worldwide_v2 --output <path>
```

Country choices must come from the selected dataset definition rather than hard-coded CLI choices.

## Data and privacy boundaries

The following data may exist only in coverage reports, MongoDB, ingestion logs, or curator-facing
exports:

- latitude and longitude;
- expected and validated country;
- provider and provider identifiers;
- sequence identifiers;
- capture timestamps;
- source URLs and attribution;
- local filenames and checksums; and
- split membership.

Production MAS inputs remain limited to the four cardinal images and the validated structured
visual extraction. The existing recursive payload safety audit must reject provider-neutral fields
as well as legacy Mapillary-specific field names.

## Failure behavior

- Provider authentication failure stops that provider scan with a clear diagnostic and does not
  silently mark countries as lacking coverage.
- Rate limits and retryable server failures use bounded exponential backoff and remain visible in
  the report.
- Exhausting one provider permits the explicitly configured fallback; it does not weaken quality or
  distance requirements.
- A country that cannot produce 15 accepted panoramas remains unsupported in the frozen dataset.
- Manifest export is atomic and must not leave a partially updated dataset version.

## Rollout plan

### Phase 1: Deep Mapillary qualification

- Expand the country candidate catalog to at least 45 countries.
- Rescan using adaptive tiling and offline boundary validation.
- Produce a reviewed report with at least 30 qualified countries if coverage permits.

### Phase 2: Provider abstraction

- Normalize the current Mapillary implementation behind the provider contract.
- Migrate storage identity and indexes to provider-scoped IDs.
- Preserve the three-country pilot and its manifests unchanged.

### Phase 3: Targeted fallback

- Implement the KartaView adapter only if the deep Mapillary report yields fewer than 30 suitable
  countries or later quality replacement exhausts a selected country.
- Re-run qualification only for deficient countries.

### Phase 4: Collection and review

- Collect development panoramas first.
- Review automatic failures and manual rejection rates before collecting the evaluation split.
- Replace rejected panoramas until exact country counts are reached.

### Phase 5: Freeze and validate

- Freeze country taxonomy, provider configuration, split seed, quality policy, and manifests.
- Generate attribution and coverage reports.
- Run model-payload audits and structural dataset validation before evaluation.

## Acceptance criteria

The feature is complete when all of the following are true:

- At least 30 countries qualify across at least five continents.
- Each selected country has exactly 10 approved development and 5 approved evaluation panoramas.
- All 450 or more retained panoramas pass offline country-boundary validation.
- Every retained pair within the same country is at least 10 km apart.
- No provider sequence crosses development and evaluation splits.
- Every retained panorama produces exactly four valid cardinal views.
- Every retained panorama has recorded provider, license, attribution, checksum, dimensions, and
  manual-review status.
- Existing three-country pilot manifests remain byte-for-byte unchanged.
- Manifest export rejects missing countries, incorrect counts, incomplete views, and duplicate
  provider identities.
- Payload-audit tests prove that coordinates, labels, providers, provider IDs, sequences, paths,
  checksums, and split metadata cannot reach the supervisor, extraction provider payload beyond
  the allowed images, or specialists.
- Focused provider, coverage, storage, ingestion, manifest, and payload-audit tests pass.
- `git diff --check` passes.

## Success metrics

- Qualified countries: at least 30.
- Accepted panoramas: at least 450.
- Continents represented: at least five.
- Split leakage incidents: zero.
- Boundary-label mismatches in retained data: zero.
- Model-payload metadata leaks: zero.
- Missing or unresolved image licenses: zero.
- Corrupt or incomplete rendered view sets: zero.

## Risks and mitigations

| Risk | Mitigation |
| --- | --- |
| Mapillary coverage is geographically uneven | Broaden candidates, deepen adaptive scans, then use targeted fallback |
| Manual review scales from 45 to at least 450 images | Review development first, report rejection reasons, and batch contact sheets without weakening approval |
| Provider camera artifacts become shortcuts | Keep provider identity hidden and monitor accuracy by provider and country |
| Mixed licenses complicate release | Persist per-image provenance and block unresolved imagery at freeze time |
| Schema migration breaks the pilot | Add provider-neutral fields additively and keep v1 exports unchanged |
| Fallback API behavior changes | Isolate provider-specific logic and retain normalized fixtures and contract tests |

## Constitutional preflight

This specification conforms to `CONSTITUTION.md` and does not require an amendment.

- Supervisor modality is unchanged: production runs still receive exactly four cardinal images and
  the structured extraction.
- Hidden evaluation metadata remains excluded from all model inputs.
- Specialist selection, reference tools, execution order, re-examination, budgets, termination,
  and tracing are unchanged.
- No live provider browsing is introduced during inference; provider calls occur only during
  offline dataset construction.
- Implementation must add focused validation for the expanded metadata-isolation invariant and
  finish with a clean `git diff --check`.
