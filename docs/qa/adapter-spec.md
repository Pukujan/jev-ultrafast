# Frontend QA harness: adapter contract (JUF-0003)

`jev-qa --url https://www.design-bakery.com` with nothing else typed should
start a local Laya exploration, record what the browser shows, and open a
saved report.html when it finishes. That is the whole product. This document
is the contract every module codes against; issue #9 and its owner comments
own the scope, this file owns the shape.

## The settled rules

Owner corrections on issue #9 (2026-09-29, comments 17:50, 17:51, 17:56,
17:58) override the issue body wherever they differ:

1. URL-only input. The CLI takes a hosted http(s) URL or a localhost URL. It
   never accepts a repository path, never inspects target scripts, never
   starts or stops target services, never runs project commands. The operator
   brings a reachable URL.
2. Laya is the default exploration runner. An omitted or blank runner choice
   selects laya. If the local Laya runtime is missing, the run fails closed
   with a clear reason. It must not fall back to Jev and must not report a
   deterministic-only pass.
3. Runner selection is provider selection. The laya path asks for no keys and
   sends no decision request off the loopback address. Jev is a separate,
   explicitly chosen arm; when chosen without a provider flag, its provider
   defaults to OpenRouter (existing `OPENROUTER_*` wiring). TypeSafe and
   OpenCode are optional arms behind the same transport boundary.
4. Playwright is the evidence stage for the selected exploration, default on,
   independently skippable (`--no-playwright`). It is not the exploration
   itself.
5. Vision is opt-in, default off (`--vision ollama|openrouter`), independent
   of the others. Skipped vision never shows up as a pass. No model download
   is automatic. Remote screenshot review shows provider and model and
   requires an explicit yes before any image leaves the device.
6. Each run writes defects.csv, workflow.mmd, run.json, events.json, an
   evidence folder, and a report.html rendered offline with the bundled
   Mermaid. The report opens in the default browser after artifacts are
   written.

## Module map and ownership

One writer per file while parallel work runs. `main` owns pyproject.toml,
contracts.py, this document, and the vendored renderer.

| Path | Content |
| --- | --- |
| `jev_ultrafast/qa/contracts.py` | Shared types and constants (written; do not edit) |
| `jev_ultrafast/qa/laya.py` | Laya discovery, fail-closed check, LayaTransport, laya_decider |
| `jev_ultrafast/qa/explorer.py` | Guided exploration loop over Browser + Decider, event and finding capture |
| `jev_ultrafast/model.py` | Refactor into a transport seam; default OpenRouter behaviour stays byte-identical |
| `jev_ultrafast/qa/providers.py` | Env discovery, fuzzy name match, confirm-without-value, secure entry, `.env` insert |
| `jev_ultrafast/qa/keywatch.py` | Idle-key watchdog: detached watcher process + `qa-runs/keywatch.json` state (see Keywatch mechanism) |
| `jev_ultrafast/qa/jev_runner.py` | Jev arm transports: openrouter, typesafe, opencode |
| `jev_ultrafast/qa/playwright_stage.py` | Deterministic browser evidence stage |
| `jev_ultrafast/qa/vision_stage.py` | Optional vision stage, local and hosted profiles |
| `jev_ultrafast/qa/artifacts.py` | defects.csv, events.json, workflow.mmd, run.json writers |
| `jev_ultrafast/qa/report.py` | Offline report.html builder + open |
| `jev_ultrafast/qa/cli.py` | `jev-qa` entry: prompts, flags, ordering, exit codes |
| `jev_ultrafast/qa/assets/mermaid.min.js` | Vendored renderer 11.17.2 (do not re-download) |

`tests/conftest.py` does not exist and stays forbidden: each
`tests/test_qa_*.py` is self-contained (own fixtures, tmp_path,
monkeypatch). Parallel writers must not add shared test plumbing.

## Decision transport

`jev_ultrafast/model.py` keeps the exact OpenRouter behaviour (request body,
error strings, env lookup) because `tests/test_agent.py` pins it, and gains a
parameterised seam:

```python
class OpenRouterTransport:          # current behaviour: env URL/key, Bearer auth
    name = "openrouter"
    def prepare(self, body) -> body # unchanged pass-through
    def request(self, body) -> dict # post_json(url, key, body)

def build_request_body(state, goal, history, model_slug=None) -> dict
def parse_result(result, targets, controls, started) -> dict
def choose(state, goal, history, *, transport=None)
def decide(transport, state, goal, history)  # same tail, provider-neutral
```

`choose()` with no transport must behave exactly as today. Two pinned
constraints: the default path resolves `post_json` as a module global at
call time and calls it with exactly three positional args
`(url, key, body)` — no `auth=`/`prepare()` kwargs — so the
`tests/test_agent.py` monkeypatch stand-in `post(_url, _key, body)` keeps
working; and the `"OPENROUTER_API_KEY is required..."` error string stays
byte-identical for existing callers.

Export pin: `model.py` must keep exporting `post_json`, `validate_choice`,
`action_space`, `choose`, `field_context`, `field_text` with unchanged call
signatures — `jev_ultrafast/agent.py:8` imports four of those names at module
import time and `tests/test_agent.py` monkeypatches `model.post_json` and
`loop.field_text`; any rename or move breaks the suite at import.

### Laya dialect

Source of truth: `/tmp/laya-browser-agent` @ main (2026-09-29), `localdecide/serve.py`
and `localdecide/page.py`.

- `POST {base}/v1/systemone` accepts the body `choose()` already builds:
  `{"model", "state", "questions"}`. It answers
  `{"answers", "model", "usage", "latency_ms", "backend"}` where each answer
  is `{choice, probabilities, confidence}`, the same shape
  `validate_choice()` enforces.
- No auth header. Laya binds 127.0.0.1 and needs no keys.
- Criteria flattening is the documented choice. Laya's own question builder
  emits compact string criteria (`{index: element.describe()}`, page.py:76:
  `[3] Where to? (combobox) = ''`), and its prompt consumes the criteria
  values directly; `choose()` emits dict criteria for target questions.
  `LayaTransport.prepare()` rewrites every dict criterion to the
  describe-style line (`[idx] label (role) = 'value' checked=true ...`) and
  passes flat string criteria through unchanged. Keys are preserved, so
  response validation and target→action mapping are untouched.
  Measured 2026-09-29 on the live laya-mlx checkpoint (localdecide @ main,
  three alternating warm trials): dict-form and flattened bodies both pass
  `validate_choice` with the identical pick (CLICK, target 1), so dict
  criteria are NOT known to confuse the runtime; flattening stays for
  prompt-format parity with Laya's own builder. Warm latencies 233–240 ms
  (flattened) vs 254–266 ms (dict) are a small, not-fully-attributed
  difference on one state, not a benchmark claim. The first-call gap
  (1288 vs 307 ms) was cold model load and is not attributable.
  `prepare()` is a pure function pinned by unit-test goldens; run.json
  provenance records `laya_criteria_flattening: "describe-v1"`.

Discovery and fail-closed (`laya.py`):

1. Read `LAYA_BASE_URL` (default `http://127.0.0.1:8791`).
2. `GET {base}/healthz`; require 200 and `{"ok": true}`; capture `backend`,
   `max_options_per_question` into run provenance. Optionally cross-check
   `GET {base}/v1/models`.
3. Anything else raises `LayaUnavailable` with the documented start
   command (`git clone https://github.com/ChenneyZhuang/laya-browser-agent
   && pip install -e '.[mlx]' && localdecide serve`) and stops before any
   browser work.

### Jev arm transports

`providers.py` scans only the jev package's own ignored `.env` (plus process
env) for `PROVIDER_ENV_ALIASES` names, using exact match first, then
`difflib` similarity over names and prefixes. It confirms a candidate by
variable name, never value; secure entry uses `getpass`; a typed key may be
written into the package `.env` and is then the only key the watchdog can
remove. Pre-existing values are never touched.

Endpoint evidence, honest state: the openrouter transport reuses the exact
OpenRouter Decisions wiring. For typesafe/opencode we do not invent URLs.
The transport takes its endpoint from env (`TYPESAFE_SYSTEMONE_URL`,
`OPENCODE_BASE_URL`); when unset the arm fails closed with a message naming
the missing variable. Upstream history mentions a TypeSafe System One path
only as prose; nothing verifiable was found in this fork's code.

### Keywatch mechanism

Acceptance 5 needs removal to survive the CLI exiting, so an in-process
thread is out. The mechanism is a detached child plus a state file:

- `providers.py` inserts a CLI-typed key as one exact line in the package
  `.env` and records in `qa-runs/keywatch.json`: variable name, sha256 of
  the inserted `NAME=value` content (newline style excluded, so a Windows
  editor re-saving the file with CRLF does not orphan the cleanup),
  inserted_at, last_used (refreshed by every run that authenticates with
  that value), `opted_out` (answer to the 3-hour question; default false =
  cleanup on), pid of the watcher.
- At run end (only when a key was newly inserted and cleanup was not
  declined), the CLI spawns the watcher with `[sys.executable, "-m",
  "jev_ultrafast.qa.keywatch", "--state", <abs state path>]` — never a
  bare `python`, which can resolve outside the uv venv and die instantly,
  and never a relative state path, which breaks once the child's cwd
  differs — via `subprocess.Popen(..., start_new_session=True,
  stdin/stdout/stderr=DEVNULL)`. The watcher loop sleeps, and when
  `now - last_used >= IDLE_KEY_TTL_SECONDS` with `opted_out` false it
  performs the guarded delete and exits.
- Guarded delete: re-read the `.env` line for that variable; remove it only
  when its content still hashes to the recorded value. If the operator
  retyped the variable (their own credential), the digest differs and the
  watcher leaves it alone and records `skipped_changed`. Name alone is
  never grounds for deletion.
- Lock: the watcher and every CLI start acquire an exclusive lock on
  `keywatch.json` (`os.O_CREAT|os.O_EXCL` lockfile with pid + staleness
  takeover after 60s). On start, the CLI first reconciles: expired inserts
  are removed with the same guard, a missing/dead watcher is respawned, a
  live one is not duplicated. Liveness asks the OS: `os.kill(pid, 0)` on
  POSIX; on Windows, `OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION)` plus
  `GetExitCodeProcess == STILL_ACTIVE`, because signal 0 raises WinError 87
  for every pid there and would misread a live watcher as unreadable.
- The state file lives under the ignored `qa-runs/` root and is never
  copied into a run folder, receipt, or the target project.
- Fake-clock unit tests cover: expiry deletes exact-line only, use
  refreshes, opt-out never deletes, restart without watcher respawns and
  recovers schedule, retyped key is preserved (`skipped_changed`), lock
  prevents double spawn.

## Explorer loop (`explorer.py`)

Reuse `jev_ultrafast.browser.Browser` (CDP via browser-harness) and
`jev_ultrafast.model.action_space` exactly as the agent loop does:
observe → index elements → one decide call → execute the chosen observed
target → log execution → re-observe. Model output can only name an
operation plus an index that came from the snapshot; selectors, coordinates,
and scripts stay out of bounds (AGENTS.md rule, unchanged).

Differences from `agent.py`: the decider is injected (laya or a Jev-arm
transport), every step appends a `PageEvent`, and the loop watches for
frontend faults while it explores:

- dead control: a CLICK executed but the page fingerprint is unchanged on
  two consecutive observations → `finding(kind=dead_control)`
- broken link: navigation landed on an error page (status or error text) →
  `finding(kind=broken_link)` when the Playwright stage corroborates the
  HTTP status; explorer-only cases stay candidate
- browser error: snapshot/prompt surface reports an error state → candidate
- budget: `DEFAULT_MAX_STEPS` from contracts caps the walk; the chart marks
  the last executed step failing only when a finding cites it

The explorer never re-reports the same (kind, url, action) twice.

## Playwright stage (`playwright_stage.py`)

Default on, skippable, purely deterministic. Given the run's visited URL
list and final page:

- navigate with a fixed viewport (1280×720 default, recorded); capture
  Navigation Timing (`loadEventEnd - navigationStart`), console messages,
  page errors
- probe every `<a href>` on visited pages once, with a GET through the
  Playwright request context (shared UA/cookies), never a bare HEAD:
  HEAD answers 405/403/429 from CDNs and bot walls on working links.
  `confirmed` broken_link requires 404/410 or a browser-visible error
  page in the navigated response; 401/403/405/429 and bot-challenge
  bodies are recorded `candidate` with the status as evidence;
  network-level failures (DNS/refused) are confirmed
- layout scan in-page: elements whose box overflows the viewport or whose
  scrollWidth exceeds clientWidth beyond a 1px tolerance → `layout` findings
  with bbox evidence
- screenshot each visited page to evidence with speakable names
  (`step 07 landing page.png`, legend below); record screenshot call time
  separately from navigation time
- tracing: when enabled record `tracing_mode` in provenance; timings stay
  comparable only within one mode

Browser binaries may be missing (`playwright install` not run). The stage
then writes a failed-setup status into run.json, adds no findings, and the
run still completes with explorer evidence. Never pretend the stage ran.
A fatal mid-sweep fault — a browser exists but the sweep raises — writes
`failed` with the error text in provenance instead, so a code bug is never
reported as an environment problem the operator could reinstall away.

## Vision stage (`vision_stage.py`)

Opt-in, default off, suggestions only.

- Credentials are separate by variable, never by reuse: hosted vision reads
  `VISION_API_KEY` / `VISION_BASE_URL` / `VISION_MODEL` and does not fall
  back to `OPENROUTER_API_KEY`. The vision names sit in the `vision` row of
  `PROVIDER_ENV_ALIASES`; a key typed for vision is inserted like any Jev
  key, enters the keywatch ledger, and gets the same 3-hour idle cleanup.
  No vision variable name, value, or hash appears in run.json, the report,
  or receipts — only the model string does.
- `ollama`: probe `VISION_OLLAMA_URL` (default
  `http://127.0.0.1:11434/api/tags`); offer installed vision-capable
  profiles only. This machine has Ollama 0.34.4 with no vision model
  installed, so the honest path is "no local vision model installed —
  install one (operator choice) or skip". Never pull. Size guard for this
  PC: 2B-class profiles by default; a 4B+ local selection must already be
  installed, never fetched. Local vision sends no screenshots off-device.
- `openrouter`: show provider + model + pricing source, then require an
  explicit yes naming that screenshots will leave the device
  (`--vision-confirm` for non-interactive runs). Without the yes, the stage
  records declined and adds nothing.
- Verdicts from a vision model are `status=candidate, stage=vision`
  findings; the CSV and report mark them uncorroborated. A skipped or
  failed vision stage is recorded as such and is never a pass.

## Artifacts (`artifacts.py`)

- `defects.csv`: columns fixed in `contracts.DEFECT_COLUMNS`;
  `evidence_refs` joined by `;`; one row per finding; deterministic order
  (step, then stage)
- `events.json`: every PageEvent as objects, camel-free snake keys, the
  sole input for the chart
- `workflow.mmd`: `flowchart TD`, one node per event (`S{step}[["7. CLICK
  [12] Sign in — url"]]`), edges in step order, terminal node per outcome;
  the failing event gets `class S7 failing` plus a `classDef failing`
  definition; no LLM touches this file; formatting is stable under reruns
  (pure function of events)
- `run.json`: run_id, started/finished ISO times, target, runner, provider
  or null, model/backend from the decision transport (laya: healthz
  `backend`, model name; never any key), stage table
  {playwright: on | skipped | failed-setup | failed | not-run, vision: off |
  declined | skipped-no-model | ran(N) | not-run}. A stage that never
  recorded a result is not-run, never a claimed on/declined. Then step
  and finding counts by status, run_error text on crash paths, renderer
  provenance (mermaid 11.17.2 sha256 581ed7d7…), tool versions, git sha,
  evidence sha256 index

Crash path: if the run raises mid-flight, the CLI still writes events,
workflow, defects, and run.json (best effort) with `run_error`, then
exits 1 without building or opening report.html. A failed run is a
recorded run, never a silent folder. A browser setup failure obeys the
same rule: when the target never opened, the CLI writes those four
evidence files with a `run_error` naming the open failure, still builds
no report, and keeps exit code 2 so setup problems stay distinct from
mid-run crashes.

## Report (`report.py`)

A saved folder, opened with `webbrowser.open(file://…)`. Self-contained
besides relative files in the same folder: report.py copies
`assets/mermaid.min.js` and `assets/mermaid.INFO.txt` into the run folder
and the HTML loads them plus `workflow.mmd` text and `defects.csv` inline.
Structure: outcome banner (never "pass" on model completion alone), one
section per defect with its reproducible action and evidence thumbnails,
the workflow chart with the failing node highlighted and each failing node
linked to its defect row, a provenance appendix. All prose inside follows
human-sounding writing; visible text is plain sentences, restrained bold.

## CLI surface (`cli.py`)

```
jev-qa [--url URL] [choices…]
```

Order: target URL → runner (blank/omitted = laya) → provider (jev only,
blank = openrouter) → playwright y/n (default y) → vision n/y
(default n; ollama|openrouter + model + confirmation) → then run. Key
discovery/entry happens inside the Jev provider step only. Laya step shows
the runtime check result and fails closed before opening a browser.
Interactive prompts accept bare returns for all defaults. `--yes` skips
prompts and applies flag values. A path-like `--url` (no scheme, or
`file:`) exits with the URL-only rule quoted from issue #9. Exit codes:
0 completed run (defects do not change this), 2 fail-closed setup,
1 internal error.

## Testing rules

Offline only; CI has no browsers, no paid APIs, no Laya runtime.

- transports: monkeypatch the seams like `tests/test_agent.py` (patch
  `post_json`/`Transport.request`); assert laya request body carries
  flattened string criteria and no Authorization header
- fail-closed: no env keys + missing healthz → laya run exits 2 before any
  browser call (a fake Browser records "never opened")
- keywatch: fake clock for expiry/refresh/opt-out/restart recovery; only
  inserted keys removed; pre-existing keys survive
- artifacts: same events → byte-identical workflow.mmd/CSV; failing step
  marked; defect rows carry all twelve columns
- metamorphic: renumbering element indices (consistent relabel) preserves
  the finding set; adding whitespace to page text preserves findings;
  CSV row order deterministic regardless of dict insertion order
- fuzz: generated DOM/control/link fixtures for the link/status and dead
  control detectors; no crashes, findings stay typed
- cli: blank runner = laya; laya path reads no OPENROUTER_API_KEY (test
  runs with the variable absent); jev without provider = openrouter;
  file path rejected

The hidden holdout lives outside this repository. Its fixtures and answers
must not be copied into tests or docs; only a pass/fail receipt belongs on
the issue.

## Filename legend

See `.content-system/filename-legends/frontend-qa.md` / `.json` for the
speakable basename rules and token glossary.

## Live acceptance status

Implementation plus offline tests are what this branch claims. AC6–AC9 live
runs (real Laya model, live design-bakery/Study OS targets, vision bake-off)
stay open on issue #9 until their runtimes exist; the run.json stage table
and receipts are the mechanism, not a claim of completion.
