# Jev Ultrafast

Read README.md before editing. Keep the loop small: page -> indexed elements -> operation + target -> execution.

- The input is one natural-language goal. Do not add site-specific plans or hardcoded field values.
- TypeSafe chooses an operation and operation-specific target heads in one request. Consume only the selected operation's target.
- Targets must map to observed elements and supported operations. Never let the model emit selectors or executable code.
- TYPE_TEXT invokes the text LLM. Cache a stale retry's value only while its entire helper input is identical.
- Never retry a browser mutation. Log execution before observing its result.
- Screenshots are optional; the model does not consume them. Keep demonstration footage at its original speed.
- Keep credentials server-side and .env ignored. Tests must not call paid APIs.
- Verify actual final outcomes independently. A DONE choice is not proof of success.
- Keep examples, README claims, raw evidence, and model-call counts consistent.
- Do not commit or push unless the user requests it.

## Policy

Full rules: [docs/POLICY.md](docs/POLICY.md).

- Adopters (e.g. Study-os) **use** Ultrafast for crawls/defect reports — they do **not** own fork code.
- This repo’s Grok Bot owns OpenRouter Decisions wiring, harness/CDP, artifact schema alignment, and Ultrafast code changes.
- OpenRouter Decisions only (no TypeSafe key): `POST https://openrouter.ai/api/alpha/decisions`, model `typesafe/jev-1.13`.
- Study-os live target: https://study.design-bakery.com (guest). Defect contract: Study-os `docs/PDD_UX_DEFECT_EXPLORATION.md` + `docs/schemas/ux-defect-report.v1.json`.

Checks: uv run ruff check ., uv run pytest, node --check jev_ultrafast/static/app.js, uv build.
