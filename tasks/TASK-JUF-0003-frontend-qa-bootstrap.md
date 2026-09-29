# TASK-JUF-0003 — Frontend QA harness for Laya

<!-- continuity:task {"acceptance":["jev-qa CLI takes URL-only targets and rejects paths with exit 2","blank or omitted runner selects laya; missing Laya runtime fails closed before any browser work; no Jev fallback","laya path reads no decision keys and sends no network decision; jev arm explicit with openrouter default provider","describe-v1 criteria flattening golden-tested; OpenRouter default path byte-identical (test_agent.py green)","key discovery names/prefixes only; watchdog deletes only the exact inserted line after 3h idle; fake-clock matrix passes","per run: defects.csv, workflow.mmd (deterministic, failing step marked), events.json, run.json with renderer sha256, offline report.html with mermaid 11.17.2","Playwright stage default-on skippable with lazy imports; vision default-off with separate VISION_* keys, never a pass; skipped/failed stages recorded honestly","PDD/SDD/TDD plus metamorphic, fuzz, hidden-holdout design committed; live AC6-AC9 runs remain open on issue #9","PR Refs #9, gates green, squash auto-merge armed"],"depends_on":[],"goal":"Ship the URL-only frontend QA harness: local Laya default runner (fail-closed), optional Jev comparison arm, skippable Playwright evidence and opt-in vision stages, offline per-run artifacts and report","id":"JUF-0003","issue_url":"https://github.com/Pukujan/jev-ultrafast/issues/9","next_action":"Integrate module implementations, run all gates, push branch, open PR Refs #9, arm squash auto-merge when gates green","owner":"Luna worker (delegated); Grok Bot review","priority":"high","protocol_version":"0.1.0-draft","schema":"project-continuity.task.v1","status":"active","why":"Operators need one terminal entry point for frontend QA against a reachable URL with provenance, without the tool owning target services or secrets"} -->

- Status: active
- Owner: Luna worker (delegated by repository owner); Grok Bot required reviewer
- Priority: high
- Depends on: none
- Issue: https://github.com/Pukujan/jev-ultrafast/issues/9
- Branch: `task/JUF-0003-frontend-qa-bootstrap`

## Goal

Let an operator run frontend QA from one terminal: give a reachable URL, get
defects.csv, workflow.mmd, run.json, and an offline report.html from a guided
Laya exploration plus optional Playwright and vision stages.

## Why

Study OS keeps separate Ultrafast, Playwright, and vision checks behind local
paths; a new operator has one reusable entry point to reach. Laya gives a
local decision runtime so the default path needs no keys and no hosted model.

## Allowed files

- `jev_ultrafast/qa/**` (new sub-package; `model.py` seam refactor by JUF-0003 owner)
- `jev_ultrafast/model.py` (transport seam; default behaviour byte-identical)
- `pyproject.toml`, `uv.lock`, `.gitignore` (playwright dep, `jev-qa` script, ignored run roots)
- `docs/qa/**`, `.content-system/filename-legends/frontend-qa.*`
- `tests/test_qa_*.py`
- `checkpoints/CURRENT.md`, `tasks/TASK-JUF-0003-*.md`, this task's projections

## Human outcome

A fresh terminal session runs `uv run jev-qa --url https://…`, accepts the
defaults, and finishes with a browsable offline report; when Laya is missing
the run stops before touching the browser and prints how to install it.

## Scope and boundaries

- In scope: URL-only CLI, laya/jev runners, provider discovery + idle key
  cleanup, Playwright evidence stage, optional vision stage, artifacts,
  offline report, PDD/SDD/TDD, unit/metamorphic/fuzz tests, holdout design
- Out of scope: target repository paths, starting or stopping target
  services, Study-os product code, live AC6–AC9 acceptance runs (runtimes
  pending on issue #9), committing any holdout contents or credentials
- Dependencies/uncertainty: live acceptance needs the localdecide runtime
  installed, Playwright browsers, and an operator-hosted Study OS URL; this
  branch claims implementation + offline tests only

## Acceptance criteria

- [ ] `jev-qa` takes URL-only targets; path/repo inputs rejected (exit 2)
- [ ] Blank/omitted runner selects laya; missing runtime fails closed; no Jev fallback
- [ ] Runner selection is provider selection; laya path uses no decision keys
- [ ] Jev arm explicit-only; openrouter default; typesafe/opencode behind env endpoints, fail closed when unconfigured
- [ ] describe-v1 flattening golden-tested; test_agent.py stays green untouched
- [ ] Key discovery is name/prefix-only; watchdog deletes only the exact inserted line after 3h idle; fake-clock matrix passes
- [ ] defects.csv/workflow.mmd/run.json/events.json byte-deterministic; report.html offline with mermaid 11.17.2 (sha256 pinned)
- [ ] Playwright stage default-on skippable, lazy import, honest failed-setup state
- [ ] Vision stage default-off, separate VISION_* keys, explicit off-device confirmation, never a pass
- [ ] PDD (docs/qa/user-flow.md), SDD (docs/qa/adapter-spec.md), TDD (docs/qa/test-plan.md) committed
- [ ] Hidden holdout authored outside the tree; receipt on issue #9; contents never committed
- [ ] Gates green, PR Refs #9, squash auto-merge armed
- [ ] Live runs (design-bakery + localhost Study OS via real Laya) — PENDING RUNTIME, tracked on #9

## Evidence and sources

- Spec: `docs/qa/adapter-spec.md` (SDD) with Laya interface verified against
  ChenneyZhuang/laya-browser-agent @ main 2026-09-29 (serve.py, page.py,
  decider.py)
- Issue #9 owner corrections 2026-09-29 17:50 / 17:51 / 17:56 / 17:58 supersede
  the issue body (URL-only; Laya default fail-closed; runner=provider)

## Related records

- Leaf owning issue: https://github.com/Pukujan/jev-ultrafast/issues/9 (parent: none)
- Primary writer / branch: Luna worker / `task/JUF-0003-frontend-qa-bootstrap`

## Checkpoint log

### 2026-09-29 - shared surface committed

Completed:
- pyproject playwright dep + `jev-qa` entry point; .gitignore qa-runs/, qa-holdout/
- contracts.py (types, provider alias table incl. vision row, constants)
- Vendored mermaid 11.17.2 (sha256 581ed7d7…) with provenance note
- adapter-spec.md SDD incl. describe-v1 flattening, keywatch detached-process
  mechanism, vision credential separation, link-probe confidence rules
- filename legend frontend-qa.md/.json; CGM adapter + writing validators VALID

Evidence:
- git commit ad20dc3 holds the shared surface; `continuity validate --root .` → VALID
- mermaid bundle re-downloaded from the exact-version URL and sha256-matched before commit

Decisions:
- Laya arm flattens dict criteria to describe-v1 strings in one shared request body
  rather than switching to /v1/table, so validation and target mapping stay untouched
- keywatch is a detached child process (sys.executable, absolute state path), not a thread,
  so cleanup survives the CLI exit
- link findings stay candidate unless the Playwright GET probe supplies status evidence;
  the explorer never claims HTTP status

Blocked/uncertain:
- Live acceptance (real Laya model, browsers, Study OS localhost) open on #9

Next:
- Integrate module implementations, full offline test matrix, gates, PR Refs #9

### 2026-09-29 - bootstrap stream reconciled to shipped main

Owner decision on issue #9 (comment 21:10Z): the harness ships on
`task/JUF-0003-frontend-qa-impl` (PR #10, merge 656c42a); this stream
stays untouched until its owner reconciles. That reconciliation is this
entry. `main` is now the only frontend QA implementation.

Completed:
- Merged origin/main into this branch; kept the shipped modules and
  retired the superseded scaffold (`frontend_qa.py`, root `providers.py`,
  `test_frontend_qa.py`, the three docs/…_FRONTEND_QA.md drafts)
- Fixed the three Windows-only failures the merge exposed: pid liveness
  now queries kernel32 instead of `os.kill(pid, 0)` (WinError 87 on every
  pid here), and an inserted key's identity moved from raw-line bytes to a
  newline-agnostic `NAME=value` content digest, so a CRLF editor re-save
  no longer leaves mark_used/guarded_remove behind
- Added one deterministic regression test: same content under CRLF still
  refreshes and removes; an operator-retyped value still does not

Evidence:
- `uv run ruff check jev_ultrafast tests` passed
- `uv run pytest` → 209 passed, 1 skipped (206 of these run the shipped
  suite green on this machine for the first time)
- `node --check jev_ultrafast/static/app.js` passed; `uv build` passed;
  `continuity validate --root .` VALID
- Playwright 1.63 finds cached chromium-1243; the localdecide server
  checkout exposes exactly the `/healthz` + `/v1/systemone` dialect the
  adapter documents, defaulting to 127.0.0.1:8791

Decisions:
- No new QA surface is ported back from the scaffold; the shipped modules
  win every overlap
- Digest semantics are documented as content identity in the adapter spec
  instead of byte identity, because editors change newline style without
  changing whose credential a line is

Blocked/uncertain:
- Live AC9 runs still open: Design Bakery through the packaged Laya path,
  operator-hosted Study OS URL, reviewer-owned hidden holdout
- The localdecide venv install (CPU torch) was still running when this
  entry was written

Next:
- Commit and push this reconciliation, open a PR Refs #9, then start the
  Laya server and run the first live acceptance pass

## Handoff

Read PROJECT → CURRENT → this task → docs/qa/adapter-spec.md → issue #9
(its owner comments override the body). Checkpoint before stopping.
