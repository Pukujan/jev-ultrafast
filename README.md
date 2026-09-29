# Jev Ultrafast

> **One natural-language goal. Indexed page controls. One Decisions request picks the next move.**

A browser agent with a **dynamic, indexed action space** — built for real sites, not invented selectors.

<img src="docs/demo.gif" alt="Google Flights search at 1x speed with generated city names and dynamic operation/target decisions" width="100%" />

[Watch the MP4](docs/demo.mp4) · [Measurements](docs/performance.md) · [Read the loop](jev_ultrafast/agent.py)

## Why this exists

You want an agent to finish a real page task — search flights, open a Wikipedia article, explore a lesson as a guest — without hand-written site scripts. Prompting a model to invent Playwright or CSS selectors looks easy until the DOM shifts, a control is covered, or the model emits something the browser should never run.

**Selectors from the model are out of bounds.** Ultrafast observes the page, numbers the controls you can actually use, and asks [OpenRouter Decisions](https://openrouter.ai/docs/guides/community/jev) (`typesafe/jev-1.13`) for an operation and a target in **one request**. A small text model runs only when the operation is `TYPE_TEXT`.

## What this project is

Ultrafast is a small Python agent and local inspector for engineers and adopters who need **validated click / type / select / scroll / wait** cycles on Chrome via [Browser Harness](https://github.com/browser-use/browser-harness).

It is **not** a booking bot, not a Study-os product fork, and **not** a TypeSafe-account requirement. Auth for decisions is `OPENROUTER_API_KEY` only ([policy](https://github.com/Pukujan/jev-ultrafast/blob/041d5242bb9159a588b09d303a19a0208cf9a95c/docs/POLICY.md#openrouter-decisions-only)).

Fork lineage: this repository is [Pukujan/jev-ultrafast](https://github.com/Pukujan/jev-ultrafast), based on upstream [browser-use/jev-ultrafast](https://github.com/browser-use/jev-ultrafast).

## What you can make or use

- **Library agent** — `Agent(url, goal)` iterates until DONE / BLOCKED / budget.
- **Local inspector** — `uv run jev` at http://127.0.0.1:8766 with numbered elements and probabilities.
- **Study-os guest crawls** — explore https://study.design-bakery.com and log artifacts aligned to the Study-os UX defect contract by reference (see [docs/POLICY.md](docs/POLICY.md)).
- **Committed demos** — Flights and Wikipedia examples under `examples/`, plus measurement docs.
- **Frontend QA from one terminal** — `uv run jev-qa --url https://…` runs a
  guided Laya exploration (default, local, no keys), optional Playwright
  evidence and opt-in vision stages, and opens an offline `report.html` with
  defects.csv, workflow.mmd, and run.json in the run folder.
  [Operator flows](docs/qa/user-flow.md) · [adapter contract](docs/qa/adapter-spec.md)

## How it works

1. **Observe** — Chrome CDP snapshot via Browser Harness yields visible controls and page text.
2. **Index** — Build an element table (`CLICK`, `TYPE_TEXT`, `SELECT`, …) from what is actually on the page.
3. **Decide** — One `POST https://openrouter.ai/api/alpha/decisions` returns operation + speculative target heads ([details](https://github.com/Pukujan/jev-ultrafast/blob/041d5242bb9159a588b09d303a19a0208cf9a95c/docs/OPENROUTER-DECISIONS.md)).
4. **Act** — Execute only the selected observed target. `TYPE_TEXT` may call `TEXT_MODEL_*` (OpenRouter chat) to fill a field.
5. **Verify** — Log execution before re-observing; check final outcomes independently. `DONE` is not proof.

```text
[1] button    Change ticket type · Round trip
[2] combobox  Where from?        · San Francisco
[3] combobox  Where to?          · empty
...
```

Operations: `CLICK`, `TYPE_TEXT`, `SELECT`, `SCROLL_UP`, `SCROLL_DOWN`, `WAIT`, `DONE`, `BLOCKED`. Target heads stay speculative until the chosen operation selects one.

## Evidence and boundaries

| Claim | What the evidence supports | What it does not establish | Source |
| --- | --- | --- | --- |
| Flights demo ~7.1 s at 1× with independent verification | Timed run (7.073 s) after first observation, including model + browser work; matched-run medians in the performance doc | Broad agent benchmark; strong statistics (three pairs) | [https://github.com/Pukujan/jev-ultrafast/blob/041d5242bb9159a588b09d303a19a0208cf9a95c/docs/performance.md#faster-on-the-real-web](https://github.com/Pukujan/jev-ultrafast/blob/041d5242bb9159a588b09d303a19a0208cf9a95c/docs/performance.md#faster-on-the-real-web) |
| OpenRouter Decisions only; no TypeSafe key | POLICY names endpoint, model `typesafe/jev-1.13`, and OpenRouter auth | Every historical upstream README sentence — prefer POLICY on this fork | [https://github.com/Pukujan/jev-ultrafast/blob/041d5242bb9159a588b09d303a19a0208cf9a95c/docs/POLICY.md#openrouter-decisions-only](https://github.com/Pukujan/jev-ultrafast/blob/041d5242bb9159a588b09d303a19a0208cf9a95c/docs/POLICY.md#openrouter-decisions-only) |
| Study-os guest crawl artifacts exist | 2026-09-27 summary: pages visited, `openrouter_decisions_ok`, defect_count 11 | Full PDD coverage or schema byte-identity with Study-os | [https://github.com/Pukujan/jev-ultrafast/blob/041d5242bb9159a588b09d303a19a0208cf9a95c/docs/benchmarks/study-os-2026-09-27/summary.json#L1](https://github.com/Pukujan/jev-ultrafast/blob/041d5242bb9159a588b09d303a19a0208cf9a95c/docs/benchmarks/study-os-2026-09-27/summary.json#L1) |

**Boundaries:** demos do not book or purchase; Ultrafast does not own Study-os code or private study logs; the model must never emit selectors, coordinates, shell, or executable JavaScript.

## Try it

```bash
git clone https://github.com/Pukujan/jev-ultrafast.git
cd jev-ultrafast
uv sync
cp .env.example .env
# Set OPENROUTER_API_KEY (Decisions). For TYPE_TEXT, set TEXT_MODEL_API_KEY (often the same OpenRouter key).
uv run jev
```

Open **http://127.0.0.1:8766** → **Start demo → Run automatically**. Allow remote debugging in Chrome when prompted. Run `uv run browser-harness --doctor` if the connection needs help.

### Library

```python
from jev_ultrafast import Agent

with Agent(
    "https://www.google.com/travel/flights?hl=en",
    "Find one-way flights from Zurich to London on September 20, 2026, "
    "for one adult in economy. Stop when matching flight options are visible.",
) as agent:
    for state in agent.run():
        print(state["elapsed_ms"], state["status"])
```

```bash
uv run --env-file .env python examples/run.py \
  --url https://study.design-bakery.com \
  --goal 'Continue as guest if offered. Explore a DSA or Big-O lesson. Stop when a worked example is visible.'
```

### Environment

| Variable | Role |
| --- | --- |
| `OPENROUTER_API_KEY` | Required for Decisions |
| `OPENROUTER_DECISIONS_URL` | Default `https://openrouter.ai/api/alpha/decisions` |
| `OPENROUTER_MODEL` | OpenRouter Decisions model **slug** (default `typesafe/jev-1.13`). Not a separate provider; does not bypass OpenRouter Decisions. |
| `TEXT_MODEL_API_KEY` / `TEXT_MODEL_BASE_URL` / `TEXT_MODEL` | Required only for `TYPE_TEXT` (example uses OpenRouter chat + `inception/mercury-2.5`) |

### Small enough to read

| File | Job |
| --- | --- |
| [agent.py](jev_ultrafast/agent.py) | Loop and text-helper handoff |
| [snapshot.js](jev_ultrafast/snapshot.js) | Atomic DOM snapshot and freshness guards |
| [browser.py](jev_ultrafast/browser.py) | Connection, geometry, execution |
| [model.py](jev_ultrafast/model.py) | Decisions heads and text generation |
| [demo.py](jev_ultrafast/demo.py) | Local inspector |

### Adopter policy

See [docs/POLICY.md](docs/POLICY.md): adopters consume crawls/reports; this fork owns Decisions wiring, harness/CDP, and Ultrafast code. Defect contract for Study-os lives in Study-os docs (PDD + `ux-defect-report.v1.json`).

### Scan test

Headings, bold phrases, and links should recover: problem (no invented selectors), promise (indexed controls + one Decisions request), mechanism (observe → decide → act), boundaries (no TypeSafe key / no booking), next action (`uv run jev`).
