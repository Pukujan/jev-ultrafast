# OpenRouter Decisions for jev-ultrafast

Alex clarified: **no TypeSafe key**. Use the OpenRouter Decisions API with `OPENROUTER_API_KEY` only.

## 1. Endpoint + shape

| Item | Value |
| --- | --- |
| URL | `POST https://openrouter.ai/api/alpha/decisions` |
| Auth | `Authorization: Bearer $OPENROUTER_API_KEY` |
| Model | `typesafe/jev-1.13` (alias `~typesafe/jev-latest` is rolling) |
| Docs | [Jev hub](https://openrouter.ai/docs/guides/community/jev), [Decisions reference](https://openrouter.ai/docs/api/api-reference/alphadecisions/submit-a-decisions-request), [tutorial](https://openrouter.ai/docs/guides/community/jev-tutorial) |

**Not** Chat Completions. Jev returns typed answers (choice / noul / score), not prose.

### Request body

```json
{
  "model": "typesafe/jev-1.13",
  "state": { "page": {}, "elements": [], "recent_actions": [] },
  "questions": {
    "operation": {
      "type": "choice",
      "instructions": { "goal": "...", "rules": "..." },
      "criteria": { "CLICK": "...", "TYPE_TEXT": "...", "DONE": "..." }
    },
    "click_target": {
      "type": "choice",
      "instructions": { "goal": "...", "operation": "CLICK", "rules": [] },
      "criteria": { "1": { "element": "[1] Submit" } }
    }
  }
}
```

Question primitives (same as System One):

- **choice** — `criteria` is a map of option → description; answer has `choice`, `probabilities`, `confidence`
- **noul** — yes/no probability; answer has `noul` in `[0,1]`
- **score** — ordered rubric array; answer has `score`, `probabilities`, `legend`, `confidence`

### Response body (documented / observed)

```json
{
  "id": "gen-dec-...",
  "model": "typesafe/jev-1.13-20260917",
  "provider": "TypeSafe",
  "answers": {
    "operation": {
      "type": "choice",
      "choice": "CLICK",
      "probabilities": { "CLICK": 0.7, "DONE": 0.3 },
      "confidence": 0.55
    }
  },
  "usage": { "input_tokens": 476, "output_tokens": 70, "cost": 0.00002 }
}
```

`jev_ultrafast.model.validate_choice` already expects `choice` / `probabilities` / `confidence` — compatible with Decisions answers.

Alternate OpenRouter surface (not used by this patch): `POST https://openrouter.ai/api/v1/systemone` for TypeSafe SDK drop-in. Prefer Decisions for plain HTTP.

## 2. Minimum patch applied in `model.py`

In `choose()`, replace the hardcoded TypeSafe System One call with Decisions + OpenRouter key:

- Default URL: `https://openrouter.ai/api/alpha/decisions` (`OPENROUTER_DECISIONS_URL` override)
- Key: `OPENROUTER_API_KEY` (falls back to `TYPESAFE_API_KEY` only if somehow present)
- Default model: `typesafe/jev-1.13` (`OPENROUTER_MODEL` or legacy `TYPESAFE_MODEL`)

`field_text()` is unchanged: still uses `TEXT_MODEL_*` OpenAI-compatible chat for TYPE_TEXT only (example already points at OpenRouter chat).

## 3. Env vars

Required for decisions:

```bash
OPENROUTER_API_KEY=          # Alex Desktop OpenRouter key
OPENROUTER_DECISIONS_URL=https://openrouter.ai/api/alpha/decisions   # optional; this is the default
OPENROUTER_MODEL=typesafe/jev-1.13                                   # optional; this is the default
```

Required only when the agent must TYPE_TEXT (fill fields):

```bash
TEXT_MODEL_API_KEY=          # usually the same OpenRouter key
TEXT_MODEL_BASE_URL=https://openrouter.ai/api/v1
TEXT_MODEL=inception/mercury-2.5
TEXT_MODEL_REASONING=none
```

Run:

```bash
uv run --env-file .env python examples/run.py \
  --url https://study.design-bakery.com \
  --goal 'Continue as guest if offered. Explore a DSA or Big-O lesson. Stop when a worked example is visible.'
```

## 4. How the loop uses Decisions (unchanged)

1. **observe** (`browser.py`) — CDP snapshot → actions + page text  
2. **element table** (`model.action_space`) — indexed CLICK / TYPE_TEXT / SELECT targets  
3. **one Decisions POST** (`model.choose`) — operation + speculative target heads  
4. **act** (`agent.py` → `browser.act`) — only selected target; fill may call text helper  
5. **loop** until DONE / BLOCKED / budget  

## 5. Gaps (honest)

- Stock upstream still documents TypeSafe System One; this tree now defaults to OpenRouter Decisions.
- No TypeSafe key on Desktop; classifier already had `OPENROUTER_API_KEY` only.
- `explore_guest.py` under artifacts is Playwright regex clicking — **not** a Jev harness.
- Study-os guest explore via real `Agent(...)` still needs a live run + Browser Harness Chrome attach to prove end-to-end.

Sources: OpenRouter Jev docs + Decisions reference; local `jev_ultrafast/{model,agent,browser,questions}.py`; `jev-classifier` Decisions client contract.

## 6. Study-os live crawl benchmark (2026-09-27)

Recorded guest UX defect crawl against https://study.design-bakery.com using OpenRouter Decisions (`typesafe/jev-1.13`):

- This fork: [docs/benchmarks/study-os-2026-09-27/](./benchmarks/study-os-2026-09-27/) (75 actions, 11 defects; P0 D004 Worked example)
- Study-os durable copy: `docs/benchmarks/ux-defect-jev-ultrafast/2026-09-27/` in Pukujan/Study-os (Refs #126 #147)

Playwright deterministic arm: placeholder for later add.