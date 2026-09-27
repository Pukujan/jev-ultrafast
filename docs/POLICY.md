# Adopter & ownership policy

Durable rules for who owns what when Ultrafast is used by adopters (e.g. Study-os).

## Ownership split

| Party | Owns | Does not own |
| --- | --- | --- |
| **Adopters** (e.g. Study-os) | Crawl goals, live targets, defect-report *consumption*, their own product docs/schemas | Fork code, Ultrafast harness/CDP, Decisions wiring, artifact schema *implementation* in this repo |
| **This repo (jev-ultrafast) / Grok Bot** | OpenRouter Decisions wiring, harness/CDP, artifact schema *alignment*, Ultrafast code changes | Adopter product code, private study-log data, TypeSafe-only paths |

Adopters **use** Ultrafast for crawls and defect reports. They do **not** own fork code. Code changes land here via this repo’s Grok Bot (jev-ultrafast).

## OpenRouter Decisions (only)

- Endpoint: `POST https://openrouter.ai/api/alpha/decisions`
- Auth: `OPENROUTER_API_KEY` (server-side / env; never commit keys)
- Model: `typesafe/jev-1.13`
- **No TypeSafe key required.** Decisions via OpenRouter is the supported path.

See also `docs/OPENROUTER-DECISIONS.md` if present for request/response details.

## Study-os live target & defect contract

When the adopter is Study-os:

- **Live target:** https://study.design-bakery.com (guest)
- **PDD / exploration:** Study-os `docs/PDD_UX_DEFECT_EXPLORATION.md`
- **Defect report schema:** Study-os `docs/schemas/ux-defect-report.v1.json`

The defect-report contract lives in Study-os. Do **not** copy private study-log data into this repo; align artifacts to that schema by reference.

## Agent rules (short)

1. Adopter asks for crawls/reports → run against their contract; do not treat their fork as source of truth for Ultrafast.
2. Wiring, harness, CDP, schema alignment, Ultrafast patches → this repo / Grok Bot owns them.
3. Prefer OpenRouter Decisions; never require a TypeSafe key.
4. Never print secrets or API keys.
