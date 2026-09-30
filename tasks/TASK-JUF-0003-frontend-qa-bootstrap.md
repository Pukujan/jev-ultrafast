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

### 2026-09-29 22:15:39 UTC — Luna worker (bootstrap stream), owner-directed parallel continuation

<!-- continuity:checkpoint {"agent":"Luna worker (bootstrap stream), owner-directed parallel continuation","blocked":["AC9 live runs open: Design Bakery Laya pass executing now on this machine; Study OS acceptance needs the operator's localhost URL; hidden-holdout grading belongs to the reviewer. Issue #9 stays open."],"changed":["docs/qa/adapter-spec.md, jev_ultrafast/qa/keywatch.py, jev_ultrafast/qa/providers.py, tests/test_qa_providers.py, checkpoints/CURRENT.md, tasks/TASK-JUF-0003-frontend-qa-bootstrap.md; deleted superseded scaffold modules/tests/docs."],"completed":["Reconciled the bootstrap stream with the shipped harness: merged main 656c42a, retired the superseded scaffold, and fixed the three Windows-only failures the merge exposed (kernel32 pid liveness; newline-agnostic inserted-key digest so CRLF editor re-saves keep idle cleanup working)."],"decisions":["main is the single frontend QA implementation; key identity is NAME=value content, not raw bytes; no scaffold code is ported back."],"evidence":["Windows: ruff clean on jev_ultrafast+tests; pytest 209 passed 1 skipped; node --check, uv build, continuity validate all green; pushed chain bd137ae/0aacba3/fe70b39; PR #11 Refs #9 open."],"next_action":"Collect the Design Bakery live-Laya receipt from the running acceptance slice, post it on #9, then final-push and arm gates on PR #11 only after checks are verified on the last push.","protocol_version":"0.1.0-draft","schema":"project-continuity.checkpoint.v1","task_id":"JUF-0003","timestamp":"2026-09-29T22:15:39Z"} -->
<!-- continuity:checkpoint-operation {"payload_sha256":"6b5900a4bafd049cc1e71fdcc3e0c6e07506f33876560174b54d5306f0727262","request_id":"juf-0003-20260929-fe70b391","schema":"project-continuity.checkpoint-operation.v1","task_id":"JUF-0003"} -->

Completed:
- Reconciled the bootstrap stream with the shipped harness: merged main 656c42a, retired the superseded scaffold, and fixed the three Windows-only failures the merge exposed (kernel32 pid liveness; newline-agnostic inserted-key digest so CRLF editor re-saves keep idle cleanup working).

Evidence:
- Windows: ruff clean on jev_ultrafast+tests; pytest 209 passed 1 skipped; node --check, uv build, continuity validate all green; pushed chain bd137ae/0aacba3/fe70b39; PR #11 Refs #9 open.

Decisions:
- main is the single frontend QA implementation; key identity is NAME=value content, not raw bytes; no scaffold code is ported back.

Changed:
- docs/qa/adapter-spec.md, jev_ultrafast/qa/keywatch.py, jev_ultrafast/qa/providers.py, tests/test_qa_providers.py, checkpoints/CURRENT.md, tasks/TASK-JUF-0003-frontend-qa-bootstrap.md; deleted superseded scaffold modules/tests/docs.

Blocked/uncertain:
- AC9 live runs open: Design Bakery Laya pass executing now on this machine; Study OS acceptance needs the operator's localhost URL; hidden-holdout grading belongs to the reviewer. Issue #9 stays open.

Next:
- Collect the Design Bakery live-Laya receipt from the running acceptance slice, post it on #9, then final-push and arm gates on PR #11 only after checks are verified on the last push.

### 2026-09-29 23:05:56 UTC — Luna worker (live acceptance fixes), parallel subagent orchestration

<!-- continuity:checkpoint {"agent":"Luna worker (live acceptance fixes), parallel subagent orchestration","blocked":["Study OS acceptance still needs the operator's localhost URL; hidden-holdout grading belongs to the reviewer; a fresh live re-run with the fixed stage must record real findings (or honestly none) before AC9 Design Bakery closes. Issue #9 stays open."],"changed":["jev_ultrafast/qa/playwright_stage.py, jev_ultrafast/qa/artifacts.py, jev_ultrafast/qa/report.py, jev_ultrafast/qa/cli.py, docs/qa/adapter-spec.md, docs/qa/user-flow.md, tests/test_qa_playwright.py, tests/test_qa_cli.py, tests/test_qa_fuzz.py, tests/test_qa_artifacts.py, checkpoints/CURRENT.md."],"completed":["First live Design Bakery pass through the packaged jev-qa path: localdecide server on 127.0.0.1:8791 answered healthz and describe-v1 /v1/systemone decisions (backend laya-torch); the run wrote defects.csv, events.json, workflow.mmd, run.json, and an offline report.html. The pass exposed three shipped-code faults, all fixed on this increment: page.title read as a property crashed the evidence stage and mislabeled it failed-setup; fatal sweep faults now record failed while missing-browser/import faults keep failed-setup; and the browser setup-failure path returned exit 2 without writing the run, breaking the recorded-run promise. Test doubles now match the real Playwright API."],"decisions":["failed-setup stays reserved for environment repair; a code fault must never read like a missing browser install; the Laya acceptance environment is proven reproducible (serve + dedicated Chrome on BU_CDP_URL)."],"evidence":["Windows full suite 211 passed 1 skipped (ruff clean, node check, uv build, continuity validate VALID); live facts in qa-runs folders 2 and 3 and the acceptance agent report; classification tests pin failed vs failed-setup; CLI test pins the four writers on the setup-failure path."],"next_action":"Merge this increment, rerun the single Design Bakery pass from merged main with the repaired evidence stage, and post its independent-confirmation receipt on #9.","protocol_version":"0.1.0-draft","schema":"project-continuity.checkpoint.v1","task_id":"JUF-0003","timestamp":"2026-09-29T23:05:56Z"} -->
<!-- continuity:checkpoint-operation {"payload_sha256":"65ad885fcb9f1c30236754ef684841ab5a28ba3651de5c26d0cbe678a23ef28c","request_id":"juf-0003-20260929-livefix1","schema":"project-continuity.checkpoint-operation.v1","task_id":"JUF-0003"} -->

Completed:
- First live Design Bakery pass through the packaged jev-qa path: localdecide server on 127.0.0.1:8791 answered healthz and describe-v1 /v1/systemone decisions (backend laya-torch); the run wrote defects.csv, events.json, workflow.mmd, run.json, and an offline report.html. The pass exposed three shipped-code faults, all fixed on this increment: page.title read as a property crashed the evidence stage and mislabeled it failed-setup; fatal sweep faults now record failed while missing-browser/import faults keep failed-setup; and the browser setup-failure path returned exit 2 without writing the run, breaking the recorded-run promise. Test doubles now match the real Playwright API.

Evidence:
- Windows full suite 211 passed 1 skipped (ruff clean, node check, uv build, continuity validate VALID); live facts in qa-runs folders 2 and 3 and the acceptance agent report; classification tests pin failed vs failed-setup; CLI test pins the four writers on the setup-failure path.

Decisions:
- failed-setup stays reserved for environment repair; a code fault must never read like a missing browser install; the Laya acceptance environment is proven reproducible (serve + dedicated Chrome on BU_CDP_URL).

Changed:
- jev_ultrafast/qa/playwright_stage.py, jev_ultrafast/qa/artifacts.py, jev_ultrafast/qa/report.py, jev_ultrafast/qa/cli.py, docs/qa/adapter-spec.md, docs/qa/user-flow.md, tests/test_qa_playwright.py, tests/test_qa_cli.py, tests/test_qa_fuzz.py, tests/test_qa_artifacts.py, checkpoints/CURRENT.md.

Blocked/uncertain:
- Study OS acceptance still needs the operator's localhost URL; hidden-holdout grading belongs to the reviewer; a fresh live re-run with the fixed stage must record real findings (or honestly none) before AC9 Design Bakery closes. Issue #9 stays open.

Next:
- Merge this increment, rerun the single Design Bakery pass from merged main with the repaired evidence stage, and post its independent-confirmation receipt on #9.

### 2026-09-30 02:08:16 UTC — Luna worker (arms comparison), owner-directed scope to Jev and OpenJev

<!-- continuity:checkpoint {"agent":"Luna worker (arms comparison), owner-directed scope to Jev and OpenJev","blocked":["Hidden holdout grading belongs to the independent reviewer; Study OS product depth needs a path past the login gate; the four named gaps (loopback text source, off-origin attribution, stale budget, zero-progress signal) await owner decisions."],"changed":["checkpoints/CURRENT.md, tasks/TASK-JUF-0003-frontend-qa-bootstrap.md, docs/benchmarks/** (new comparison folder and catalog rows)."],"completed":["Recorded the two-arm live acceptance comparison in the repository: four single post-fix jev-qa runs at main adca368 (Jev and OpenJev against design-bakery.com and study.design-bakery.com), published as docs/benchmarks/frontend-qa-arms-2026-09-29/ with the harness's own Mermaid workflow sources, full defect CSVs, a machine summary, and a plain-language report. Owner direction dropped the Laya arm from this comparison; the shipped Laya default in code is unchanged."],"decisions":["Laya excluded from this comparison by owner direction, docs only; study-OS guest depth stays unproven rather than called a pass; four harness gaps are recorded as owner decisions, not silently patched."],"evidence":["Recomputed from run folders before writing: Jev 14 executed steps over 6 pages with one dead control and 37 mostly off-origin link rows; OpenJev 25 steps on one page, fingerprint unchanged throughout, dead control at step 1; Jev on Study OS answered BLOCKED at 0.33-0.36 with zero clicks; OpenJev reached the credentials form and died on a TYPE_TEXT with no text source. Copied charts and CSVs verified md5-identical to their sources; ruff and continuity validate green."],"next_action":"Push the docs branch, open the PR Refs #9, and carry the four gap decisions to the owner on the leaf.","protocol_version":"0.1.0-draft","schema":"project-continuity.checkpoint.v1","task_id":"JUF-0003","timestamp":"2026-09-30T02:08:16Z"} -->
<!-- continuity:checkpoint-operation {"payload_sha256":"ab57f0bb05c00e25d54036953fccda76434da0016f5bc954be996a9b6ab81c46","request_id":"juf-0003-20260930-armsdocs1","schema":"project-continuity.checkpoint-operation.v1","task_id":"JUF-0003"} -->

Completed:
- Recorded the two-arm live acceptance comparison in the repository: four single post-fix jev-qa runs at main adca368 (Jev and OpenJev against design-bakery.com and study.design-bakery.com), published as docs/benchmarks/frontend-qa-arms-2026-09-29/ with the harness's own Mermaid workflow sources, full defect CSVs, a machine summary, and a plain-language report. Owner direction dropped the Laya arm from this comparison; the shipped Laya default in code is unchanged.

Evidence:
- Recomputed from run folders before writing: Jev 14 executed steps over 6 pages with one dead control and 37 mostly off-origin link rows; OpenJev 25 steps on one page, fingerprint unchanged throughout, dead control at step 1; Jev on Study OS answered BLOCKED at 0.33-0.36 with zero clicks; OpenJev reached the credentials form and died on a TYPE_TEXT with no text source. Copied charts and CSVs verified md5-identical to their sources; ruff and continuity validate green.

Decisions:
- Laya excluded from this comparison by owner direction, docs only; study-OS guest depth stays unproven rather than called a pass; four harness gaps are recorded as owner decisions, not silently patched.

Changed:
- checkpoints/CURRENT.md, tasks/TASK-JUF-0003-frontend-qa-bootstrap.md, docs/benchmarks/** (new comparison folder and catalog rows).

Blocked/uncertain:
- Hidden holdout grading belongs to the independent reviewer; Study OS product depth needs a path past the login gate; the four named gaps (loopback text source, off-origin attribution, stale budget, zero-progress signal) await owner decisions.

Next:
- Push the docs branch, open the PR Refs #9, and carry the four gap decisions to the owner on the leaf.

## Handoff

Read PROJECT → CURRENT → this task → docs/qa/adapter-spec.md → issue #9
(its owner comments override the body). Checkpoint before stopping.
