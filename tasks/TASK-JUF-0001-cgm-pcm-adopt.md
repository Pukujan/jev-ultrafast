# TASK-JUF-0001 — Adopt CGM + PCM

<!-- continuity:task {"acceptance":["continuity validate VALID / preflight TARGET_VALID","CGM validate_content_system stdout starts with VALID","PR to main linking issue #3","CI job named gates present","OpenRouter Decisions path in model.py without requiring TypeSafe key","README product-only (no CGM cite)"],"depends_on":[],"goal":"Adopt CGM 0.5.4 + PCM continuity overlay, OpenRouter Decisions wiring alignment, gates CI, and product README regen","id":"JUF-0001","issue_url":"https://github.com/Pukujan/jev-ultrafast/issues/3","next_action":"Push branch, open PR Refs #3, arm squash auto-merge, apply main ruleset with required gates","owner":"Grok Bot","priority":"high","protocol_version":"0.1.0-draft","schema":"project-continuity.task.v1","status":"active","why":"Fresh agents need TARGET_VALID continuity and evidence-bounded product docs without requiring a TypeSafe key"} -->

- Status: active
- Owner: Grok Bot
- Priority: high
- Depends on: none
- Issue: https://github.com/Pukujan/jev-ultrafast/issues/3
- Branch: `chore/cgm-pcm-adopt`

## Goal

Adopt CGM 0.5.4 + PCM continuity overlay, OpenRouter Decisions wiring alignment, gates CI, and product README regen.

## Why

Fresh agents need TARGET_VALID continuity and evidence-bounded product docs without requiring a TypeSafe key.

## Allowed files

- `.continuity/**`, `schemas/v1/**`, `PROJECT.md`, `HANDOFF.md`, `checkpoints/**`, `tasks/**`
- `.content-system/**`
- `AGENTS.md`, `README.md`, `docs/POLICY.md` (do not clobber ownership semantics)
- `jev_ultrafast/model.py`, `.env.example`
- `.github/workflows/**`

## Human outcome

A new session can recover purpose, OpenRouter-only auth, Study-os pointers, and the next task from the repo plus live issues.

## Scope and boundaries

- In scope: PCM overlay, CGM adapter, README regen, Decisions wiring alignment, gates CI, enforcement notes
- Out of scope: Study-os product code, inventing performance metrics, narrating CGM in README
- Dependencies/uncertainty: Hosted Actions must run before `gates` is a verified required check

## Acceptance criteria

- [x] `continuity validate` VALID / preflight TARGET_VALID
- [x] CGM validate stdout starts with VALID
- [ ] PR to main linking issue #3
- [x] CI job named `gates` present
- [x] OpenRouter Decisions path in `model.py` without requiring TypeSafe key
- [x] README product-only (no CGM cite)

## Evidence and sources

Local validators green before push (see checkpoint log).

## Reproduction details (only when needed)

N/A for docs/adoption overlay.

## Related records

- Leaf owning issue: https://github.com/Pukujan/jev-ultrafast/issues/3 (parent: none)
- Primary writer / branch: Grok Bot / `chore/cgm-pcm-adopt`
- Related PR/CI evidence: pending push

## Checkpoint log

### 2026-09-27 — Grok Bot adoption prep

Completed:
- PCM overlay schemas/config/PROJECT/CURRENT/HANDOFF/tasks (prefix JUF)
- CGM `.content-system` adapter pinned to helper 0.5.4 / c95d73a
- Product README regen; OpenRouter model/.env alignment; gates CI workflow
- Issues enabled; leaf issue #3; task JUF-0001

Evidence:
- `continuity validate --root D:\claude\jev-ultrafast` → VALID
- CGM `validate_content_system.py` → VALID: content-generation-modules contract and target adapter
- `continuity --version` → 0.6.0

Decisions:
- Mature TARGET_ADOPTION overlay (init refused AGENTS.md/README.md conflicts)
- Task prefix JUF; register existing product screenshots/gif as non-narrative assets
- Align model.py with POLICY OpenRouter Decisions (no TypeSafe key required)

Blocked/uncertain:
- Hosted Actions / required-check `gates` not yet verified on a live PR
- Main ruleset requiring `gates` pending first green check appearance

Next:
- Push branch, open PR Refs #3, arm squash auto-merge, apply main ruleset requiring gates

## Handoff

Read PROJECT → CURRENT → this task → docs/POLICY.md → README. Checkpoint before stopping.
