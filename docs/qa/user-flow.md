# Frontend QA harness: user flows (PDD)

Task JUF-0003, issue #9: let operators run frontend QA from one terminal.
This document describes the product from the operator's chair. The module
contract lives in `docs/qa/adapter-spec.md` (SDD); the test design lives in
`docs/qa/test-plan.md` (TDD). Where the issue body and the owner corrections
of 2026-09-29 differ, the corrections win, and this document follows them.

## The story in one breath

Open a terminal. Hand the tool a URL that already answers. Press return at
every question you don't care about. The harness selects Laya, turns the
Playwright evidence stage on, leaves vision off, walks the site, and writes
five contract files into a `qa-runs` folder. The report opens in the default
browser and works with the network cable unplugged. If the Laya runtime is
missing, the run stops before any browser opens and prints the exact commands
that start it.

## What the operator brings

- One reachable URL: a hosted http(s) address such as
  `https://www.design-bakery.com`, or a localhost address for a stack the
  operator started themselves.
- For the Jev arm only: a provider key, when discovery finds none.
- For hosted vision only: an explicit yes before any screenshot leaves the
  device.

The harness brings the rest: prompts, runtime checks, evidence capture,
artifacts, and the offline report.

## The CLI surface

The entry point and its flags, exactly as the SDD defines them:

```
jev-qa [--url URL] [choices…]
```

Prompt order, with the value a bare return selects:

| Order | Prompt | Bare return selects |
| --- | --- | --- |
| 1 | Target URL | required: hosted http(s) or localhost URL |
| 2 | Runner | laya |
| 3 | Provider (Jev only) | openrouter |
| 4 | Playwright evidence (y/n) | y |
| 5 | Vision (n/y, then profile, model, confirmation) | n |

Named flags: `--url URL`, `--no-playwright`, `--vision ollama|openrouter`,
`--vision-confirm`, `--yes`. `--yes` skips prompts and applies flag values.
Every interactive prompt accepts a bare return for its default.

Exit codes: 0 the run completed (defects do not change this), 2 fail-closed
setup, 1 internal error.

## Flow 1. First run, every choice blank

1. Open a terminal where `jev-qa` is installed.
2. Run `jev-qa --url https://www.design-bakery.com` (or run `jev-qa` and
   type the URL at the first prompt).
3. Bare return at the runner prompt. Laya is selected. Runner selection is
   provider selection: the laya path reads no keys and sends no decision
   request off the loopback address.
4. Bare return at the Playwright prompt. The evidence stage is on.
5. Bare return at the vision prompt. Vision stays off. A skipped vision stage
   is recorded as skipped and never counts as a pass.
6. The harness checks the Laya runtime with `GET /healthz` against
   `http://127.0.0.1:8791` (or `LAYA_BASE_URL` when set), expects 200 and
   `{"ok": true}`, and prints the check result.
7. Exploration walks the site for at most 60 steps: observe, index elements,
   one decide call, execute the chosen observed target, log, re-observe. The
   model can name an operation and an index from the snapshot. Selectors,
   coordinates, and scripts stay out of bounds.
8. The Playwright stage revisits the pages: navigation timing, console
   messages, page errors, one GET probe per link, a layout scan, and
   screenshots into the evidence folder.
9. Artifacts are written and `report.html` opens in the default browser.

Success outcome. Exit code 0. The run folder
`qa-runs/<date> <host> <purpose>/` contains `defects.csv`, `workflow.mmd`,
`run.json`, `events.json`, `report.html`, the evidence folder, and the
bundled Mermaid renderer. The report renders offline. The outcome banner says
what the run found; model completion alone is never reported as a pass.

Failure outcome. An internal crash exits 1 with the error. A setup refusal
exits 2 before browser work. Defects found during the walk do not change the
exit code.

## Flow 2. Laya runtime missing: fail closed

1. Same start as flow 1: URL given, every choice blank.
2. The healthz check fails: nothing listens on 127.0.0.1:8791, the answer is
   not 200, or `ok` is not true.
3. The harness raises `LayaUnavailable` and stops before any browser opens.

Success outcome for this guard. The message names the reason and the
documented start commands:

```
git clone https://github.com/ChenneyZhuang/laya-browser-agent && pip install -e '.[mlx]' && localdecide serve
```

Exit code 2. No run folder claims completion. The operator knows exactly what
to start and can rerun once `localdecide serve` answers.

Failure outcome this flow forbids. No fallback to Jev. No deterministic-only
pass. Silence is not an option: the refusal is the product behaviour.

## Flow 3. Jev comparison arm, OpenRouter default

1. Choose `jev` at the runner prompt.
2. Bare return at the provider prompt. OpenRouter is selected, on the
   existing `OPENROUTER_*` wiring.
3. Key discovery scans the process environment and the jev package's ignored
   `.env` for supported variable names: exact match first, then fuzzy name
   match. A candidate is confirmed by variable name only; the value is never
   displayed. Secure entry uses `getpass`. A typed key may be written into
   the package `.env`.
4. The harness asks whether to remove that directly entered key after three
   hours of inactivity. The default answer is yes. Removal is guarded: only
   the exact line this run inserted, verified by hash, is ever deleted.
5. The run proceeds like flow 1 from step 7, with the Jev transport answering
   the decide calls.

Success outcome. Exit code 0. `run.json` records runner `jev`, provider
`openrouter`, and the model string. No key value, variable name, or hash
appears in `run.json`, the report, or any receipt.

Failure outcome. TypeSafe or OpenCode chosen with its endpoint variable unset
(`TYPESAFE_SYSTEMONE_URL` or `OPENCODE_BASE_URL`) exits 2 with a message
naming the missing variable. A missing OpenRouter key stops the arm before
any decision request.

## Flow 4. Skip Playwright

1. Run with `--no-playwright`, or answer `n` at the Playwright prompt.
2. Exploration runs and records its own evidence.

Outcome. The stage table in `run.json` records `playwright: skipped`. The run
completes, the report opens, and link findings stay `candidate` without HTTP
corroboration. Skipping Playwright is a supported choice, recorded honestly.

## Flow 5. Playwright selected, browser binaries missing

1. Playwright is on, but `playwright install` was never run on this machine.
2. The stage cannot launch a browser.

Outcome. The stage writes `failed-setup` into the `run.json` stage table, adds
no findings, and never pretends it ran. The run completes on explorer
evidence alone. Exit code 0. If a browser launches but the sweep itself dies,
the stage records `failed` with the error text instead, so a code fault is
never mislabeled as a missing install.

## Flow 6. Local vision through Ollama

1. Answer `y` at the vision prompt and choose `ollama`.
2. The harness probes `VISION_OLLAMA_URL` (default
   `http://127.0.0.1:11434/api/tags`) and lists installed vision-capable
   profiles only. No model download is automatic. This machine has Ollama
   0.34.4 with no vision model installed, so the honest path is: no local
   vision model installed; install one, operator's choice, or skip.
3. Local vision never sends screenshots off the device.

Success outcome. With a profile installed and chosen, vision verdicts land as
`candidate` findings with `stage=vision`, marked uncorroborated in the CSV
and the report.

Failure outcome. A skipped or failed vision stage is recorded as such. It is
never a pass.

## Flow 7. Hosted vision through OpenRouter

1. Answer `y` at the vision prompt and choose `openrouter`.
2. The harness shows the provider, the model, and the pricing source.
3. It requires an explicit yes naming that screenshots will leave the device.
   Non-interactive runs supply `--vision-confirm`.

Success outcome. After the yes, screenshots go to the named provider and
model; verdicts are `candidate` findings, never confirmed by vision alone.

Failure outcome. Without the yes, the stage records `declined` and adds
nothing. Vision credentials live in separate variables (`VISION_API_KEY`,
`VISION_BASE_URL`, `VISION_MODEL`) and never fall back to
`OPENROUTER_API_KEY`.

## Flow 8. Path-like targets are refused

1. Run `jev-qa --url ./my-app`, or pass a `file:` URL.
2. The harness rejects the input.

Outcome. Exit code 2 with the URL-only rule from issue #9 quoted. The tool
takes a hosted http(s) URL or a localhost URL. It accepts no repository path,
inspects no target scripts, starts and stops no target services, and runs no
project commands.

## Flow 9. Non-interactive run

1. Run `jev-qa --url https://www.design-bakery.com --yes --no-playwright`.
2. Prompts are skipped; flag values apply.

Outcome. Same artifacts, same exit codes, no interaction. The stage table
records every choice exactly as applied.

## Where the output lands

One folder per run under the ignored `qa-runs/` root, named with the ISO
date, the URL host, and a short purpose phrase, for example
`qa-runs/2026-09-29 www.design-bakery.com first pass/`.

| File | Content |
| --- | --- |
| `defects.csv` | One row per finding; the twelve fixed columns; `evidence_refs` joined by `;`; rows ordered by step, then stage |
| `events.json` | Every page event with snake-case keys; the chart's sole input |
| `workflow.mmd` | `flowchart TD` built from events; the failing step carries the `failing` class; no LLM touches this file |
| `run.json` | run id, ISO start/finish, target, runner, provider or null, model/backend, stage table (`playwright: on\|skipped\|failed-setup\|failed`, `vision: off\|declined\|ran`), step and finding counts, renderer provenance (`mermaid 11.17.2` with sha256), tool versions, git sha, evidence sha256 index |
| `report.html` | Saved offline report; opens via the default browser; outcome banner, one section per defect with its reproducible action and evidence thumbnails, the workflow chart with failing nodes linked to their defect rows, provenance appendix |
| `mermaid.min.js`, `mermaid.INFO.txt` | Bundled renderer copies so the report opens with no network |
| `evidence/` | Screenshots with speakable names (`step 07 landing page.png`) and per-link probe records (`link 03 www.design-bakery.com.json`) |

`qa-runs/keywatch.json` holds the idle-key watchdog ledger at the `qa-runs/`
root. It is never copied into a run folder, a receipt, or the target project.

## State boundaries

The harness never crosses these lines:

- Target input is a URL only. The owner correction of 2026-09-29 17:50
  supersedes the repository-path and service-startup wording in acceptance
  criteria 1 and 2 of issue #9. The operator starts their own local services
  and supplies the already-reachable URL.
- No target script inspection, no service start or stop, no project commands.
- Model output names an operation and an observed index only. Selectors,
  coordinates, executable code, and shell commands stay out of bounds, per
  the indexed-action safety rule in AGENTS.md.
- Private Study OS state stays out: no raw transcripts, credentials, cookies,
  or hidden holdout answers enter this public repository. Live findings are
  redacted and provenance-linked.
- Screenshots leave the device only after the explicit yes of flow 7, with
  provider and model named in the question.
- A missing Laya runtime refuses. A skipped vision stage never counts as a
  pass. A finished run reports what it observed.

## Honest outcomes

Exit code 0 means the run completed. It makes no claim about defect counts.
The report banner never says "pass" on model completion alone. A skipped or
failed stage is recorded with its real status in `run.json`. The live runs for
acceptance criteria 6 through 9 (real Laya model, live Design Bakery and
Study OS targets, the vision bake-off) stay open on issue #9 until their
runtimes exist; the run.json stage table and receipts are the mechanism, and
this document makes no completion claim for them.
