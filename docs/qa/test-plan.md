# Frontend QA harness: test plan (TDD)

Task JUF-0003, issue #9. This is the deterministic test design for the
frontend QA harness. The module contract it tests against lives in
`docs/qa/adapter-spec.md` (SDD); the operator story lives in
`docs/qa/user-flow.md` (PDD).

Ground rules, taken from the SDD testing rules:

- Offline only. CI has no browsers, no paid APIs, no Laya runtime.
- `tests/conftest.py` does not exist and stays forbidden. Every
  `tests/test_qa_*.py` is self-contained: own fixtures, `tmp_path`,
  `monkeypatch`. No shared test plumbing.
- The monkeypatch pattern follows `tests/test_agent.py`. The stand-in for
  `post_json` is `post(_url, _key, body)` with exactly three positional
  arguments, and on the default OpenRouter path `post_json` must resolve as
  a module global at call time. Patching `Transport.request` is the seam for
  provider-neutral tests.

Planned files: `tests/test_qa_transport.py`, `tests/test_qa_laya.py`,
`tests/test_qa_keywatch.py`, `tests/test_qa_providers.py`,
`tests/test_qa_artifacts.py`, `tests/test_qa_cli.py`,
`tests/test_qa_metamorphic.py`, `tests/test_qa_fuzz.py`. The hidden holdout
lives outside the repository and has no test file (see its own section).

## Unit tests

### Transport seam — `tests/test_qa_transport.py`

| Case | Setup | Expectation | AC |
| --- | --- | --- | --- |
| Default path unchanged | Monkeypatch `jev_ultrafast.model.post_json`; call `choose()` with no transport | Request body, env lookup, and error behaviour match today; the string `OPENROUTER_API_KEY is required for Decisions; nothing executed.` stays byte-identical; `post_json` is called with exactly `(url, key, body)` | AC3, AC11 |
| describe-v1 flattening golden | Request body whose target questions carry dict criteria; call `LayaTransport.prepare(body)` | Every dict criterion becomes the describe-style line `[idx] label (role) = 'value' checked=true ...` (shape of Laya's own `[3] Where to? (combobox) = ''`); flat string criteria of the operation question pass through unchanged; question keys preserved | AC3, AC8 |
| Laya request shape | Capture the prepared body sent to `POST {base}/v1/systemone` | Body carries `{"model", "state", "questions"}` with flattened string criteria; no Authorization header | AC3 |
| Laya answer validation | Fake transport returns `{"answers", "model", "usage", "latency_ms", "backend"}`; each answer `{choice, probabilities, confidence}` | `parse_result` accepts the shape `validate_choice()` enforces and maps target answers back to observed actions | AC3 |
| Provider-neutral tail | Fake `Transport` objects for each arm | `decide()` behaves identically per transport; the tail holds no provider-specific branch | AC3 |

Provenance check: `run.json` records `laya_criteria_flattening: "describe-v1"`
rather than duplicated request bodies.

### Fail-closed Laya — `tests/test_qa_laya.py`

| Case | Setup | Expectation | AC |
| --- | --- | --- | --- |
| Missing runtime | No `LAYA_BASE_URL` listener; `OPENROUTER_API_KEY` absent from the environment; fake `Browser` installed | The laya run exits 2 before any browser call; the fake Browser records it was never opened; no Jev fallback is attempted; no deterministic-only pass is reported | AC1, AC3 |
| Bad healthz | Endpoint answers 404, or 200 with `ok` false | `LayaUnavailable` raised; message carries the documented start commands (`git clone https://github.com/ChenneyZhuang/laya-browser-agent && pip install -e '.[mlx]' && localdecide serve`) | AC3 |
| Discovery provenance | Healthy answer with `backend` and `max_options_per_question` | Both fields land in run provenance; no key material alongside them | AC3 |
| Laya reads no keys | Run the full laya path with every `OPENROUTER_*` and `VISION_*` variable deleted | The run succeeds with the fake transport; no env lookup touches provider variables | AC3 |

### Keywatch fake-clock matrix — `tests/test_qa_keywatch.py`

The clock is injected. The state file lives in a `tmp_path` `qa-runs/`. The
inserted key is one exact line in a fake package `.env`.

| Case | Steps | Expectation | AC |
| --- | --- | --- | --- |
| Expiry | Insert key line; advance the fake clock past `IDLE_KEY_TTL_SECONDS` (3 h) with no use | Guarded delete re-reads the line, verifies the recorded sha256, and removes exactly that line; pre-existing variables in the same file survive | AC5 |
| Refresh | Advance 2 h; record a use; advance 2 h more | `last_used` is refreshed; the key survives the original deadline | AC5 |
| Opt-out | Set `opted_out` true; advance far past the TTL | The key is never deleted | AC5 |
| Restart recovery | Delete the watcher process record; start the CLI reconciliation | A missing or dead watcher is respawned with `[sys.executable, "-m", "jev_ultrafast.qa.keywatch", "--state", <abs path>]`; the schedule is recovered from state; a live watcher is not duplicated | AC5 |
| Retyped key | Replace the variable's value with the operator's own key; advance past the TTL | The hash differs from the ledger; the watcher records `skipped_changed` and leaves the line alone | AC5 |
| Lock | Race two CLI starts against one state file | The `O_CREAT\|O_EXCL` lockfile with pid allows one watcher; stale locks are taken over after 60 s; no double spawn | AC5 |

Every case also asserts that the state file stays under the ignored
`qa-runs/` root and is never copied into a run folder, receipt, or target
project.

### Provider discovery — `tests/test_qa_providers.py`

| Case | Setup | Expectation | AC |
| --- | --- | --- | --- |
| Exact alias wins | `.env` with an exact `PROVIDER_ENV_ALIASES` name | Discovery returns that variable first | AC4 |
| Fuzzy name match | Misspelled or prefixed variable names | `difflib` similarity over names and prefixes ranks the candidate; matching never reads key values | AC4 |
| Confirm without value | A discovered candidate | The confirmation prompt names the variable only; no part of the value is displayed or logged | AC4 |
| Secure entry | Typed key via `getpass` | The key is inserted as one exact line in the package `.env` and recorded in the keywatch ledger; pre-existing values are untouched | AC4, AC5 |
| Scope of the scan | Decoy `.env` files outside the jev package | Only the process environment and the jev package's own ignored `.env` are scanned | AC4 |

### Artifacts — `tests/test_qa_artifacts.py`

| Case | Setup | Expectation | AC |
| --- | --- | --- | --- |
| Byte identity | Write `workflow.mmd` and `defects.csv` twice from the same event and finding lists | Second bytes equal first bytes | AC7 |
| Failing step marked | One event with `failing=True` | The node line follows `S{step}[["7. CLICK [12] Sign in — url"]]`; the file carries `class S{step} failing` and the `classDef failing` definition; edges stay in step order | AC6, AC7 |
| Twelve columns | Any finding written to CSV | The row carries every `DEFECT_COLUMNS` entry; `evidence_refs` joined by `;` | AC6, AC7 |
| Deterministic order | Findings inserted in shuffled order | Rows sort by step, then stage, every run | AC7 |
| Secret whitelist | Render `run.json` and the report HTML from a run that used fake credentials | Only whitelisted fields appear (model/backend strings, stage table, counts, evidence hashes); no credential variable name, value, or sha256 of a key line appears anywhere | AC4, AC5, AC10 |

### CLI rules — `tests/test_qa_cli.py`

| Case | Setup | Expectation | AC |
| --- | --- | --- | --- |
| Blank runner | Bare return at the runner prompt | Runner resolves to `laya` | AC1, AC3 |
| Laya needs no OpenRouter | Full laya run with `OPENROUTER_API_KEY` deleted from the environment | The run proceeds; no prompt and no lookup asks for it | AC3 |
| Jev default provider | Runner `jev`, bare return at the provider prompt | Provider resolves to `openrouter` | AC1, AC3 |
| Path-like target | `--url ./my-app` and `--url file:///tmp/x` | Exit 2 with the URL-only rule from issue #9 quoted; no browser work starts | AC1, AC2 (as amended) |
| Non-interactive | `--yes` with flags | Prompts are skipped; flag values apply; stage table records them | AC1 |

## Metamorphic relations — `tests/test_qa_metamorphic.py`

Each relation has a generator, a transform, and an oracle, and each keeps the
finding set as the compared object.

| Relation | Transform | Oracle | AC |
| --- | --- | --- | --- |
| Index renumbering | Apply one consistent permutation to element indices across the page snapshot and every event that cites a target | The finding set is preserved: same kinds, same counts, same urls, actions relabelled consistently | AC8 |
| Label whitespace | Add leading, trailing, and doubled spaces to labels and page text | Findings are preserved, so the CSV rows survive; normalized comparison shows no added or dropped rows | AC8 |
| Dict insertion order | Rebuild event and finding dicts with shuffled insertion order | `defects.csv` stays byte-identical; row order comes from (step, stage), never from dict order | AC7, AC8 |

## Fuzzer — `tests/test_qa_fuzz.py`

Design. A seeded generator builds page snapshots and event streams with
varied DOM: anchors whose probes return sampled statuses (200, 301, 401, 403,
404, 405, 410, 429, 500, DNS failure, bot-challenge bodies), clickable
controls whose page fingerprint changes or stays identical after CLICK, boxes
with random geometry around the 1280×720 viewport and its 1 px tolerance, and
console messages of every captured type. The generated inputs run through the
link/status detector and the dead-control detector. Seeds are pinned, so a
failure is reproducible.

Invariants, asserted on every generated case:

| Invariant | Meaning | AC |
| --- | --- | --- |
| Typed findings only | Every finding has `kind` in `FINDING_KINDS`, `status` in `FINDING_STATUSES`, `severity` in `SEVERITIES` | AC6, AC8 |
| No crash | No detector raises on any generated DOM, control, or link variation | AC8 |
| Dedupe holds | The explorer never reports the same (kind, url, action) twice | AC6, AC8 |
| Status policy | 404/410 and network-level failures are `confirmed`; 401/403/405/429 and bot-challenge bodies stay `candidate` with the status as evidence; layout findings exist only beyond the 1 px tolerance and carry bbox evidence | AC6 |
| Action hygiene | No selector, coordinate, or script text appears in any event or finding; actions name an operation and an observed index only | AC6, AC10 |

## Hidden holdout

Authorship. A separate worker, who has access to issue #9 and
`docs/qa/adapter-spec.md` only, writes the holdout. That worker does not read
the implementation. The implementation worker does not read the holdout.

Location. The holdout lives outside the repository tree in `qa-holdout/`,
which `.gitignore` already excludes. Fixture files and graded answers are
never committed, never copied into tests or docs. The only artifact that
returns to the repository is a pass/fail receipt posted on issue #9.

Fixture recipe (design only; the built pages stay in `qa-holdout/`). A small
static site served from localhost, with injected known defects:

| Injected defect | Expected finding kind | Minimum count | Corroboration the run must show |
| --- | --- | --- | --- |
| A real 404 link | `broken_link` | 1 | Playwright GET probe returns 404, so the finding is `confirmed` |
| A dead button handler | `dead_control` | 1 | Fingerprint unchanged on two consecutive observations after the CLICK |
| Clipped or overlapping layout | `layout` | 1 | bbox evidence for a box outside the viewport or beyond the 1 px tolerance |
| A console error | `browser_error` | 1 | The console/page error is captured in stage evidence |
| A clean control page | none | 0 findings | False-positive guard: the harness reports nothing invented |

Grading and receipt. The packaged harness runs its default path (laya,
Playwright on, vision off) against the holdout's localhost URL. The receipt
records pass/fail, the run folder name, and per-kind counts. It carries no
fixture content and no graded answers. Grading needs a real Laya runtime and
browser binaries, so it shares the AC9 status below: PENDING RUNTIME.

## Acceptance-criterion map

| AC (issue #9) | Offline coverage | Live status |
| --- | --- | --- |
| 1. Terminal entry point, runner choice | CLI rules table; prompt defaults; `--yes` | Blind operator walkthrough: PENDING RUNTIME |
| 2. Amended by owner correction 2026-09-29 17:50 to URL-only | Path-like target refusal test; no service-management code exists to exercise | Superseded scope; no live run applies |
| 3. Laya local interface; no Jev/OpenRouter in Laya mode; tested provider adapters | Transport seam, describe-v1 golden, fail-closed matrix, key-read absence test | Live Laya decision traffic: PENDING RUNTIME |
| 4. Name-only provider discovery, no LLM, credentials in the ignored `.env` | Provider discovery table; secret whitelist | Offline complete |
| 5. Three-hour idle cleanup, default yes, exact-line deletion | Keywatch fake-clock matrix (expiry, refresh, opt-out, restart, retyped key, lock) | Offline complete |
| 6. Broken links, dead controls, browser errors, layout; reproducible findings; model completion is not a pass | Detector units, fuzz invariants, failing-step mark | Checks against live targets: PENDING RUNTIME |
| 7. CSV, event-derived Mermaid, provenance JSON; LLM-free formatter | Artifacts byte identity, twelve columns, deterministic order | Live-run artifact set: PENDING RUNTIME |
| 8. PDD/SDD/TDD; metamorphic; fuzzer; hidden holdout | This document plus `user-flow.md` and `adapter-spec.md`; metamorphic and fuzz suites offline | Holdout grading: PENDING RUNTIME |
| 9. Blind acceptance on Design Bakery and locally hosted Study OS | None offline, by design | PENDING RUNTIME |
| 10. No private Study OS data or holdout answers in this repository | Secret whitelist; holdout location and receipt rules | Redacted live findings: PENDING RUNTIME |
| 11. Gates, unit, metamorphic/fuzz, holdout | Full offline suite plus repository gates | No completion claim from unit tests alone |

## What this branch claims

Implementation and offline tests. The live runs for AC6 through AC9 (real
Laya model, live Design Bakery and Study OS targets, the vision bake-off,
holdout grading) stay open on issue #9 until their runtimes exist. The
run.json stage table and issue receipts are the mechanism for recording them,
and this plan makes no completion claim for them.
