# Benchmarks

## Runs

| Date (ET) | Path | Notes |
| --- | --- | --- |
| 2026-09-27 ~01:48–01:50 ET | [study-os-2026-09-27/](./study-os-2026-09-27/) | Guest crawl vs https://study.design-bakery.com ; OpenRouter Decisions `typesafe/jev-1.13`; 75 actions, 11 defects (P0 D004 Worked example). Also in Study-os `docs/benchmarks/ux-defect-jev-ultrafast/2026-09-27/`. |
| 2026-09-29 ~20:00–23:10 ET | [frontend-qa-arms-2026-09-29/](./frontend-qa-arms-2026-09-29/) | Four `jev-qa` runs, Jev and OpenJev arms against both live sites, after the settle and stale-snapshot fixes; 41 walked steps, 3 corroborated defects, and the harness gaps the runs exposed. |

An early `jev-qa` pass on 2026-09-29 recorded a finished exploration at step
zero on both sites. That was the harness racing a still-mounting page, not the
model choosing to stop; see the issue #9 receipts for the two fixes.