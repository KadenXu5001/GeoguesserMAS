# MAS decision log

Every production MAS invocation maintains an append-only `decision_log`. The log complements the
full LangSmith trace with a compact explanation of observable decisions and runtime enforcement.
It does not contain hidden model chain-of-thought.

The completed log is available in two places:

- `run_mas_row(...)["decision_log"]` for programmatic inspection; and
- the root LangSmith run output under `decision_log`, committed by `emit_prediction` or a terminal
  extraction failure.

Each event contains a sequence number, elapsed milliseconds, current phase, summary, budget
snapshot, machine-readable `reason_code`, and event-specific evidence. Typical events include:

- `runtime_route` and `model_tool_proposal`;
- `tool_requested` and `tool_rejected`;
- `todo_updated`;
- `extraction_started`, `extraction_completed`, or `extraction_failed`;
- `specialist_delegated` and `specialist_completed`;
- `reference_lookup_requested`, `reference_lookup_completed`, or
  `reference_lookup_rejected`;
- `reexamination_authorized` and `reexamination_completed`; and
- `prediction_finalized`.

The log records visible evidence, specialist candidates, contradictions, accepted/rejected tool
names, todo transitions, and final prediction evidence. Raw image data, local paths, filenames,
coordinates, image IDs, and ground-truth labels are redacted or omitted.

To diagnose a run, start with `prediction_finalized`, follow its evidence backward through
`specialist_completed` and `reference_lookup_completed`, then inspect `runtime_route` and
`tool_rejected` events for any enforcement that changed the model's proposed action.
