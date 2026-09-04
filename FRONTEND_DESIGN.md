# GeoGuessr MAS Frontend Design

This document is the governing specification for the GeoGuessr MAS frontend. It defines approved
layouts, interactions, routes, presentation state, and user-facing behavior. All frontend changes
must conform to both this document and `CONSTITUTION.md`.

## Frontend change protocol

Before changing frontend code, styles, routes, presentation state, frontend-facing APIs, tests, or
supporting documentation:

1. Read `CONSTITUTION.md` and this document completely.
2. Identify the affected requirements and confirm that the proposed change conforms.
3. If the proposed behavior is new or changes an approved decision, update this document first.
4. Implement only the behavior recorded here.
5. Validate the affected layout and interactions at desktop and mobile sizes.
6. Run the frontend production build and `git diff --check`.

User requests and screenshots are proposed frontend changes. When an approved request or screenshot
changes this specification, record it here before changing the implementation. The constitution is
the highest authority; this document is the frontend source of truth beneath it.

## Design-source hierarchy

When frontend sources disagree, use this order:

1. `CONSTITUTION.md`.
2. Approved behavior recorded in this document.
3. User-provided screenshot references named in this document.
4. The current implementation.

Screenshots govern visible structure, hierarchy, placement, grouping, and composition. Small changes
to dimensions, spacing, or colors are allowed when they improve visual quality, readability,
responsiveness, or consistency without substantially redesigning the approved structure.

## Product scope

The initial frontend contains three screens:

1. Home screen.
2. World training screen.
3. Vision MAS screen.

The product is a training experience, not a game. It must not introduce points, distance scoring,
timers, streaks, lives, competitive rankings, a fixed-length match, or a final game summary unless
this document is amended first.

## Shared experience

- The user-facing product name is `GeoTrainer`. The former `AtlasLens` name must not appear in
  visible interface copy, labels, or branding.
- The interface must be responsive and usable with mouse, touch, and keyboard input.
- Desktop and mobile layouts must preserve the same content hierarchy and available actions.
- Loading, empty, error, and disabled states must be visible and understandable.
- Interactive elements must have accessible names and visible keyboard focus.
- Country answers and hidden round metadata must never be exposed to the browser before a guess is
  submitted.
- Navigation to the Vision MAS screen and back must preserve the active training round, panorama
  orientation, selected country, and submitted result.

## Home screen

### Purpose

Introduce the training experience and let the user enter a training mode.

### Approved layout

The home screenshot is the structural reference. The screen contains:

- A prominent global map in the upper content area.
- A short training-mode introduction below the map.
- Three training-mode cards arranged together:
  - `World`, enabled.
  - `USA`, unavailable and marked as coming soon.
  - A third future mode, unavailable and marked as coming soon.

### Behavior

- The global map may expose clickable regions as a visual entry point.
- Selecting the map or the enabled `World` card starts a random unseen world-training round.
- Unavailable modes must remain visibly disabled.

## World training screen

### Purpose

Emulate the core observational and country-guessing workflow of GeoGuessr while remaining an
unscored training tool. The user observes an unknown place, explores a real world map, selects a
country, submits a guess, and learns whether the country was correct.

### Round identity and answer privacy

- A training route must use an opaque round identifier, not a country name or other answer-bearing
  value.
- Pre-guess API responses must not include the correct country, country code, coordinates,
  filenames, or other metadata that reveals the answer.
- The server is authoritative for the correct country and guess evaluation.
- The training set combines the 45 frozen pilot panoramas with eligible `worldwide_v2` panoramas
  registered in MongoDB. The two sources are additive and are deduplicated by Mapillary source
  identity, with the frozen pilot manifest winning any collision.
- A production deployment may omit pilot media when the deployment independently verifies that
  eligible `worldwide_v2` rounds still serve France, Brazil, and Thailand. Omitting pilot media must
  not remove any of those three countries from the playable country pool. Objects referenced by a
  restored `worldwide_v2` record must be uploaded even when their original provenance was the pilot
  collection; only pilot-only, unreferenced media may be omitted.
- A `worldwide_v2` MongoDB record is playable only when it is explicitly tagged with that dataset
  version, belongs to one of the versioned dataset's countries, has `quality.automatic_pass` set,
  is in `quality_review` or `rendered` state, has an exact 2:1 original panorama, has exactly one
  local cardinal view for each required heading, and every referenced local media object exists.
  Records that fail any eligibility check are excluded rather than repaired or approximated.
- New Mapillary content may be acquired using `MAPILLARY_ACCESS_TOKEN`, but playing existing rounds
  must use local panorama files and must not require a live Mapillary request.
- The frozen pilot CSVs remain authoritative for pilot round labels and split membership. MongoDB
  is authoritative for `worldwide_v2` round labels, quality state, split membership, and portable
  object-store references. Pilot media resolution may use a validated local storage-migration
  overlay keyed by source identity. The overlay, MongoDB records, object keys, and resolved
  filesystem paths remain server-only and must never appear in pre-guess responses.
- A completed storage migration may remove the legacy media files only after every replacement
  object passes its frozen-manifest checksum and the frontend can load all 45 rounds through the
  overlay. The frozen CSV bytes, labels, split membership, and review decisions remain unchanged.
- Only records verified as true panoramas may be admitted to the playable set. A record without a
  valid original 360-degree panorama is excluded; it must not fall back to cardinal-view snapping
  or synthetic stitching.

### Round selection

- Entering World training selects a random unseen panorama.
- A panorama should not repeat until the available set has been exhausted in the current browser
  training session.
- After a submitted result, the user can request another random training example.
- This non-repetition state is a convenience, not a score or game session.

### Panorama viewer

- The locally stored Mapillary equirectangular image must be rendered as a true 360-degree
  panorama.
- The viewer must support smooth horizontal and vertical dragging with mouse and touch.
- The viewer must support zooming.
- Each round begins facing North.
- Training is stationary: the user rotates and zooms at one capture location but cannot move to
  neighboring panorama locations or along a Mapillary sequence.
- The panorama is the dominant visual surface and should occupy most of the viewport, matching the
  supplied GeoGuessr reference.
- The correct country must not appear in the page heading, capture label, alt text, media URL, or
  any other visible or inspectable frontend value before submission.

### Interactive world map

- Use Leaflet with OpenStreetMap tiles.
- The map must provide real panning and zooming behavior.
- The map begins at a world view and must not center on, mark, or otherwise hint at the correct
  location.
- The map floats over the panorama in the lower-right area, following the GeoGuessr reference.
- On desktop, the compact map expands on hover or direct interaction.
- On touch devices, tapping toggles the expanded state.
- The user selects a guess by clicking a country boundary. The selected country is highlighted as
  a whole shape; no coordinate pin is required. Selection uses fill highlighting only and must not
  draw a dark country outline or pointer-focus bounding box.
- Selecting a different country replaces the previous selection.
- Ocean or non-country clicks do not produce a valid selection.
- The Guess action remains disabled until a country has been selected.

### Guess submission and result

- A guess consists of the selected country's stable country code.
- The server compares the selected country with the hidden correct country.
- Submission is single-use for that round.
- The result shows:
  - Correct or incorrect status.
  - The selected country.
  - The correct country.
  - An action to start another training example.
- The result does not show distance, coordinates, an actual-location pin, points, or a game score.
- After submission, the revealed answer may be retained while the user opens the Vision MAS guide
  or returns from it.

### Vision Agent Guide entry

- The Vision Agent Guide action is visible before and after guessing.
- Before a guess it is clearly labeled as a hint because it may reveal identifying evidence.
- Selecting it opens immediately; no spoiler-confirmation dialog is required.
- Opening the guide must preserve the current training state.

## Vision MAS screen

### Purpose

Teach the user what visual evidence the multi-agent system notices for the active panorama.

### Approved layout

The Vision MAS screenshot is the structural reference. The screen contains:

- Four separate cardinal views arranged as a coherent group.
- Colored bounding boxes over the views.
- A guide explaining what each bounding-box color represents.
- A compact overlay-controls box with independent switch controls labeled `What the agent sees`
  and `What the agent informs`.
- When informed evidence exists, a one-at-a-time evidence selector beneath the controls.
- A clearly labeled agent-prediction card that shows the country selected by the MAS, up to three
  other candidates considered by the MAS, and an explicit explanation that the agent is not shown
  the answer beforehand and may be wrong.
- An action to return to the active world-training round.
- Clear indication that this screen is an optional Vision Agent Guide.

### Behavior

- The four views correspond to North/0 degrees, East/90 degrees, South/180 degrees, and West/270
  degrees.
- Bounding boxes must align to the image dimensions and identify the extraction category and
  confidence where available.
- `What the agent sees` controls the complete extraction overlay that was previously always
  visible: all detected-object bounding boxes, category labels, and confidence values.
- `What the agent informs` controls the smaller, higher-priority set of observations that informed
  the final country prediction. The two controls are independent and may be enabled together.
- Informed evidence is derived from the final prediction's `evidence` subfield and successful
  specialist reference lookups. Each item uses the final prediction evidence text as its short
  description and highlights the exact extracted object cited by the corresponding lookup.
- Informed evidence is selected one item at a time. The selected item is highlighted in its
  cardinal view, and placing a pointer over the highlight reveals its short description. Keyboard
  focus reveals the same description, and touch users can read it in the persistent selected-item
  control.
- Object observations and descriptions displayed as informed-evidence hints use sentence
  capitalization in selector cards, image tooltips, and accessible labels. This is a presentation
  transformation only; the underlying MAS evidence text remains unchanged.
- Evidence-selector cards must never permanently truncate their clue text. On pointer hover or
  keyboard focus, a card expands smoothly within the selector while its siblings contract slightly
  so the full observation and description can be read. On touch-sized layouts, the selected card
  displays its full text without relying on hover.
- The informed overlay has stronger visual emphasis than the complete extraction overlay. It is
  enabled by default; the complete extraction overlay is disabled by default. If no final evidence
  can be associated with a bounded extracted object, the guide explains that no highlightable
  informed evidence is available instead of inventing a location.
- The browser receives the final prediction evidence, the MAS's chosen country, and up to three
  alternative candidates needed by the guide. These countries are presented only as agent
  predictions: the guide explicitly states that the agent is not shown the answer beforehand and
  that its prediction may be wrong. Ground truth, confidence details, and evaluation output remain
  server-side.
- Vision analysis normally runs once per panorama and is persisted in a server-controlled website
  cache for later visits, including visits after the website server restarts. If that initial MAS
  run times out before returning a prediction, capacity warning, or other structured result, the
  website may start exactly one fresh, isolated production MAS run with the same server-side image
  references after the timed-out run terminates. The failed run is never resumed or cached. Generic
  provider, validation, policy, capacity, observability, and all other non-timeout failures do not
  start another run.
- The first guide visit may show a loading state while the analysis runs.
- The website supervises every MAS child process with a 215-second outer deadline, including after
  an early browser-safe prediction has been returned. At that deadline it requests termination,
  allows at most 15 seconds for trace cleanup and process exit, and then forcibly terminates a child
  that remains alive. This outer safety deadline never starts a replacement run; only an earlier
  timeout that leaves sufficient enclosing-request budget may use the single fresh-run allowance.
- The loading state ends as soon as the MAS emits its complete browser-safe prediction JSON. The
  website must not wait for the subsequent mandatory LangSmith trace flush or Python process exit
  before presenting and caching that completed result. Trace delivery continues server-side; a
  later observability failure is logged clearly and does not rerun or retract the MAS prediction.
- Later visits reuse the cached website payload rather than starting the MAS process again. Cache
  lookup happens entirely in the website layer: cached data is never supplied to MAS state,
  prompts, tools, specialists, or runtime context.
- Cache identity includes the panorama source, all four rendered-view hashes, and a website
  analysis schema/version. A changed image or analysis version is a cache miss and runs the full
  production MAS.
- Only a successful, browser-safe payload containing extraction analysis and informed evidence is
  persisted. Failed, partial, capacity-limited, or answer-bearing payloads are never cached.
- A failed analysis shows a recoverable error without losing the active training round.
- Returning to the world screen restores the exact panorama orientation, selected country, and
  result state from before navigation.

## Frontend-facing service contract

The implementation may refine endpoint names, but it must preserve these trust boundaries:

- A round-start response supplies an opaque round ID and a protected panorama media reference. It
  does not supply answer metadata.
- A guess request supplies the opaque round ID and selected country code. The response supplies
  correctness, selected-country presentation data, and the correct-country presentation data.
- Panorama delivery must not encode the answer in a browser-visible path or filename.
- Vision-analysis requests use the opaque round ID. Successful browser-safe results are stored in
  a server-controlled persistent cache. The persistent cache is consulted before starting the MAS
  and is not accessible from within the MAS execution path.
- Frontend source code, browser state, network payloads, and pre-guess accessibility text must not
  contain the hidden answer.

## Responsive requirements

- The panorama remains the primary surface on every viewport.
- The floating map must remain reachable and must not cover essential panorama controls.
- Country selection and Guess must be operable on touch screens without relying solely on hover.
- Four Vision MAS views may collapse from a two-column desktop grid to a single mobile column.
- Training-mode cards may collapse from a row to a vertical list.
- Text must not clip, overlap, or require horizontal page scrolling at supported viewport sizes.

## Acceptance criteria for the World training flow

Before the World training redesign is complete, focused validation must demonstrate that:

1. A round loads without exposing the country before submission.
2. The panorama starts North and supports smooth drag and zoom.
3. The Leaflet map pans and zooms independently of the panorama.
4. The map expands appropriately on desktop and touch layouts.
5. Clicking a country highlights it and enables Guess.
6. Changing the selected country moves the highlight.
7. Guess submission is evaluated on the server and can be submitted only once.
8. The result reveals correct/incorrect and the correct country without points or coordinates.
9. Another training example loads without repeating an unseen round prematurely.
10. Vision Guide navigation preserves round state.
11. Vision analysis is reused after its first successful generation for a panorama.
12. The Vision Guide switches independently control complete extraction and informed overlays;
    informed items can be selected individually and expose their short descriptions by hover,
    keyboard focus, and touch-accessible persistent text.
13. Pre-guess Vision Guide payloads expose evidence text, the predicted country, and up to three
    alternative agent candidates, but not ground truth, confidence details, or other hidden answer
    metadata.
14. Desktop and mobile visual checks conform to the approved references.
15. The production frontend build and `git diff --check` pass.

## Implementation status

The `/world` implementation now conforms to this specification: it uses protected opaque rounds,
a draggable and zoomable 360-degree panorama, an interactive Leaflet country map, single-use
server-authoritative country guessing, state-preserving Vision Guide navigation, and cached
four-view analysis. Focused server tests and desktop/mobile browser checks cover these invariants.

## Decision record

### 2026-07-22: Public production access

- Removed the Caddy HTTP Basic Auth prompt so the home, training, media, guess, and Vision Guide
  routes are publicly accessible over HTTPS without an account or sign-in step.
- Kept opaque round IDs, server-authoritative answers, one-time guess submission, bounded MAS
  concurrency, per-IP request limits, and the persistent monthly MAS spend ceiling. Anonymous
  traffic does not use a shared per-user throttle because every visitor has the same anonymous
  identity; the client address is the public request-limit key.
- Continued to strip inbound authorization headers at Caddy and keep MongoDB, the application port,
  answer metadata, local media paths, and model credentials inaccessible from the public network.
- Retained all production security headers and left `/healthz` publicly available for infrastructure
  checks.

### 2026-07-21: VPS production access boundary

- Protected the production website and every application API route with Caddy-managed HTTP Basic
  authentication, while leaving only `/healthz` public for infrastructure health checks.
- Kept credentials out of the frontend bundle and browser storage. Caddy removes the inbound
  `Authorization` header and forwards only a validated username and client address to the app over
  the private Docker network.
- Required the backend to bind opaque rounds to the authenticated username and to enforce
  per-user, per-IP, concurrency, and monthly MAS spend limits server-side. Local development may
  explicitly disable the trusted-proxy authentication boundary.
- Required production HTTPS responses to include HSTS, CSP, `nosniff`, frame-denial, referrer, and
  permissions policies at the Caddy boundary without changing the approved visible interface.

### 2026-07-19: Initial frontend master specification

- Established the three-screen structure from the user-provided home, map, and Vision MAS
  screenshots.
- Defined the World page as an unscored country-identification training flow.
- Selected true locally stored Mapillary panoramas, stationary 360-degree rotation and zoom, North
  starting orientation, Leaflet with OpenStreetMap, whole-country highlighting, country-only
  evaluation, random unseen training examples, immediate optional Vision hints, and once-per-
  panorama cached Vision analysis.

### 2026-07-19: Vision evidence overlay controls

- Added independent `What the agent sees` and `What the agent informs` switches.
- Preserved the existing extraction boxes under the sees control and prioritized informed evidence
  by enabling it by default while leaving the complete extraction overlay off by default.
- Selected informed evidence one item at a time, with exact-object highlighting and a short final-
  prediction evidence description available on hover, keyboard focus, and touch.
- Kept prediction country and alternatives out of the browser-facing Vision Guide payload.

### 2026-07-19: Minimap selection highlight

- Removed the selected country's polygon stroke and pointer-focus rectangle so selection is shown
  only through the whole-country fill highlight.
- Preserved a visible focus indicator for keyboard navigation.

### 2026-07-19: Persistent website-only Vision analysis cache

- Moved reuse semantics from process-local memory to a persistent server-controlled cache so a
  successful analysis survives website restarts.
- Kept cached analysis outside the MAS boundary; a cache hit does not start a production MAS run,
  while every cache miss still executes the full required workflow.
- Versioned cache identity by panorama source, rendered-view hashes, and analysis schema, and
  prohibited caching failures or answer-bearing output.

### 2026-07-19: Country-scoped local media migration

- Kept the frozen pilot CSVs authoritative and byte-for-byte unchanged while allowing a validated
  server-only migration overlay to resolve their media into the country-scoped object store.
- Required checksum verification and complete 45-round frontend resolution before deleting legacy
  panorama or rendered-view files.
- Kept country folders, object keys, source identities, and resolved paths out of every pre-guess
  browser response.

### 2026-07-19: Bounded website MAS recovery

- Allowed the website analysis boundary to start one fresh MAS run only after a timeout from the
  initial run and only after that timed-out run terminates without a structured result.
- Kept retries outside the failed MAS graph so extraction remains single-use within every run.
- Continued to cache only successful browser-safe analysis and prohibited new runs for generic
  provider, validation, policy, capacity, and observability failures.

### 2026-07-21: Timeout-only whole-run retry amendment

- Defined each MAS invocation as an isolated run with fresh graph state, runtime counters, cost
  accounting, and trace identity.
- Prohibited every retry inside a run while permitting at most one replacement run when the first
  invocation times out before returning any structured result.
- Removed Gemini capacity and other non-timeout provider failures from website retry eligibility.

### 2026-07-21: Deployment media and MAS process deadline

- Allowed production to omit pilot media only while independently playable `worldwide_v2` rounds
  continue to cover France, Brazil, and Thailand.
- Added a 215-second outer MAS child-process deadline with a 15-second graceful termination window,
  keeping cleanup bounded below the planned 240-second Cloud Run timeout.
- Kept process supervision active after early prediction delivery and prohibited a fresh run after
  the outer safety deadline.

### 2026-07-21: Restore France and Thailand worldwide coverage

- Restored eight approved France development panoramas and four approved Thailand development
  panoramas from the frozen pilot collection into `worldwide_v2`, bringing each country to ten
  independently playable MongoDB records.
- Selected only automatic-quality passes with approved manual review, exact 2:1 originals, all four
  cardinal views, and verified content-addressed objects. Among eligible development records, the
  lowest horizontal seam-error scores were selected deterministically.
- Kept frozen evaluation records and rejected Thailand candidates out of the restoration. The pilot
  CSVs remain authoritative for their original split membership, and pilot identities continue to
  win frontend deduplication when local pilot media is present.

### 2026-07-20: Readable evidence cards and visible agent prediction

- Made evidence-selector cards expand smoothly on hover and keyboard focus while neighboring cards
  yield space; touch layouts show the selected clue without truncation.
- Added the MAS's single chosen country to the Vision Guide as a clearly labeled model prediction
  that may differ from the hidden answer.
- Continued to keep prediction alternatives, ground truth, confidence details, and evaluation
  metadata out of the browser payload.

### 2026-07-20: Additive worldwide MongoDB training pool

- Expanded World training additively from the 45 frozen pilot rounds to eligible panoramas tagged
  for `worldwide_v2` in MongoDB, while preserving pilot manifest authority and deduplicating source
  identities.
- Required automatic quality approval, exact equirectangular dimensions, all four local cardinal
  views, dataset-country membership, and existing country-scoped object-store files before a Mongo
  record can enter the playable pool.
- Kept dataset labels, source identities, object keys, and filesystem paths behind opaque server
  round IDs so the larger pool preserves the existing pre-guess answer boundary.

### 2026-07-20: Prediction alternatives and uncertainty disclosure

- Expanded the Vision Agent prediction card to show up to three alternative country candidates
  returned by the MAS.
- Added an explicit disclosure that the agent is not shown the answer beforehand and that its
  prediction may be wrong.
- Continued to keep ground truth, confidence details, and evaluation metadata out of the pre-guess
  browser payload.

### 2026-07-20: Prediction-first Vision Guide delivery

- Ended the Vision Guide loading state when the MAS emits its completed browser-safe JSON instead
  of waiting for the Python child process to exit.
- Kept the mandatory LangSmith flush running server-side after prediction delivery and required
  any later trace failure to remain a clearly logged observability failure.
- Prohibited a late trace failure from rerunning or retracting the already completed MAS result.

### 2026-07-20: GeoTrainer branding and capitalized informed hints

- Renamed the user-facing product from `AtlasLens` to `GeoTrainer` across the header and footer.
- Required informed object observations and descriptions to begin with a capital letter anywhere
  they are presented as selector hints, image tooltips, or accessible labels.
- Preserved the original evidence strings in the MAS and website payloads.
