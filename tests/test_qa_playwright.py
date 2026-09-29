"""Offline contracts for the Playwright evidence stage. No real browser."""

import json
import sys
import time
import types

import pytest

from jev_ultrafast.qa import contracts, playwright_stage

PNG_BYTES = b"\x89PNG fake screenshot"


class FakeMessage:
    def __init__(self, kind, text):
        self.type = kind
        self.text = text


class FakeNavResponse:
    def __init__(self, status):
        self.status = status


class FakePage:
    def __init__(self, scenario):
        self.scenario = scenario
        self.handlers = {}
        self.title = ""
        self.goto_calls = []
        self.shot_count = 0
        self.closed = False

    def on(self, event, handler):
        self.handlers.setdefault(event, []).append(handler)

    def goto(self, url, wait_until=None, timeout=None):
        self.goto_calls.append((url, wait_until, timeout))
        info = self.scenario["pages"].get(url)
        if info is None:
            raise RuntimeError(f"net::ERR_NAME_NOT_RESOLVED at {url}")
        self.url = url
        self.title = info.get("title", "")
        for message in info.get("console", []):
            for handler in self.handlers.get("console", []):
                handler(message)
        for error in info.get("page_errors", []):
            for handler in self.handlers.get("pageerror", []):
                handler(error)
        return FakeNavResponse(info.get("status", 200))

    def evaluate(self, expression):
        info = self.scenario["pages"][self.url]
        if expression == playwright_stage.NAV_TIMING_JS:
            return info.get("timing", {"load_ms": 42.0})
        if expression == playwright_stage.LINKS_JS:
            return info.get("links", [])
        if expression == playwright_stage.LAYOUT_JS:
            return info.get("layout", [])
        raise AssertionError(f"unexpected evaluate: {expression!r}")

    def screenshot(self):
        self.shot_count += 1
        return PNG_BYTES

    def close(self):
        self.closed = True


class FakeRequestContext:
    def __init__(self, scenario):
        self.scenario = scenario
        self.calls = []

    def get(self, url, timeout=None):
        self.calls.append((url, timeout))
        spec = self.scenario["links"].get(url)
        if spec is None:
            raise RuntimeError(f"getaddrinfo ENOTFOUND for {url}")
        if isinstance(spec, Exception):
            raise spec
        return FakeNavResponseWithBody(spec["status"], spec.get("body", "fine"))


class FakeNavResponseWithBody(FakeNavResponse):
    def __init__(self, status, body):
        super().__init__(status)
        self._body = body

    def text(self):
        return self._body


class FakeTracing:
    def __init__(self):
        self.started_with = None
        self.stopped_at = None

    def start(self, **kwargs):
        self.started_with = kwargs

    def stop(self, path=None):
        self.stopped_at = path


class FakeBrowserContext:
    def __init__(self, scenario, viewport):
        self.scenario = scenario
        self.viewport = viewport
        self.request = FakeRequestContext(scenario)
        self.tracing = FakeTracing()
        self.pages = []
        self.closed = False

    def new_page(self):
        page = FakePage(self.scenario)
        self.pages.append(page)
        return page

    def close(self):
        self.closed = True


class FakeBrowser:
    def __init__(self, scenario):
        self.scenario = scenario
        self.contexts = []
        self.closed = False

    def new_context(self, viewport=None):
        context = FakeBrowserContext(self.scenario, viewport)
        self.contexts.append(context)
        return context

    def close(self):
        self.closed = True


class FakeChromium:
    def __init__(self, scenario, launch_error=None):
        self.scenario = scenario
        self.launch_error = launch_error
        self.launch_kwargs = None
        self.browsers = []

    def launch(self, **kwargs):
        if self.launch_error is not None:
            raise self.launch_error
        self.launch_kwargs = kwargs
        browser = FakeBrowser(self.scenario)
        self.browsers.append(browser)
        return browser


class FakePlaywright:
    def __init__(self, chromium):
        self.chromium = chromium
        self.stopped = False

    def stop(self):
        self.stopped = True


class FakeSyncPlaywright:
    def __init__(self, playwright):
        self._playwright = playwright
        self.started = False

    def start(self):
        self.started = True
        return self._playwright


def install_fake_playwright(monkeypatch, scenario, launch_error=None):
    playwright = FakePlaywright(FakeChromium(scenario, launch_error))
    module = types.ModuleType("playwright.sync_api")
    module.sync_playwright = lambda: FakeSyncPlaywright(playwright)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", module)
    return playwright


def make_context(tmp_path, urls, *, labels=None, playwright=True, **config_extra):
    labels = labels or {}
    config = contracts.RunConfig(target_url=urls[0], playwright=playwright, **config_extra)
    context = contracts.RunContext(config=config, run_id="run-1", run_dir=str(tmp_path), started_at=time.time())
    for step, url in enumerate(urls, start=1):
        context.add_event(contracts.PageEvent(
            step=step, timestamp_ms=step * 10, url=url, title=f"Page {step}", operation="CLICK",
            target="e1", label=labels.get(url, f"Control {step}"), action_id=f"a{step}",
            executed=True, page_changed=True,
        ))
    return context


URL_A = "http://a.test/"
URL_B = "http://b.test/"


def big_scenario():
    return {
        "pages": {
            URL_A: {
                "title": "The Landing-Page!",
                "status": 200,
                "timing": {"navigation_start": 0.0, "load_event_end": 250.0, "load_ms": 250.0},
                "console": [FakeMessage("error", "TypeError: boom"), FakeMessage("log", "harmless")],
                "page_errors": ["Uncaught ReferenceError: missing is not defined"],
                "links": ["http://a.test/good", "http://a.test/gone", "http://a.test/walled", "http://dead.test/x"],
                "layout": [{
                    "tag": "div", "id": "hero", "classes": ["wide"], "text": "overflowing hero",
                    "bbox": {"x": 0, "y": 10, "width": 1400, "height": 300, "scroll_width": 1400, "client_width": 1280},
                    "reason": "viewport",
                }],
            },
            URL_B: {"title": "Books", "status": 200, "links": ["http://a.test/gone"]},
        },
        "links": {
            "http://a.test/good": {"status": 200, "body": "all fine"},
            "http://a.test/gone": {"status": 404, "body": "not here"},
            "http://a.test/walled": {"status": 403, "body": "denied"},
        },
    }


def run_stage(tmp_path, scenario, **stage_kwargs):
    context = make_context(tmp_path, [URL_A, URL_B])
    playwright_stage.PlaywrightStage(**stage_kwargs).run(context)
    return context


@pytest.mark.parametrize("status,body,verdict", [
    (404, "anything", contracts.STATUS_CONFIRMED),
    (410, "anything", contracts.STATUS_CONFIRMED),
    (200, "Sorry, page not found", contracts.STATUS_CONFIRMED),
    (401, "", contracts.STATUS_CANDIDATE),
    (403, "", contracts.STATUS_CANDIDATE),
    (405, "", contracts.STATUS_CANDIDATE),
    (429, "", contracts.STATUS_CANDIDATE),
    (500, "", contracts.STATUS_CANDIDATE),
    (200, "Just a moment... checking your browser", contracts.STATUS_CANDIDATE),
    (200, "Welcome to the site", "ok"),
    (301, "", "ok"),
])
def test_link_probe_status_mapping(status, body, verdict):
    assert playwright_stage.classify_link(status, body)[0] == verdict


def test_sweep_records_viewport_timings_and_screenshots(tmp_path, monkeypatch):
    install_fake_playwright(monkeypatch, big_scenario())
    context = run_stage(tmp_path, big_scenario())

    assert context.provenance["playwright_stage"] == "on"
    assert context.provenance["playwright_viewport"] == {"width": 1280, "height": 720}
    assert context.provenance["tracing_mode"] == "off"

    pages = context.provenance["playwright_pages"]
    assert [p["url"] for p in pages] == [URL_A, URL_B]
    for record in pages:
        assert record["navigation_ms"] is not None
        assert record["screenshot_ms"] is not None  # recorded separately from navigation
        assert record["screenshot"].startswith(f"{contracts.ARTIFACT_EVIDENCE}/step ")
    assert pages[0]["load_ms"] == 250.0
    assert pages[0]["screenshot"] == f"{contracts.ARTIFACT_EVIDENCE}/step 01 the landing page.png"
    assert (tmp_path / "evidence" / "step 01 the landing page.png").read_bytes() == PNG_BYTES


def test_sweep_link_findings_and_records(tmp_path, monkeypatch):
    install_fake_playwright(monkeypatch, big_scenario())
    context = run_stage(tmp_path, big_scenario())

    link_findings = [f for f in context.findings if f.kind == "broken_link"]
    by_url = {f.url: f for f in link_findings}
    assert set(by_url) == {"http://a.test/gone", "http://a.test/walled", "http://dead.test/x"}
    assert by_url["http://a.test/gone"].status == contracts.STATUS_CONFIRMED
    assert by_url["http://a.test/walled"].status == contracts.STATUS_CANDIDATE
    assert "403" in by_url["http://a.test/walled"].title or "403" in by_url["http://a.test/walled"].detail
    assert by_url["http://dead.test/x"].status == contracts.STATUS_CONFIRMED  # DNS failure
    for finding in link_findings:
        assert finding.stage == "playwright" and finding.severity == "P2"
        assert finding.action.startswith("playwright: GET")
        assert finding.evidence_refs and finding.evidence_refs[0].startswith(f"{contracts.ARTIFACT_EVIDENCE}/link ")

    evidence = sorted(p.name for p in (tmp_path / "evidence").glob("link *.json"))
    assert evidence == ["link 01 a.test.json", "link 02 a.test.json", "link 03 a.test.json",
                        "link 04 dead.test.json"]
    record = json.loads((tmp_path / "evidence" / "link 02 a.test.json").read_text())
    assert record["verdict"] == contracts.STATUS_CONFIRMED and record["status"] == 404
    assert context.provenance["playwright_links"] == {"probed": 4, "confirmed": 2, "candidate": 1, "capped": False}


def test_sweep_reports_console_page_and_layout_faults(tmp_path, monkeypatch):
    install_fake_playwright(monkeypatch, big_scenario())
    context = run_stage(tmp_path, big_scenario())

    page_errors = [f for f in context.findings if f.title == "uncaught page error"]
    assert len(page_errors) == 1 and page_errors[0].status == contracts.STATUS_CONFIRMED
    assert "missing is not defined" in page_errors[0].detail

    console_errors = [f for f in context.findings if f.title == "console error"]
    assert len(console_errors) == 1 and console_errors[0].status == contracts.STATUS_CANDIDATE
    assert "TypeError: boom" in console_errors[0].detail

    layouts = [f for f in context.findings if f.kind == "layout"]
    assert len(layouts) == 1 and layouts[0].status == contracts.STATUS_CONFIRMED
    assert "div#hero" in layouts[0].title and "bbox=(0,10 1400x300)" in layouts[0].detail


def test_each_link_probed_once_via_get(tmp_path, monkeypatch):
    playwright = install_fake_playwright(monkeypatch, big_scenario())
    run_stage(tmp_path, big_scenario())
    request_context = playwright.chromium.browsers[0].contexts[0].request
    assert sorted(url for url, _timeout in request_context.calls) == sorted([
        "http://a.test/good", "http://a.test/gone", "http://a.test/walled", "http://dead.test/x",
    ])  # http://a.test/gone appears on both pages but is probed once


def test_failed_setup_records_status_and_zero_findings(tmp_path, monkeypatch):
    install_fake_playwright(monkeypatch, big_scenario(), launch_error=RuntimeError("Executable doesn't exist"))
    context = make_context(tmp_path, [URL_A])
    playwright_stage.PlaywrightStage().run(context)  # must not raise
    assert context.provenance["playwright_stage"] == "failed-setup"
    assert context.findings == []
    assert "Executable doesn't exist" in context.provenance["playwright_error"]


def test_config_skip_writes_nothing_stage_side(tmp_path, monkeypatch):
    playwright = install_fake_playwright(monkeypatch, big_scenario())
    context = make_context(tmp_path, [URL_A], playwright=False)
    playwright_stage.PlaywrightStage().run(context)
    assert "playwright_stage" not in context.provenance  # the CLI owns the skipped marker
    assert context.findings == []
    assert playwright.chromium.launch_kwargs is None  # never launched


def test_visited_urls_dedupe_keep_order_and_cap():
    events = []
    for step in range(1, 21):
        events.append(contracts.PageEvent(
            step=step, timestamp_ms=step, url=f"http://site.test/p{step % 15}", title="",
            operation="CLICK", target=None, label="", action_id=f"a{step}", executed=True, page_changed=True,
        ))
    urls = playwright_stage.visited_urls(events)
    assert urls == urls[:12] == [f"http://site.test/p{i}" for i in range(1, 13)]
    assert len(set(urls)) == 12


def test_speakable_phrase_strips_punctuation():
    assert playwright_stage.speakable_phrase("The Design-Bakery — Home!") == "the design bakery home"
    assert playwright_stage.speakable_phrase("  ") == "untitled page"


def test_dedupe_by_kind_url_action(tmp_path, monkeypatch):
    install_fake_playwright(monkeypatch, big_scenario())
    context = make_context(tmp_path, [URL_A, URL_B])
    context.add_finding(
        stage="playwright", kind="broken_link", severity="P2", title="already known", url="http://a.test/gone",
        action="playwright: GET http://a.test/gone", timestamp="2026-09-29T00:00:00+00:00", confidence=1.0,
        status=contracts.STATUS_CONFIRMED,
    )
    playwright_stage.PlaywrightStage().run(context)
    matches = [f for f in context.findings if f.url == "http://a.test/gone" and f.kind == "broken_link"]
    assert len(matches) == 1 and matches[0].title == "already known"  # the pre-existing row wins


def test_corroborates_explorer_dead_control_candidates(tmp_path, monkeypatch):
    install_fake_playwright(monkeypatch, big_scenario())
    context = make_context(tmp_path, [URL_A, URL_B], labels={URL_A: "Sign in"})
    context.add_finding(
        stage="explorer", kind="dead_control", severity="P2", title='step 1: CLICK [4] "Sign in"', url=URL_A,
        action='step 1: CLICK [4] "Sign in"', timestamp="2026-09-29T00:00:00+00:00", confidence=0.5,
        status=contracts.STATUS_CANDIDATE,
    )
    context.add_finding(
        stage="explorer", kind="dead_control", severity="P2", title="ghost button", url=URL_A,
        action="step 2: CLICK [9] ghost button", timestamp="2026-09-29T00:00:01+00:00", confidence=0.5,
        status=contracts.STATUS_CANDIDATE,
    )
    playwright_stage.PlaywrightStage().run(context)
    dead = [f for f in context.findings if f.kind == "dead_control"]
    sign_in = next(f for f in dead if "Sign in" in f.action)
    ghost = next(f for f in dead if "ghost" in f.action)
    assert sign_in.status == contracts.STATUS_CONFIRMED and sign_in.severity == "P1"
    assert ghost.status == contracts.STATUS_CANDIDATE and ghost.severity == "P2"
