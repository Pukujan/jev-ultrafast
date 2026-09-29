# Frontend QA terminal flow

An operator enters one command and provides an already-reachable hosted URL or localhost URL. The operator starts any local frontend/backend services before running QA; the CLI does not accept a repository path or execute project commands. Local Laya-driven exploration is the default. The operator can explicitly select Jev as a separate comparison/alternate arm; only then are Jev provider credentials selected. The CLI scans only the Jev package's `.env`; a chosen value is never displayed. Playwright provides the browser substrate for the selected exploration, with deterministic assertions as supporting evidence rather than a replacement for model-driven exploration. Vision is an independent optional stage. Run output includes a CSV, an event-derived Mermaid source, provenance JSON, and a static HTML summary.

The current implementation performs HTTP and static HTML checks. It cannot establish whether JavaScript-bound controls work, whether browser console errors occur, or whether layout breaks at a viewport. The report states that limitation instead of treating an empty defect list as a pass.

## PDD acceptance boundary

- Reproduce every finding using its URL, action, timestamp and evidence reference.
- Never treat the browser agent's DONE response as evidence of a pass.
- Never copy target credentials, cookies or private transcripts into output.
- Laya guided exploration is the default and required local path; missing Laya must fail closed without Jev or deterministic-only fallback. Jev is an explicit alternate/comparison arm. Playwright is the browser substrate and supplies supporting deterministic evidence; standalone browser assertions may be skipped. Vision is independent and defaults off. A report must say `NOT RUN` when an optional stage was skipped.

Vision is off by default. On this PC, local vision is limited to a 2B-class option; hosted vision may use a 4B-class option. Current catalog/model availability is not treated as validated accuracy: live OpenRouter catalog inspection found Gemma 3 4B but no Qwen3.5 4B. The owner’s Gemma 3 4B synthetic pilot had 8/8 sensitivity, 0/8 specificity, and 2/8 exact-category accuracy in an isolated pass; paired pass had 8/8 sensitivity, 0/2 specificity, and 2/8 exact-category accuracy. This is a weak pilot, not model acceptance. A local Ollama Qwen3.5 2B pull stalled at 19 KB of 2.7 GB and was stopped. No model download is automatic. Holdout cases should inject clipping, overflow, alignment, spacing, and overlap problems and include clean screenshots to measure false positives.

Browser timing reports should keep navigation timing, event-to-next-paint, event-to-asserted-state, request/response, visual settle, and screenshot duration separate. Playwright documents action durations, DOM snapshots, and screenshots in [Trace Viewer](https://playwright.dev/docs/trace-viewer); its trace mode must be disclosed because tracing all tests is performance-heavy. Playwright [discourages `networkidle` for test readiness](https://playwright.dev/docs/api/class-page). Synthetic lab latency is not field Interaction to Next Paint (INP).
