"""jev-qa: one reachable URL, one guided QA run, one saved offline report.

v1 input is URL-only. The command never accepts a repository path, never
inspects target scripts, never starts or stops target services, and never
runs project commands. The operator brings a reachable URL.
"""

from __future__ import annotations

import argparse
import importlib
import os
import re
import time
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

from .contracts import (
    ALLOWED_TARGET_SCHEMES,
    DEFAULT_MAX_STEPS,
    JEV_PROVIDERS,
    KEYWATCH_STATE,
    PROVIDER_ENV_ALIASES,
    PROVIDER_OPENROUTER,
    RUNNER_JEV,
    RUNNER_LAYA,
    RUNNERS,
    RunConfig,
    RunContext,
)
from .explorer import Explorer

URL_ONLY_RULE = (
    "v1 input is URL-only: jev-qa takes one hosted http(s) URL, or a localhost URL. "
    "It never accepts a repository path, never inspects target scripts, never starts or stops "
    "target services, and never runs project commands. Bring a reachable URL."
)

_WORDS = re.compile(r"[a-z0-9]+")
_VISION_MODES = ("off", "ollama", "openrouter")


def _import(name):
    # Lazy on purpose: sibling qa modules are only touched on the paths that need
    # them, and tests can stand them in through sys.modules.
    return importlib.import_module(f"jev_ultrafast.qa.{name}")


def _valid_target(url):
    parsed = urlparse(url)
    return parsed.scheme in ALLOWED_TARGET_SCHEMES and bool(parsed.hostname)


def _speakable_host(netloc):
    host = netloc.split("@")[-1].replace(":", " ").replace("/", " ")
    return " ".join(host.split()) or "local"


def _purpose(goals):
    words = _WORDS.findall(goals[0].lower())
    return " ".join(words[:3]) or "first pass"


def _parser():
    parser = argparse.ArgumentParser(prog="jev-qa", description="Guided frontend QA for one reachable URL.")
    parser.add_argument("--url", default="", help="hosted http(s) or localhost URL to explore")
    parser.add_argument("--runner", default="", choices=list(RUNNERS), help="decision runner; blank means laya")
    parser.add_argument(
        "--provider", default="", choices=list(JEV_PROVIDERS), help="jev provider; blank means openrouter"
    )
    parser.add_argument("--goal", dest="goals", action="append", default=None, help="exploration goal; repeatable")
    parser.add_argument("--no-playwright", action="store_true", help="skip the Playwright evidence stage")
    parser.add_argument("--vision", default=None, choices=list(_VISION_MODES), help="vision review mode; default off")
    parser.add_argument("--vision-model", default=None, help="vision model name for the chosen mode")
    parser.add_argument("--vision-confirm", action="store_true", help="confirm hosted vision may receive screenshots")
    parser.add_argument("--max-steps", type=int, default=DEFAULT_MAX_STEPS, help="exploration step budget")
    parser.add_argument("--out", default="qa-runs", help="output root for run folders")
    parser.add_argument("--no-browser", action="store_true", help="do not open the saved report")
    parser.add_argument("--yes", action="store_true", help="non-interactive: apply defaults, never prompt")
    return parser


def main(argv=None):
    args = _parser().parse_args(argv)
    try:
        return _run(args)
    except EOFError:
        print("Input ended before every choice had an answer.")
        return 2


def _run(args):
    say = print
    yes = args.yes

    def ask(prompt):
        return input(prompt).strip()

    # 1. Target URL. Scheme-required http(s); anything else fails closed.
    url = args.url.strip()
    if url and not _valid_target(url):
        say(URL_ONLY_RULE)
        return 2
    if not url:
        if yes:
            say(URL_ONLY_RULE)
            return 2
        url = ask("Target URL: ")
        if not _valid_target(url):
            say(URL_ONLY_RULE)
            return 2

    out_root = Path(args.out)
    state_path = str((out_root / KEYWATCH_STATE).resolve())

    # 2. Runner. Blank or omitted selects laya.
    runner = args.runner.strip().lower()
    if not runner and not yes:
        runner = ask("Runner laya/jev [laya]: ").lower()
    runner = runner or RUNNER_LAYA
    if runner not in RUNNERS:
        say(f"Unknown runner {runner!r}; expected laya or jev.")
        return 2

    # 3. Provider, jev arm only. Key discovery and entry live inside this step;
    # the laya arm asks for no keys and sends no decision off loopback.
    provider = args.provider.strip().lower()
    new_key_inserted = False
    opted_out = False
    if runner == RUNNER_JEV:
        if not provider and not yes:
            provider = ask("Provider openrouter/typesafe/opencode [openrouter]: ").lower()
        provider = provider or PROVIDER_OPENROUTER
        if provider not in JEV_PROVIDERS:
            say(f"Unknown provider {provider!r}; expected one of {', '.join(JEV_PROVIDERS)}.")
            return 2
        providers = _import("providers")
        try:
            candidates = providers.discover(provider) or []
        except Exception as exc:
            say(f"Provider discovery failed: {exc}")
            return 2
        key_names = [c["name"] for c in candidates if str(c.get("name", "")).upper().endswith("API_KEY")]
        primary = PROVIDER_ENV_ALIASES[provider][0]
        ordered = [primary] if primary in key_names else []
        ordered.extend(name for name in key_names if name != primary)
        chosen = None
        for name in ordered:
            if yes or providers.confirm_candidate(name):
                chosen = name
                break
        if not chosen:
            variable = primary
            if yes:
                say(f"No {provider} credential found and no key was typed; rerun interactively to enter one.")
                return 2
            value = providers.secure_entry(variable)
            if not value:
                say("No key entered; nothing to run.")
                return 2
            record = providers.insert_key(providers.env_file_path(), variable, value, state_path=state_path)
            new_key_inserted = True
            opted_out = ask("Remove this typed key after 3 hours idle? [Y/n] ").lower().startswith("n")
            if isinstance(record, dict) and record.get("opted_out"):
                opted_out = True  # a persisted opt-out is honored; the typed answer stays authoritative
            chosen = variable
        found = providers.read_env_value(chosen)
        if found:
            # Make a file-resident credential visible to the transport wiring for
            # this process only. The value is never printed.
            os.environ.setdefault(chosen, found)

    # 4. Playwright evidence stage: default on, independently skippable.
    playwright = not args.no_playwright
    if playwright and not yes:
        playwright = not ask("Playwright evidence stage? [Y/n] ").lower().startswith("n")

    # 5. Vision: default off, opt-in, never an automatic pass.
    vision_mode = args.vision
    if vision_mode is None:
        if yes:
            vision_mode = "off"
        else:
            answer = ask("Vision review off/ollama/openrouter [off]: ").lower()
            if answer in {"y", "yes"}:
                answer = ask("Which vision mode, ollama or openrouter? ").lower()
            vision_mode = answer if answer in _VISION_MODES else "off"
    vision_confirmed = args.vision_confirm
    if vision_mode == "openrouter" and not vision_confirmed and not yes:
        answer = ask("Screenshots leave this device for OpenRouter review. Continue? [y/N] ").lower()
        vision_confirmed = answer in {"y", "yes"}

    if args.max_steps < 1:
        say("--max-steps must be at least 1.")
        return 2

    # 6. Laya runtime check fails closed before any browser work.
    laya = None
    laya_info = None
    if runner == RUNNER_LAYA:
        laya = _import("laya")
        try:
            laya_info = laya.discover() or {}
        except laya.LayaUnavailable as exc:
            say(str(exc))
            return 2
        backend = laya_info.get("backend") if isinstance(laya_info, dict) else None
        say(f"Laya runtime ready ({backend})." if backend else "Laya runtime ready.")

    goals = tuple(args.goals) if args.goals else RunConfig(target_url="").goals
    host = _speakable_host(urlparse(url).netloc)
    base = f"{date.today().isoformat()} {host} {_purpose(goals)}"
    run_dir = out_root / base
    suffix = 2
    while run_dir.exists():
        run_dir = out_root / f"{base} {suffix}"
        suffix += 1
    run_dir.mkdir(parents=True)

    config = RunConfig(
        target_url=url,
        runner=runner,
        provider=provider or None,
        goals=goals,
        playwright=playwright,
        vision_mode=vision_mode,
        vision_model=args.vision_model,
        vision_confirmed=vision_confirmed,
        max_steps=args.max_steps,
        out_root=args.out,
        noninteractive=yes,
    )
    context = RunContext(config=config, run_id=run_dir.name, run_dir=str(run_dir), started_at=time.time())
    context.provenance["playwright_stage"] = "on" if playwright else "skipped"
    if vision_mode == "off":
        context.provenance["vision_stage"] = "off"

    if runner == RUNNER_LAYA:
        decider = laya.laya_decider()
        if isinstance(laya_info, dict):
            for key in ("backend", "model", "max_options_per_question"):
                if laya_info.get(key) is not None:
                    context.provenance[key] = laya_info[key]
    else:
        decider = _import("jev_runner").jev_decider(provider)
        if getattr(decider, "name", None):
            context.provenance["backend"] = decider.name
        if getattr(decider, "model_slug", None):
            context.provenance["model"] = decider.model_slug

    try:
        terminal = Explorer(config, context, decider=decider).run()
        say(f"Exploration finished: {terminal}.")
        if config.playwright:
            _import("playwright_stage").PlaywrightStage().run(context)
        if config.vision_mode != "off":
            _import("vision_stage").VisionStage().run(context)
        keywatch = _import("keywatch")
        try:
            summary = keywatch.reconcile(state_path)
        except Exception as exc:
            say(f"Keywatch reconciliation failed: {exc}")
            return 2
        # reconcile respawns a missing watcher for actionable records; spawn here
        # only when a fresh insert needs one and reconcile left none running.
        if new_key_inserted and not opted_out and not (summary or {}).get("watcher_pid"):
            keywatch.spawn_watcher(state_path)
        artifacts = _import("artifacts")
        artifacts.write_events(run_dir, context.events)
        artifacts.write_workflow(run_dir, context.events)
        artifacts.write_defects(run_dir, context.findings)
        artifacts.write_run(run_dir, context)
        report = _import("report")
        report.build_report(run_dir, context)
        if not args.no_browser:
            report.open_report(run_dir)
    except Exception as exc:
        say(f"Run failed: {exc}")
        return 1
    say(f"Report saved to {run_dir}.")
    return 0
