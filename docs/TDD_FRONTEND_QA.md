# Frontend QA test plan

The automated tests check that local Laya is the default runner, missing Laya fails without Jev or deterministic-only fallback, secret-safe provider discovery, alias repeatability, artifact completeness, trace growth, and failure capture when a target cannot be reached. These are deterministic checks and make no paid model calls.

Metamorphic relation: appending one observed browser event must add a workflow node and edge while preserving earlier events. The basic fuzzer varies URL reachability and provider variable spelling through parametrized fixtures; additional randomized DOM/link generation remains outstanding.

Hidden holdout acceptance must be authored and run by a separate reviewer. It should include both injected layout defects and clean screenshots to measure false positives. No hidden fixture or answer was available to this implementation worker; visible tests are not a substitute.

Playwright is the browser substrate for the selected model-driven exploration; deterministic assertions are supporting evidence and cannot substitute for the selected runner. When Playwright tracing is added, lock and report trace mode because tracing affects timing. Record navigation timing, event-to-next-paint where supported, event-to-asserted-state, request/response, visual settle, and screenshot call duration independently. Do not use `networkidle` as the ready signal and do not call synthetic latency field INP.

Unit coverage should accept reachable hosted and localhost HTTP(S) URLs and reject malformed URLs and unsupported schemes. No test should invoke project scripts or start arbitrary services. Live acceptance still requires a discovered Laya interface, an operator-started local Study OS service and URL, and independent reproduction of real defects on both required targets. A hosted static pass alone cannot satisfy this plan.
