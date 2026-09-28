# TASK-JUF-0002 - Re-pin CGM 0.5.7 + always-on HSW

<!-- continuity:task {"acceptance":["adapter validate stdout starts with VALID","writing-mode validate stdout starts with VALID","verify_hsw_applied HSW_VERIFY OK","pin helper_version 0.5.7 @ c069613ca8b3e02bcf5aba1960160583537f8a3a with eight modules including human-output-naming","AGENTS.md contains always-on CGM writing rule block","PR Refs #7 merged or squash auto-merge armed"],"depends_on":[],"goal":"Re-pin CGM 0.5.4 to 0.5.7, eight modules, always-on HSW inject in AGENTS.md, validate+verify","id":"JUF-0002","issue_url":"https://github.com/Pukujan/jev-ultrafast/issues/7","next_action":"Push branch, open PR Refs #7, arm squash auto-merge when gates green","owner":"Grok Bot","priority":"high","protocol_version":"0.1.0-draft","schema":"project-continuity.task.v1","status":"active","why":"0.5.7 adds human-output-naming and requires every adopter to paste the always-on writing block at agent boot"} -->

- Status: active
- Owner: Grok Bot
- Priority: high
- Depends on: none
- Issue: https://github.com/Pukujan/jev-ultrafast/issues/7
- Branch: `juf/cgm-0.5.7-repin`

## Goal

Re-pin CGM 0.5.4 to 0.5.7, list all eight modules (including human-output-naming), and inject the always-on HSW system_block into AGENTS.md.

## Why

Without the bump, adapter modules lag the helper contract and agents miss the always-on HSW default for human-facing prose.

## Allowed files

- `.content-system/system-version.json`
- `.content-system/asset-manifest.json` (system_version bump only)
- `AGENTS.md` (always-on writing rule inject)
- `tasks/TASK-JUF-0002-*.md`

## Human outcome

Agents boot with the pinned 0.5.7 writing rule; validate and verify_hsw_applied pass against the pinned helper.

## Scope and boundaries

- In scope: pin, modules list, AGENTS inject, validators, PR + auto-merge
- Out of scope: README CGM cites, image-gen/writing-method README sections, Study-os product code
- Dependencies/uncertainty: required check `gates` must run before merge completes

## Acceptance criteria

- [ ] Adapter validate stdout starts with VALID
- [ ] Writing-mode validate stdout starts with VALID
- [ ] verify_hsw_applied HSW_VERIFY OK
- [ ] Pin is 0.5.7 @ c069613… with eight modules including human-output-naming
- [ ] AGENTS.md contains the always-on CGM writing rule block
- [ ] PR Refs #7 merged or squash auto-merge armed

## Evidence and sources

Local validators against CGM checkout at c069613 (see PR / checkpoint).

## Related records

- Leaf owning issue: https://github.com/Pukujan/jev-ultrafast/issues/7 (parent: none)
- Primary writer / branch: Grok Bot / `juf/cgm-0.5.7-repin`

## Checkpoint log

### 2026-09-28 - Grok Bot CGM 0.5.7 re-pin

Completed:
- Pin `.content-system/system-version.json` to helper 0.5.7 / c069613 with eight modules including human-output-naming
- Inject always-on HSW `system_block` into `AGENTS.md`
- Bump asset-manifest `system_version` to 0.5.7
- Open leaf issue #7; task JUF-0002

Evidence:
- `python scripts/validate_content_system.py --root <cgm> --adapter … --project-root …` → VALID: content-generation-modules contract and target adapter
- `python scripts/validate_content_system.py --root <cgm> --mode writing` → VALID: content-generation-modules writing contract
- `python scripts/verify_hsw_applied.py --root <cgm>` → HSW_VERIFY mode=contract status=OK; VALID: HSW always-on contract OK

Decisions:
- No `.content-system/filename-legends/` yet — assets have no `feature` claims; adapter legend dir optional when absent
- Keep README product-only (no CGM cite)

Blocked/uncertain:
- Hosted `gates` check must go green before squash merge completes

Next:
- Commit, push `juf/cgm-0.5.7-repin`, open PR Refs #7, arm squash auto-merge

## Handoff

Read PROJECT → CURRENT → this task → docs/POLICY.md → README. Checkpoint before stopping.
