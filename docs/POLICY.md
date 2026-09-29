# Adopter & ownership policy

Durable rules for who owns what when Ultrafast is used by adopters (e.g. Study-os).

## Ownership split

| Party | Owns | Does not own |
| --- | --- | --- |
| **Adopters** (e.g. Study-os) | Crawl goals, live targets, defect-report *consumption*, their own product docs/schemas | Fork code, Ultrafast harness/CDP, Decisions wiring, artifact schema *implementation* in this repo |
| **This repo (jev-ultrafast) / Grok Bot** | OpenRouter Decisions wiring, harness/CDP, artifact schema *alignment*, Ultrafast code changes | Adopter product code, private study-log data, TypeSafe-only paths |

Adopters **use** Ultrafast for crawls and defect reports. They do **not** own fork code. Code changes land here via this repo’s Grok Bot (jev-ultrafast).

## OpenRouter Decisions (default path)

- Endpoint: `POST https://openrouter.ai/api/alpha/decisions` — the primary and
  default decision path for the agent loop
- Auth: `OPENROUTER_API_KEY` (server-side / env; never commit keys). The main
  agent still requires no `TYPESAFE_API_KEY`.
- Model: `OPENROUTER_MODEL` defaults to `typesafe/jev-1.13`. That value is an
  **OpenRouter model slug** in the Decisions body, not a TypeSafe-account or
  System One backend switch.
- **No TypeSafe key required for the agent.** Decisions via OpenRouter stays
  the supported default.

### QA harness amendment (JUF-0003, owner-directed 2026-09-29)

Issue #9 authorizes, for the `jev-qa` frontend QA package only, optional
decision arms beyond OpenRouter: local Laya (`http://127.0.0.1:8791/v1/systemone`,
no auth — the default exploration runner), TypeSafe, and OpenCode transports.
Boundaries of the amendment: the main `Agent` loop and `jev` inspector keep
OpenRouter Decisions as the default and require no extra keys; TypeSafe and
OpenCode endpoints come from operator-set env (`TYPESAFE_SYSTEMONE_URL`,
`OPENCODE_BASE_URL`) with no key committed and fail closed when unconfigured;
runner selection is provider selection, so a Laya run never reads decision
credentials; provider keys entered through the CLI live only in the ignored
package `.env` and are subject to the 3-hour idle cleanup. Nothing here changes
the Study-os crawl default or the model output boundary (never selectors or
executable code).

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
3. Prefer OpenRouter Decisions; the agent never requires a TypeSafe key. The
   QA harness arms are scoped by the amendment above.
4. Never print secrets or API keys.
