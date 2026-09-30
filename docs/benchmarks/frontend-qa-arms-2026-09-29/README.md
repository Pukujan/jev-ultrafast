# Frontend QA arms — 2026-09-29

Two decision arms drove the same packaged `jev-qa` run against the same two
live sites, after fixes that made the comparison mean something. Read
[the report](./report.md) for what each arm found; this folder holds the raw
machine records next to the prose.

| Field | Value |
| --- | --- |
| Date (ET) | 2026-09-29 ~20:00–23:10 ET |
| Runner | `jev-qa` from this repository, `main` at `adca368` |
| Targets | https://www.design-bakery.com and https://study.design-bakery.com (both hosted, operator-provided) |
| Decision arms | OpenRouter Decisions (`typesafe/jev-1.13`) and local OpenJev (APUS-OpenJev-v1-4B Q4_K_M on Ollama 0.34.4) |
| Evidence stage | Playwright, viewport 1280×720, on for every run |
| Vision | off for every run |
| Step budget | 25 executed steps per run |
| Owner scope | the Laya arm is excluded from this comparison by owner direction the same evening; its passes are recorded on issue #9 and are not counted here |

## What lives here

- `report.md` — the readable version: what each arm did, what it found, what
  stayed unproven.
- `summary.json` — the same numbers in machine form, one object per run.
- `workflows/` — the Mermaid sources the harness itself wrote, one per run.
  GitHub renders these; each names the failing step in red.
- `defects/` — the full `defects.csv` from each run: every recorded row with
  its reproducible action, timestamp, and evidence reference.

The run folders themselves stay on the machine that ran them. `qa-runs*/` is
git-ignored because each holds a 3.5 MB copy of the bundled chart renderer,
screenshots of a live site, and browser probes that carried cookies. Nothing
here repeats a private learner record, a credential, or a raw page transcript:
labels, measurements, and HTTP statuses only.

## Why the earliest passes today are excluded

The first runs, before the settle fix in `a8fd5e7`, recorded a finished
exploration at step zero. A page that has not mounted yet offers a decision
model nothing to click, and every model answered that honestly. Those passes
are superseded rather than wrong: the harness had been measuring its own race.
The receipts are on issue #9, keyed to commits `c95545f` and `a8fd5e7`.
