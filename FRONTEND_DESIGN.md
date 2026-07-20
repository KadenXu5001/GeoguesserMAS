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
- The current training set contains 45 locally stored Mapillary panoramas. All 45 are valid
  equirectangular images, and the current source dimensions satisfy the 2:1 panorama format.
- New Mapillary content may be acquired using `MAPILLARY_ACCESS_TOKEN`, but playing existing rounds
  must use local panorama files and must not require a live Mapillary request.
- The frozen pilot CSVs remain the authoritative round/label manifests, but media resolution may
  use a validated local storage-migration overlay keyed by source identity. When that overlay is
  marked complete, the server loads panorama and cardinal-view bytes from country-scoped,
  content-addressed object-store paths instead of the legacy manifest paths. The overlay and
  resolved filesystem paths remain server-only and must never appear in pre-guess responses.
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
- The informed overlay has stronger visual emphasis than the complete extraction overlay. It is
  enabled by default; the complete extraction overlay is disabled by default. If no final evidence
  can be associated with a bounded extracted object, the guide explains that no highlightable
  informed evidence is available instead of inventing a location.
- The browser receives the final prediction evidence needed by the guide, but the prediction's
  country, alternatives, and other answer-like output remain server-side.
- Vision analysis normally runs once per panorama and is persisted in a server-controlled website
  cache for later visits, including visits after the website server restarts. If that initial MAS
  run fails with a transient transport or Gemini capacity error, the website may start exactly one
  fresh production MAS run with the same server-side image references. The failed run is never
  resumed or cached, and validation, policy, and other deterministic failures are not retried.
- The first guide visit may show a loading state while the analysis runs.
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
13. Pre-guess Vision Guide payloads expose evidence text but not the predicted country,
    alternatives, or hidden answer metadata.
14. Desktop and mobile visual checks conform to the approved references.
15. The production frontend build and `git diff --check` pass.

## Implementation status

The `/world` implementation now conforms to this specification: it uses protected opaque rounds,
a draggable and zoomable 360-degree panorama, an interactive Leaflet country map, single-use
server-authoritative country guessing, state-preserving Vision Guide navigation, and cached
four-view analysis. Focused server tests and desktop/mobile browser checks cover these invariants.

## Decision record

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

- Allowed the website analysis boundary to start one fresh MAS run after a transient timeout or
  Gemini capacity failure from the initial run.
- Kept retries outside the failed MAS graph so extraction remains single-use within every run.
- Continued to cache only successful browser-safe analysis and prohibited retries for deterministic
  validation or policy failures.
