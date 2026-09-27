# Study OS full guest UX defect crawl

- **Live URL:** https://study.design-bakery.com
- **When (UTC):** 2026-09-27T05:50:30.804972+00:00
- **Duration:** 36.42s
- **Actions:** 75 (cap 140)
- **Decisions:** 103 (OpenRouter Decisions OK: True)
- **Pages visited:** 4
- **Defects:** 11
- **Artifact dir:** `artifacts\study-os-full-crawl\20260927-054810`

## Prior guest explore (folded)

- `artifacts/study-os-guest/20260927-014415`: clicked Try it → fractions play UI; died on screenshot IPC timeout.
- `artifacts/study-os-guest/20260927-014622`: Start → Big O lesson; Explain again; DONE. Decisions×5 with usage.

## Coverage

### Pages
- https://study.design-bakery.com/
- https://study.design-bakery.com/play/3c43a3d4-97c6-4648-ba48-64a38bb2fa3c
- https://study.design-bakery.com/play/62028e19-2ae4-4801-99d9-35e1701a697c
- https://study.design-bakery.com/play/e5ef7961-fa11-4dd3-93c9-037cae09945d

### Phases
- prior: {"status": "ready", "actions": 1, "final_url": "https://study.design-bakery.com/play/62028e19-2ae4-4801-99d9-35e1701a697c", "error": "_IPCResponseTimeout: Page.captureScreenshot timed out after 5s waiting for the daemon", "lesson_ui_appeared": true}
- prior: {"status": "done", "actions": 2, "final_url": "https://study.design-bakery.com/play/3c43a3d4-97c6-4648-ba48-64a38bb2fa3c", "error": null, "lesson_ui_appeared": true}
- **home_and_lanes**: status=ready actions=6 elapsed=3.65s
- **hesi_fractions_lesson**: status=done actions=13 elapsed=7.49s
- **dsa_big_o_lesson**: status=blocked actions=10 elapsed=4.1s
- **sliding_window_and_misc**: status=blocked actions=30 elapsed=12.09s
- **controls_sweep**: status=blocked actions=16 elapsed=6.55s

### Buttons / controls clicked
- 1 Ready
- 1 Why
- Ask the tutor
- Back
- Collapse
- Continue
- Explain again
- Message
- Open Message
- Open Your answer
- Open study assistant
- Rate 1 out of 5
- Read aloud
- Resume
- Save progress
- Send
- Show a worked example
- Start
- Study OS
- Voice input
- Worked example

## Defects

### D004 — P0: Dead/no-op control: Worked example

- **URL:** https://study.design-bakery.com/play/62028e19-2ae4-4801-99d9-35e1701a697c
- **Repro:** On https://study.design-bakery.com/play/62028e19-2ae4-4801-99d9-35e1701a697c, click/activate 'Worked example' and wait ~3s
- **Expected:** Visible change (URL, DOM text, panel, toast) within ~3s
- **Actual:** No URL/text/fingerprint change after action

### D002 — P1: Missing Back/exit control on play surface

- **URL:** https://study.design-bakery.com/play/3c43a3d4-97c6-4648-ba48-64a38bb2fa3c
- **Repro:** Enter lesson player at https://study.design-bakery.com/play/3c43a3d4-97c6-4648-ba48-64a38bb2fa3c and inspect visible actions
- **Expected:** Visible Back/Exit/Home control to leave lesson
- **Actual:** No back/exit/home among 15 actions: ['study os', 'save progress', 'sign out', '1 why', 'explain again', 'worked example', 'your answer', 'open your answer', 'read aloud', 'voice input', 'i’m confused', 'ask the tutor', 'open study assistant', 'scroll down', 'wait for the page to update']

### D005 — P1: Dead/no-op control: Read aloud

- **URL:** https://study.design-bakery.com/play/3c43a3d4-97c6-4648-ba48-64a38bb2fa3c
- **Repro:** On https://study.design-bakery.com/play/3c43a3d4-97c6-4648-ba48-64a38bb2fa3c, click/activate 'Read aloud' and wait ~3s
- **Expected:** Visible change (URL, DOM text, panel, toast) within ~3s
- **Actual:** No URL/text/fingerprint change after action

### D006 — P1: Dead/no-op control: Open Message

- **URL:** https://study.design-bakery.com/play/3c43a3d4-97c6-4648-ba48-64a38bb2fa3c
- **Repro:** On https://study.design-bakery.com/play/3c43a3d4-97c6-4648-ba48-64a38bb2fa3c, click/activate 'Open Message' and wait ~3s
- **Expected:** Visible change (URL, DOM text, panel, toast) within ~3s
- **Actual:** No URL/text/fingerprint change after action

### D007 — P1: Missing Back/exit control on play surface

- **URL:** https://study.design-bakery.com/play/3c43a3d4-97c6-4648-ba48-64a38bb2fa3c
- **Repro:** Enter lesson player at https://study.design-bakery.com/play/3c43a3d4-97c6-4648-ba48-64a38bb2fa3c and inspect visible actions
- **Expected:** Visible Back/Exit/Home control to leave lesson
- **Actual:** No back/exit/home among 16 actions: ['study os', 'save progress', 'sign out', '1 why', 'read aloud', 'voice input', 'collapse', 'show a worked example', 'explain again', 'message', 'open message', 'voice input', 'turn on read aloud', 'open study assistant', 'scroll down', 'wait for the page to update']

### D008 — P1: Dead/no-op control: Voice input

- **URL:** https://study.design-bakery.com/play/e5ef7961-fa11-4dd3-93c9-037cae09945d
- **Repro:** On https://study.design-bakery.com/play/e5ef7961-fa11-4dd3-93c9-037cae09945d, click/activate 'Voice input' and wait ~3s
- **Expected:** Visible change (URL, DOM text, panel, toast) within ~3s
- **Actual:** No URL/text/fingerprint change after action

### D009 — P1: Dead/no-op control: Voice input

- **URL:** https://study.design-bakery.com/play/3c43a3d4-97c6-4648-ba48-64a38bb2fa3c
- **Repro:** On https://study.design-bakery.com/play/3c43a3d4-97c6-4648-ba48-64a38bb2fa3c, click/activate 'Voice input' and wait ~3s
- **Expected:** Visible change (URL, DOM text, panel, toast) within ~3s
- **Actual:** No URL/text/fingerprint change after action

### D010 — P1: Missing Back/exit control on play surface

- **URL:** https://study.design-bakery.com/play/3c43a3d4-97c6-4648-ba48-64a38bb2fa3c
- **Repro:** Enter lesson player at https://study.design-bakery.com/play/3c43a3d4-97c6-4648-ba48-64a38bb2fa3c and inspect visible actions
- **Expected:** Visible Back/Exit/Home control to leave lesson
- **Actual:** No back/exit/home among 22 actions: ['study os', 'save progress', 'sign out', '1 why', 'explain again', 'worked example', 'your answer', 'open your answer', 'read aloud', 'voice input', 'i’m confused', 'ask the tutor', 'collapse', 'show a worked example', 'explain again', 'message', 'open message', 'voice input', 'turn on read aloud', 'open study assistant']

### D011 — P1: Dead/no-op control: Open Your answer

- **URL:** https://study.design-bakery.com/play/3c43a3d4-97c6-4648-ba48-64a38bb2fa3c
- **Repro:** On https://study.design-bakery.com/play/3c43a3d4-97c6-4648-ba48-64a38bb2fa3c, click/activate 'Open Your answer' and wait ~3s
- **Expected:** Visible change (URL, DOM text, panel, toast) within ~3s
- **Actual:** No URL/text/fingerprint change after action

### D001 — P2: Harness screenshot IPC timeout during guest explore

- **URL:** https://study.design-bakery.com/play/62028e19-2ae4-4801-99d9-35e1701a697c
- **Repro:** Run Agent with record_dir/screenshots enabled on Windows
- **Expected:** Screenshots capture without killing the agent loop
- **Actual:** _IPCResponseTimeout: Page.captureScreenshot timed out after 5s waiting for the daemon

### D003 — P2: Possible teach/probe answer co-visibility (spoil risk)

- **URL:** https://study.design-bakery.com/play/62028e19-2ae4-4801-99d9-35e1701a697c
- **Repro:** Open fractions (or similar) probe step with teach controls visible
- **Expected:** Probe should not display the correct answer before submission
- **Actual:** Answer-like fraction text visible alongside probe question

## Known #126 suspects checklist

- **blank play/Resume:** exercised/observed (see actions.jsonl)
- **missing Back/exit:** HIT
- **Explain again / Worked example dead:** HIT
- **speaker/mic no-op:** exercised/observed (see actions.jsonl)
- **teach spoils probe:** HIT
- **arrow overlap:** exercised/observed (see actions.jsonl)
- **review only once:** exercised/observed (see actions.jsonl)
- **chat no ack:** exercised/observed (see actions.jsonl)
- **number-line before probe:** exercised/observed (see actions.jsonl)
- **companion chips:** exercised/observed (see actions.jsonl)

## Blockers / errors

- home_and_lanes: ValueError: Invalid TypeSafe response; no action executed.

## Coverage gaps

- Screenshots optional/skipped (prior IPC timeout on Windows).
- Mic/speaker may require OS permission; no-op may be environmental.
- Chat ack detection is text-diff based; may miss toast-only UI.
- Not all catalog lessons guaranteed if home listing changed or login-gated.

## Method

- Agent: `jev-ultrafast` with OpenRouter Decisions (`typesafe/jev-1.13`), no TypeSafe key.
- Pass/fail: after each non-wait action, require URL/text/fingerprint change; else DEFECT.
- Multi-phase goals with runtime MAX_STEPS=150, global action cap 140.