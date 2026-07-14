# GeoGuessr MAS Constitution

This constitution is the governing contract for all future code and prompt changes in the
GeoGuessr multi-agent system. A change is incomplete if it violates these rules.

## Supervisor modality and evidence

- The Deep Agents supervisor is multimodal. Every production MAS run gives it all four cardinal
  images and the structured visual description produced by the extraction preprocessor.
- The supervisor must scan the images itself. The description is a first-pass aid, not a substitute
  for visual inspection; the supervisor may correct or supplement it using visible evidence.
- The supervisor and specialists must never receive hidden evaluation metadata such as coordinates,
  country labels, image IDs, filenames, or sequence information.

## Specialist policy

- Every production MAS run must invoke at least one specialist.
- The production choices are `urban-specialist` and `rural-specialist`. The urban specialist owns
  built-environment clues; the rural specialist owns natural and low-density-settlement clues.
- Both specialists have access to universal lookup tools. Urban and rural lookup tools remain
  private to their corresponding specialist.
- The supervisor may invoke both configured specialists for a genuinely mixed scene, but each
  configured specialist may be invoked at most once per run.
- All reference knowledge is accessed through ordinary lookup tools backed by versioned local rows;
  lookup calls never spawn another subagent or perform live web browsing during inference.
- The supervisor may not repeat a specialist task or invoke any specialist that has already
  completed its task.
- Specialists are never replaced by cached responses. Every delegated specialist runs and can
  inspect its task, choose its permitted tools, and return a result to the supervisor.
- Only deterministic reference-tool responses may be persisted in the local Deep Agents cache.
  A cached tool response may be read at most three times in total; after that, the tool must
  return a capacity warning and the MAS must not make another lookup API call.

## Re-examination policy

- `reexamine_region` is optional and may be called at most once per panorama.
- It is allowed only when two distinct country signals remain genuinely competitive and their
  confidence scores differ by no more than 10 points.
- It must not be used merely because a clue is illegible, out of curiosity, or to retry a prior
  question. The competing signals and scores must be supplied to the tool and validated in code.

## Termination and bounded execution

- The supervisor makes one finite todo plan, progresses forward, and calls `emit_prediction` exactly
  once. `emit_prediction` terminates the run.
- No tool may be repeated, retried, or called merely to verify a previous result.
- Runtime middleware remains the source of hard enforcement for specialist, re-examination,
  orchestrator-turn, token, and cost limits. Prompts may explain these limits but cannot replace
  code enforcement.
- A run has a hard capacity ceiling of three minutes or $0.50, whichever is reached first. It
  must return an immediate warning and suggestion and make no further API calls.

## Observability

- LangSmith tracing and upload are mandatory for production MAS runs. LangSmith receives the
  run structure, tool calls, tool results, model outputs, timing, and usage; raw base64 image
  inputs must be hidden from the trace to keep uploads bounded. The local MAS still receives and
  processes the full images.
- Trace delivery is synchronous and must be flushed before the process exits. A trace-upload
  failure is an observability failure and must be printed clearly in the terminal; it must not be
  confused with a model or MAS prediction failure.

## Change discipline

Before changing MAS code, prompts, tools, state, or budgets, compare the proposed change against
this constitution. Update the constitution first when a deliberate architectural decision changes
the contract, then update code and tests to match. Do not introduce behavior outside this
constitution without recording and approving the corresponding constitutional change.
