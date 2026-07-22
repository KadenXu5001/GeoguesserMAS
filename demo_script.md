# GeoTrainer Demo Script (2:30–3:00 target)

Purpose: a portfolio demo for AI engineering roles. Show a real deployed product, then prove there's
a genuine multi-agent system with engineering discipline behind it (cost control, testing, CI/CD,
observability) — not just a prompt wrapper.

Read the narration at a natural pace (~150 wpm). Bracketed lines are on-screen actions, not spoken.

---

## Before you record — have these open in tabs/windows

1. `https://geo-trainer.com` (or your current domain) — logged out, home screen.
2. A terminal at the repo root, ready to run `python -m geoguesser.cost_model`.
3. A LangSmith trace for one recent production MAS run (pick a clean one in advance).
4. The GitHub Actions tab showing a green `deploy-production` run.
5. `CONSTITUTION.md` or `docs/cost_model.md` open in your editor, scrolled to a clean section.
6. Optional: a terminal with the test suite already run once so it's warm, e.g.
   `pytest -q` and `npm test --prefix web`.

---

## 0:00–0:15 — Hook

**[Screen: GeoTrainer home screen, world map visible]**

> "This is GeoTrainer — a live geography-training app where a multi-agent AI system looks at a
> street-level photo and figures out what country it's in, the same way a human GeoGuessr player
> would: by reading signs, architecture, plants, road markings. It's live in production right now,
> and I built the whole stack — product, agents, and infrastructure — myself."

---

## 0:15–0:55 — Product walkthrough

**[Click "World" mode. A 360° panorama loads.]**

> "The player drags around a real 360-degree panorama, pans the world map in the corner, and picks a
> country."

**[Drag the panorama, expand the map, click a country to highlight it, hit Guess.]**

> "The guess is single-use and evaluated server-side — the answer never touches the browser before
> submission, so there's no way to inspect it in dev tools and cheat."

**[Result reveals correct/incorrect + correct country.]**

> "Correct or not, you find out immediately — no scores, no timers, this is a training tool, not a
> game."

---

## 0:55–1:35 — Vision MAS guide (the AI-facing screen)

**[Click "Vision Agent Guide."]**

> "Here's the part built for this role: the same panorama, run through a multi-agent vision system,
> shown transparently."

**[Four cardinal views appear with bounding boxes.]**

> "Four directional views go through an extraction pass, and I can toggle between everything the
> model detected, and — more importantly — only the evidence that actually drove the final answer."

**[Toggle "What the agent informs," click one evidence card, hover to show its highlight + tooltip.]**

> "Each of these is traced back to a specific tool call a specialist agent made — not a hallucinated
> justification bolted on after the fact."

**[Scroll to the prediction card with alternatives.]**

> "And the agent shows its work: its top guess, up to three runner-ups, and an explicit disclaimer
> that it never saw the answer and can be wrong — same epistemic honesty I'd want from any agent in
> production."

---

## 1:35–2:15 — Under the hood: the multi-agent system

**[Cut to editor: `agent_factory.py` or `budget_middleware.py`.]**

> "Under the hood this is a LangChain Deep Agents orchestrator. A Gemini Flash pass extracts visual
> evidence from all four views first, then the orchestrator delegates to one or two narrow
> specialists — urban and rural — each scoped to its own private lookup tools."

**[Point at `wrap_model_call` / the `tool_choice` override in `budget_middleware.py`.]**

> "The important part is that this isn't just a prompt asking the model to behave — there's runtime
> middleware that tracks the current phase and sets `tool_choice` to the one legal next tool on every
> turn. If the model tries to finalize before a specialist has actually run, the tool call is
> rejected in code, not just discouraged in a system prompt."

**[Point at `_with_authorized_objects` or the specialist system prompt.]**

> "Delegation is capability-scoped too: each specialist only gets tools for its own clue domain, and
> it has to cite an exact object the extraction pass actually detected — so the evidence you saw
> highlighted on the panorama earlier is traceable back to a real tool call, not invented after the
> fact."

**[Show LangSmith trace.]**

> "Every run is traced end-to-end in LangSmith — I can see exactly which tools fired, in what order,
> and with what inputs, which is how I debug and tune this instead of guessing."

---

## 2:15–2:50 — Engineering rigor (the differentiator)

**[Run `python -m geoguesser.cost_model` live, or show its output.]**

> "Because multi-agent systems can get expensive fast, I built a real cost model comparing this
> pipeline against a single-call Opus baseline. The delegated path runs about 70% cheaper per
> panorama at comparable accuracy, and there's a hard runtime budget — capped tool calls, capped
> tokens, and an automatic cutoff that forces a final answer once spend hits 90% of the baseline."

**[Show green GitHub Actions run.]**

> "It's backed by 175-plus Python tests and 30-plus Node tests, and every push to main runs the full
> suite and auto-deploys through GitHub Actions to a Dockerized VPS — app, MongoDB, and Caddy —
> behind rate limiting and a hard monthly spend ceiling, so a bug can't turn into a runaway bill."

---

## 2:50–3:00 — Close

**[Back to the home screen or a GitHub repo page.]**

> "So — real product, real multi-agent orchestration, and the cost, testing, and deployment
> guardrails to run it safely in production. Code's linked below."

---

## Notes for delivery

- The two segments most worth over-rehearsing are the **evidence-toggle click** (1:00–1:20) and the
  **cost-model number** (2:20–2:35) — those are the two moments that separate "cool demo" from
  "this person can ship agents responsibly." Don't rush them.
- If time is tight, cut the CI/Actions clip first, then the DAG-enforcement line — the LangSmith
  trace and the cost number are the highest-signal seconds in the video.
- Say the savings number ("~70% cheaper than Opus") from `docs/cost_model.md`'s measured/estimated
  figures at recording time — re-check it against your latest `cost_model.py` output before
  recording, in case prices or measured usage changed.
