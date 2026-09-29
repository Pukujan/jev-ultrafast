# Task JUF-0003 — Give operators one frontend QA command

<!-- continuity:task {"acceptance":["Interactive entry point accepts an already-reachable hosted URL or localhost URL","Local services are operator-started; CLI never executes target project commands","Laya guided exploration is the default and required local path; Jev is an explicit comparison/alternate arm","Playwright is the browser substrate for the selected exploration; deterministic assertions are supporting evidence, not replacement exploration","Vision is independent and optional, off by default","OpenRouter, TypeSafe and OpenCode providers are isolated and tested","Provider discovery never reads or displays secret values","CLI-inserted keys alone can expire after three idle hours","Frontend findings include reproducible browser evidence","CSV, Mermaid, provenance JSON and offline HTML report are written and opened","PDD, SDD and TDD artifacts include metamorphic, fuzz and hidden-holdout coverage","Blind Laya acceptance against Design Bakery and operator-hosted local Study OS passes or is explicitly blocked on missing Laya","Repository gates pass"],"depends_on":[],"goal":"Add terminal frontend QA modules for reachable hosted/localhost URLs with default Laya exploration, optional Jev comparison, browser evidence, optional vision, providers, and offline reports","id":"JUF-0003","issue_url":"https://github.com/Pukujan/jev-ultrafast/issues/9","next_action":"Complete the Laya-driven Playwright exploration loop and evidence pipeline; run live acceptance only after runtime prerequisites are ready","owner":"Luna worker (delegated); Grok Bot review required","priority":"high","protocol_version":"0.1.0-draft","schema":"project-continuity.task.v1","status":"active","why":"Operators currently need separate wrappers and lose reproducible provenance across frontend checks"} -->

- Status: active
- Owner: Luna worker (delegated); Grok Bot review required
- Priority: high
- Depends on: none
- Issue: https://github.com/Pukujan/jev-ultrafast/issues/9
- Branch: `task/JUF-0003-frontend-qa-bootstrap`

## Goal

Let an operator provide an already-reachable hosted or localhost URL and receive an offline report from default local Laya-driven exploration. Jev is a separately selected comparison/alternate arm. Local services are started and managed by the operator; the CLI takes only the URL.

## Evidence and boundary

Issue #9 is open and names this branch and task. The owner has clarified that v1 accepts only already-reachable hosted or localhost URLs; local app services belong to the operator, and this CLI must not execute target project commands. Laya mode must use a discovered local interface, and Study OS code and private evidence stay out of this repository. No Laya executable or endpoint is present in the worker environment; live Laya acceptance is therefore a known prerequisite until discovery changes that fact.

## Acceptance

See the owning issue for full acceptance. In particular, the two-target Laya acceptance is not passed by substituting Jev. Preserve public outputs as redacted evidence only.

## Checkpoint log

### 2026-09-29 — implementation started

Completed:
- Added the terminal entry point, static HTTP/link inspection, CSV, Mermaid source, provenance JSON, and offline report scaffold
- Added the optional Playwright browser pass and the documented Laya `Router.predict` adapter boundary
- Added PDD/SDD/TDD drafts and fake-clock/key-discovery/report tests

Evidence:
- Live issue #9 verified open; task identity and branch match
- `continuity validate --root .` initially failed because this checkpoint log needed its required fields; repair is pending validation
- `uv run pytest -q` → 35 passed before the most recent changes
- `uv run ruff check` on the changed Python files → passed; `uv run pytest -q` after key-cleanup and DOM variation coverage → 42 passed
- `uv run python -m compileall jev_ultrafast tests`, `node --check jev_ultrafast/static/app.js`, package build, and continuity validation → passed
- Repository-wide Ruff reports 12 lint findings only in the pre-existing untracked `full_defect_crawl.py`; that file was preserved untouched
- Runtime discovery found neither the `laya` module nor Playwright installed. The OpenCode command exists, but the official server docs expose an OpenAPI agent server rather than this repository's typed decision endpoint.
- Local Laya runtime absent; package interface found in upstream package documentation

Decisions:
- Keep Laya local and fail closed; no Jev/OpenRouter fallback in Laya mode
- Playwright is an independent optional stage; vision judging stays off unless separately requested
- Preserve the existing OpenRouter Decisions path as default

Blocked/uncertain:
- Laya package and checkpoint are not installed; required live acceptance has not run
- Visual holdout and reviewer-owned hidden acceptance answers were not available
- OpenCode has no tested typed-decision adapter; full provider acceptance remains incomplete
- The current report draws an offline SVG and includes workflow.mmd; a bundled Mermaid runtime is still needed for the owner correction
- TypeSafe and OpenCode provider request adapters are not implemented; the CLI static pass does not call any selected provider
- Playwright is optional but absent here; browser error, screenshot, and overflow stages were not run
- Existing untouched `full_defect_crawl.py` triggers pre-existing repository-wide Ruff failures

Next:
- Run focused tests, formatting, packaging, and validators; report the live Laya/Playwright/vision blockers without substituting runners

### 2026-09-29 — owner clarified URL-only target scope

Completed:
- Reconciled v1 to already-reachable hosted or localhost URLs; local service lifecycle is operator-owned
- Removed target repository selection and project service startup from the CLI
- Updated issue #9 with a superseding owner correction and aligned PDD/SDD/TDD, README, CURRENT, HANDOFF, and task projection

Evidence:
- Issue #9 correction: https://github.com/Pukujan/jev-ultrafast/issues/9#issuecomment-5895613229
- Live acceptance was intentionally not run during this scope-only follow-up

Decisions:
- Keep Laya and Jev as separate selectable modes; keep Playwright independently optional and vision opt-in
- Treat Laya as the required local exploration path and Jev as a distinct optional comparison arm; Playwright and vision stay independently selectable
- Default to Laya; fail closed without a deterministic-only or Jev fallback when it is unavailable
- Record the Gemma 3 4B and Qwen3.5 2B owner pilot/download evidence as unresolved validation, not model acceptance

Blocked/uncertain:
- All previously listed runtime, provider, hidden holdout, and live acceptance blockers remain

Next:
- Complete remaining acceptance implementation and run live targets only after required runtime and operator-provided local URL are available

### 2026-09-29 14:12:50-04:00 — Codex, checkpointing Luna worker's committed increment per owner request

<!-- continuity:checkpoint {"agent":"Codex, checkpointing Luna worker's committed increment per owner request","blocked":["The Laya-driven browser exploration loop and live Laya runtime are not ready; Playwright and vision validation are incomplete; no live target or blind hidden holdout was run. Keep issue #9 open."],"changed":["Added frontend QA CLI and provider adapter scaffolding, key cleanup, reports, focused tests, PDD/SDD/TDD, README/policy updates, and current/task/handoff projections."],"completed":["Operators lacked a single URL-based frontend QA entry point. Added the terminal scaffold, URL-only target intake, local Laya default with explicit Jev comparison selection, report outputs, tests, and PDD/SDD/TDD projections."],"decisions":["V1 accepts only a reachable hosted or operator-started localhost URL. Laya local exploration is the default and required path; Jev is a separate selected comparison arm. Playwright is the browser substrate, deterministic assertions support the exploration, and vision is optional and off by default."],"evidence":["Issue #9 is still OPEN and has owner corrections for URL-only scope, Laya default, Jev comparison, and vision research. Focused Ruff passed; 44 tests passed; Node syntax, package build, continuity validation, issue verification, and diff checks passed. Hosted Gemma 3 4B synthetic pilot is weak and not acceptance evidence: 8/8 sensitivity, 0/8 specificity, 2/8 exact categories; paired pilot 8/8 sensitivity, 0/2 specificity, 2/8 exact categories. Local Qwen3.5 2B pull stalled and was stopped."],"next_action":"Complete the Laya-driven Playwright exploration loop and provider/vision adapters, then run independent blind acceptance against Design Bakery and an operator-provided local Study OS URL; keep acceptance open until evidence passes.","protocol_version":"0.1.0-draft","schema":"project-continuity.checkpoint.v1","task_id":"JUF-0003","timestamp":"2026-09-29T14:12:50-04:00"} -->
<!-- continuity:checkpoint-operation {"payload_sha256":"f46c0ab5fd25e820f21fb1ad2c73959159bb1d7dec5a87fd89ce7c12e8670e6e","request_id":"juf-0003-20260929-7f034ba1","schema":"project-continuity.checkpoint-operation.v1","task_id":"JUF-0003"} -->

Completed:
- Operators lacked a single URL-based frontend QA entry point. Added the terminal scaffold, URL-only target intake, local Laya default with explicit Jev comparison selection, report outputs, tests, and PDD/SDD/TDD projections.

Evidence:
- Issue #9 is still OPEN and has owner corrections for URL-only scope, Laya default, Jev comparison, and vision research. Focused Ruff passed; 44 tests passed; Node syntax, package build, continuity validation, issue verification, and diff checks passed. Hosted Gemma 3 4B synthetic pilot is weak and not acceptance evidence: 8/8 sensitivity, 0/8 specificity, 2/8 exact categories; paired pilot 8/8 sensitivity, 0/2 specificity, 2/8 exact categories. Local Qwen3.5 2B pull stalled and was stopped.

Decisions:
- V1 accepts only a reachable hosted or operator-started localhost URL. Laya local exploration is the default and required path; Jev is a separate selected comparison arm. Playwright is the browser substrate, deterministic assertions support the exploration, and vision is optional and off by default.

Changed:
- Added frontend QA CLI and provider adapter scaffolding, key cleanup, reports, focused tests, PDD/SDD/TDD, README/policy updates, and current/task/handoff projections.

Blocked/uncertain:
- The Laya-driven browser exploration loop and live Laya runtime are not ready; Playwright and vision validation are incomplete; no live target or blind hidden holdout was run. Keep issue #9 open.

Next:
- Complete the Laya-driven Playwright exploration loop and provider/vision adapters, then run independent blind acceptance against Design Bakery and an operator-provided local Study OS URL; keep acceptance open until evidence passes.
