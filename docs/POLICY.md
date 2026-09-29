# Adopter & ownership policy

Durable rules for who owns what when Ultrafast is used by adopters (e.g. Study-os).

## Ownership split

| Party | Owns | Does not own |
| --- | --- | --- |
| **Adopters** (e.g. Study-os) | Crawl goals, live targets, defect-report *consumption*, their own product docs/schemas | Fork code, Ultrafast harness/CDP, Decisions wiring, artifact schema *implementation* in this repo |
| **This repo (jev-ultrafast) / Grok Bot** | OpenRouter Decisions wiring, harness/CDP, artifact schema *alignment*, Ultrafast code changes | Adopter product code, private study-log data, TypeSafe-only paths |

Adopters **use** Ultrafast for crawls and defect reports. They do **not** own fork code. Code changes land here via this repo’s Grok Bot (jev-ultrafast).

## Decision provider policies

### Task-scoped frontend QA provider exception (JUF-0003 / issue #9)

The existing Ultrafast browser agent continues to use OpenRouter Decisions as its only decision path. Issue #9 separately authorizes OpenRouter, TypeSafe, and OpenCode choices in the frontend QA bootstrap. This exception does not change the library agent's authentication contract. Provider credentials stay with the Jev package and are never read from or copied into a target repository. The current bootstrap discovers OpenRouter credentials and includes a unit-tested Laya SDK boundary, but its terminal flow does not yet run browser decisions. TypeSafe and OpenCode request adapters remain unfinished and must not be advertised as working.

- Endpoint for the core browser agent: `POST https://openrouter.ai/api/alpha/decisions` — its primary and only supported decision path
- Auth: `OPENROUTER_API_KEY` (server-side / env; never commit keys). No `TYPESAFE_API_KEY`.
- Model: `OPENROUTER_MODEL` defaults to `typesafe/jev-1.13`. That value is an **OpenRouter model slug** in the Decisions body, not a TypeSafe-account or System One backend switch.
- **No TypeSafe key required.** Decisions via OpenRouter is the supported path.

See `docs/OPENROUTER-DECISIONS.md` (§2b) for how `OPENROUTER_MODEL` works.

## Study-os live target & defect contract

When the adopter is Study-os:

- **Live target:** https://study.design-bakery.com (guest)
- **PDD / exploration:** Study-os `docs/PDD_UX_DEFECT_EXPLORATION.md`
- **Defect report schema:** Study-os `docs/schemas/ux-defect-report.v1.json`

The defect-report contract lives in Study-os. Do **not** copy private study-log data into this repo; align artifacts to that schema by reference.

## Agent rules (short)

1. Adopter asks for crawls/reports → run against their contract; do not treat their fork as source of truth for Ultrafast.
2. Wiring, harness, CDP, schema alignment, Ultrafast patches → this repo / Grok Bot owns them.
3. The core browser agent uses OpenRouter Decisions and never requires a TypeSafe key. See the task-scoped frontend QA exception above for issue #9's requested provider work.
4. Never print secrets or API keys.
