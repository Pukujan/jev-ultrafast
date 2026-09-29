# Filename legend: frontend QA runs

Feature: `jev_ultrafast/qa` (JUF-0003). The harness writes one folder per
run under `qa-runs/` (git-ignored). Contract filenames come from issue #9
and stay fixed. Generated media basenames follow the rules below.

## Glossary

| Token | Meaning |
| --- | --- |
| `qa-runs/<date> <host> <purpose>/` | One folder per run: ISO date, URL host, short purpose phrase, e.g. `2026-09-29 www.design-bakery.com first pass/` |
| `defects.csv` | Fixed contract name: one row per finding |
| `workflow.mmd` | Fixed contract name: Mermaid chart generated from events.json |
| `run.json` | Fixed contract name: provenance record |
| `events.json` | Fixed contract name: raw page event trace |
| `report.html` | Fixed contract name: saved offline report |
| `mermaid.min.js` | Bundled renderer copy (version and sha256 in run.json) |
| `evidence/` | Screenshot and metric folder inside the run folder |
| `step <NN> <what>.png` | Speakable screenshot: zero-padded step and plain phrase, e.g. `step 07 landing page.png` |
| `step-<NN>--<what>.png` | Safe twin for tools that cannot store spaces or dashes, e.g. `step-07--landing-page.png` |
| `link <NN> <host>.json` | Per-link status probe record for visited pages |

Never used: hash or hex stems as the discriminator, `key=value` robot stems.
A content hash may appear only as a separate field inside run.json's
evidence index.

## Associated paths

- `qa-runs/<run folder>/defects.csv`
- `qa-runs/<run folder>/workflow.mmd`
- `qa-runs/<run folder>/run.json`
- `qa-runs/<run folder>/events.json`
- `qa-runs/<run folder>/report.html`
- `qa-runs/<run folder>/mermaid.min.js`
- `qa-runs/<run folder>/evidence/step <NN> <what>.png`
- `qa-runs/<run folder>/evidence/link <NN> <host>.json`
- `qa-runs/keywatch.json` (idle-key watchdog recovery state)

Machine twin: `frontend-qa.json`.
