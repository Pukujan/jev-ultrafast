# Jev Ultrafast — Project Contract

<!-- continuity:project {"id":"jev-ultrafast","protocol_version":"0.1.0-draft","schema":"project-continuity.project.v1","title":"Jev Ultrafast"} -->

<!-- pcm:github-progression:start -->
## GitHub-owned progression

GitHub Issues are required for PCM-governed project work and own task scope, acceptance, priority, ownership, dependencies, lifecycle and durable project progression. Merged default-branch history owns accepted code and normative/domain documents; PR checks and merge records own delivery facts. Checked-in PROJECT/CURRENT/TASK/checkpoint/handoff documents are mandatory versioned projections for task state, not a parallel authority. Local files, registries, context packs and chat are ephemeral execution aids. Domain-document ownership stays with the target project.

Every issue progress update MUST link the leaf child issue that owns the work, its parent ancestry and dependencies (or explicitly none). A top-level deliverable identifies itself as the leaf and says parent: none. Create one child per independently deliverable scope, never one per comment. Record task ID, primary writer and branch on the issue before creating its repository projection. Re-read live issues and relevant source revisions before resuming; the issue verifier checks identity/status, not semantic agreement.

Authorized owner/user direction can revise intent: record it on the owning GitHub issue with a correction/supersession link before dependent work. It cannot alter observed CI/merge facts or waive required gates. Stale projections yield to their field's authority. If direction, ownership or evidence conflicts remain unresolved, pause affected work and record uncertainty; continue independent safe work. One primary writer owns each task branch/checkpoint stream. Coordinate shared-document edits through linked issues/PRs, re-read the current base and reconcile concurrent changes; never force-push or overwrite another writer. Issue prose is not an atomic lock.

Label observed results, repository/external evidence, agent reports and inference separately. Preserve contradictory evidence with source/revision and mark conclusions disputed or unknown until resolved. Append correction/supersession evidence; never rewrite checkpoint history. An upstream correction MUST identify affected descendants and assumptions on their issues; pause, re-plan and revalidate dependent work before resuming. Follow explicit parent/dependency links within the affected scope; cycles or unknown lineage block affected claims. No graph database, local canonical ledger or autonomous polling agent is required.

Before every push, synchronize relevant docs and task/checkpoint projections, CURRENT/HANDOFF when affected, and reviewed catalog/generated index. Record leaf/parent/dependency links, source issue/comment revision, as-of status, evidence, blockers and next action. Commit product/docs first; `continuity checkpoint` then commits and synchronously pushes the checkpoint with a stable request ID. After every successful push, manually publish a leaf issue receipt keyed by request ID and exact pushed SHA, linking changed docs/checkpoint, PR, tests and pending gates; add a linked parent progression update. Retry a missing receipt without another checkpoint/push; inspect for the same key before posting. --receipt-repo and --receipt-issue are opt-in and still require a proven lookup; omit them and the receipt stays manual. Automatic issue-comment synchronization is not implemented.

Required CI and GitHub auto-merge are mandatory. Arm auto-merge only after the increment's final push: a later push races the merge window and strands outside accepted history. Verify protection, required reviews/checks on the exact current-base or merge-queue candidate, and auto-merge; missing, failed, skipped, stale or unverified gates fail closed: no completion or cleanup. After CI/merge, append the exact check results, PR/merge SHA and live issue status to the leaf and link the parent update; fetch and verify accepted history. Reconcile material doc/status corrections in a new synchronized increment. Receipt-only transitions need no recursive doc commit: docs retain an explicit as-of/pending state and point to the live issue. Never label local-only or merely pushed work delivered. Preserve unsafe resources and keep incomplete issues open.
<!-- pcm:github-progression:end -->

## Main goal

Ship a small, readable browser agent that turns one natural-language goal into validated page operations—operation plus target in one Decisions request—while keeping model output from becoming selectors or executable code.

## Why

Browser automation that asks an LLM to invent scripts or selectors is brittle and unsafe. Ultrafast keeps the action space indexed from the live page, lets Jev choose among supported operations and targets, and only calls a text model when the chosen operation is `TYPE_TEXT`.

## Scope

- OpenRouter Decisions API path (`https://openrouter.ai/api/alpha/decisions`, model `typesafe/jev-1.13`) with `OPENROUTER_API_KEY` only — no TypeSafe key required.
- Browser Harness / Chrome CDP connection, local inspector demo, library `Agent` API.
- Study-os guest/UX defect crawls against https://study.design-bakery.com and artifact logging aligned to the Study-os defect contract by reference.
- Task-scoped frontend QA terminal bootstrap (JUF-0003 / issue #9); see `docs/POLICY.md`. This does not change the core browser agent's OpenRouter-only provider contract.
- Fork maintenance relative to upstream `browser-use/jev-ultrafast`.

## Non-goals

- Owning adopter product code (e.g. Study-os itself).
- Requiring a TypeSafe account or `TYPESAFE_API_KEY`.
- Letting the model emit selectors, coordinates, shell, or executable JavaScript.
- Committing secrets or private study-log data.

## Delivery gates (PCM adopter enforcement)

- **PR-only to `main`** — no direct pushes for normal contributors.
- Required status check named exactly **`gates`** when Actions can run.
- Prefer **squash auto-merge when green** (`allow_auto_merge`).

## Definition of success

A fresh agent or human can recover purpose, OpenRouter-only auth rules, Study-os contract pointers, and the next bounded task from repository docs plus live GitHub issues without prior chat.

## Related contracts

- Agent loop rules: `AGENTS.md`
- Adopter ownership: `docs/POLICY.md`
- OpenRouter Decisions details: `docs/OPENROUTER-DECISIONS.md`
- Study-os crawl evidence: `docs/benchmarks/`
