"""Seeded fuzz for the Playwright stage's detectors. No browser, no network.

Varied link hrefs, probe outcomes, and layout boxes are generated from a
fixed seed and pushed through the stage's classify/scan/corroborate logic
against fake Playwright objects. Invariants: findings stay typed, dedupe
by (kind, url, action) holds, auth-walled statuses never confirm, and
404/410 always confirm.
"""

import json
import random
import sys
import time
import types
from urllib.parse import urljoin, urlparse

from jev_ultrafast.qa import contracts, playwright_stage

BASE = "http://fuzz.test/"
STATUS_POOL = [200, 201, 204, 301, 302, 400, 401, 403, 404, 405, 408, 410, 418, 429, 451, 500, 502, 503]
BODY_POOL = [
    "", "all good here", "welcome to the shop",
    "Sorry, page not found", "404 Not Found", "error 404", "file not found", "is no longer available",
    "Just a moment...", "cf-chl-bypass", "Attention Required", "verify you are human",
    "denied", "<html>buy now</html>",
]
LABEL_POOL = ["Sign in", "Buy now", "Contact", "Menu", "Search"]


# --- minimal fake sync-playwright ---------------------------------------------------------

class FakeMessage:
    def __init__(self, kind, text):
        self.type = kind
        self.text = text


class FakeNavResponse:
    def __init__(self, status):
        self.status = status


class FakeBodyResponse(FakeNavResponse):
    def __init__(self, status, body):
        super().__init__(status)
        self._body = body

    def text(self):
        return self._body


def overflowing(item):
    """Mirror of the stage's in-page layout scan rule, zero-area skip included."""
    bbox = item["bbox"]
    if bbox["width"] <= 0 and bbox["height"] <= 0:
        return False
    past_viewport = bbox["x"] + bbox["width"] > playwright_stage.VIEWPORT_WIDTH + 1 or bbox["x"] < -1
    return past_viewport or bbox["scroll_width"] - bbox["client_width"] > 1


def layout_signatures(items):
    """Distinct finding signatures the stage can emit for one page's scan."""
    seen = set()
    for item in [i for i in items if overflowing(i)][:25]:
        bbox = item.get("bbox") or {}
        seen.add((playwright_stage._element_name(item), bbox.get("x"), bbox.get("y"),
                  bbox.get("width"), bbox.get("height")))
    return seen


class FakePage:
    def __init__(self, scenario):
        self.scenario = scenario
        self.handlers = {}
        self.title = ""
        self.url = None

    def on(self, event, handler):
        self.handlers.setdefault(event, []).append(handler)

    def goto(self, url, wait_until=None, timeout=None):
        info = self.scenario["pages"][url]
        self.url = url
        self.title = info.get("title", "")
        for kind, text in info.get("console", []):
            for handler in self.handlers.get("console", []):
                handler(FakeMessage(kind, text))
        return FakeNavResponse(info.get("status", 200))

    def evaluate(self, expression):
        info = self.scenario["pages"][self.url]
        if expression == playwright_stage.NAV_TIMING_JS:
            return {"load_ms": 10.0}
        if expression == playwright_stage.LINKS_JS:
            return info.get("links", [])
        if expression == playwright_stage.LAYOUT_JS:
            return [item for item in info.get("layout", []) if overflowing(item)][:25]
        raise AssertionError(f"unexpected evaluate: {expression!r}")

    def screenshot(self):
        return b"\x89PNG fuzz"

    def close(self):
        pass


class FakeRequestContext:
    def __init__(self, outcomes):
        self.outcomes = outcomes
        self.calls = []

    def get(self, url, timeout=None):
        self.calls.append(url)
        outcome = self.outcomes.get(url)
        if outcome is None:
            raise RuntimeError(f"getaddrinfo ENOTFOUND for {url}")
        if isinstance(outcome, Exception):
            raise outcome
        return FakeBodyResponse(outcome["status"], outcome.get("body", ""))


class FakeBrowserContext:
    def __init__(self, scenario):
        self.scenario = scenario
        self.request = FakeRequestContext(scenario["links"])
        self.tracing = None
        self.pages = []

    def new_page(self):
        page = FakePage(self.scenario)
        self.pages.append(page)
        return page

    def close(self):
        pass


class FakeBrowser:
    def __init__(self, scenario):
        self.scenario = scenario
        self.contexts = []

    def new_context(self, viewport=None):
        context = FakeBrowserContext(self.scenario)
        self.contexts.append(context)
        return context

    def close(self):
        pass


def install_fake_playwright(monkeypatch, scenario):
    class FakeChromium:
        def launch(self, **kwargs):
            return FakeBrowser(scenario)

    class FakePlaywright:
        chromium = FakeChromium()

        def stop(self):
            pass

    class FakeSyncPlaywright:
        def start(self):
            return FakePlaywright()

    module = types.ModuleType("playwright.sync_api")
    module.sync_playwright = FakeSyncPlaywright
    monkeypatch.setitem(sys.modules, "playwright.sync_api", module)


# --- scenario generation -------------------------------------------------------------------

def make_scenario(rng, page_count):
    """Random pages, links, and layout boxes for one stage run."""
    scenario = {"pages": {}, "links": {}}
    urls = [f"{BASE}page-{i}" for i in range(page_count)]
    for url in urls:
        links = []
        for n in range(rng.randint(0, 8)):
            roll = rng.random()
            if roll < 0.1:
                links.append("mailto:hello@fuzz.test")
            elif roll < 0.2:
                links.append(f"{url}#section-{n}")
            else:
                href = f"http://{rng.choice(['a', 'b', 'cdn'])}.fuzz.test/res-{rng.randint(0, 48)}"
                links.append(href)
                if href not in scenario["links"]:
                    mode = rng.random()
                    if mode < 0.15:
                        scenario["links"][href] = RuntimeError("net::ERR_CONNECTION_REFUSED")
                    else:
                        scenario["links"][href] = {
                            "status": rng.choice(STATUS_POOL),
                            "body": rng.choice(BODY_POOL),
                        }
        layout = []
        for i in range(rng.randint(0, 5)):
            layout.append({
                "tag": rng.choice(["div", "section", "span", "img", "table"]),
                "id": f"item-{url.rsplit('-', 1)[-1]}-{i}",
                "classes": rng.sample(["wide", "banner", "hero", "card"], k=rng.randint(0, 2)),
                "text": rng.choice(["", "some text", "x" * 120]),
                "bbox": {
                    "x": rng.randint(-50, 2000), "y": rng.randint(0, 800),
                    "width": rng.randint(0, 3000), "height": rng.randint(0, 900),
                    "scroll_width": rng.randint(0, 4000), "client_width": rng.randint(0, 2000),
                },
                "reason": rng.choice(["viewport", "scroll"]),
            })
        console = []
        if rng.random() < 0.4:
            console.append(("error", f"TypeError: fuzz{rng.randint(0, 99)}"))
        scenario["pages"][url] = {"title": f"Fuzz page {url.rsplit('-', 1)[-1]}", "status": 200,
                                  "links": links, "layout": layout, "console": console}
    return urls, scenario


def expected_probe_count(urls, scenario):
    """Distinct bare http(s) hrefs the stage must GET: its own selection rule."""
    probed = set()
    for source in urls:
        for href in scenario["pages"][source]["links"]:
            absolute = urljoin(source, href)
            parsed = urlparse(absolute)
            if parsed.scheme not in ("http", "https") or not parsed.hostname:
                continue
            bare = absolute.split("#", 1)[0]
            if bare == source.split("#", 1)[0]:
                continue
            probed.add(bare)
    return min(len(probed), playwright_stage.MAX_LINK_PROBES)


def make_context(run_dir, urls, labels):
    config = contracts.RunConfig(target_url=urls[0])
    context = contracts.RunContext(config=config, run_id="fuzz", run_dir=str(run_dir), started_at=time.time())
    for step, url in enumerate(urls, start=1):
        context.add_event(contracts.PageEvent(
            step=step, timestamp_ms=step, url=url, title="", operation="CLICK", target="e1",
            label=labels.get(url, ""), action_id=f"a{step}", executed=True, page_changed=True,
        ))
    return context


# --- fuzz tests ------------------------------------------------------------------------------

def test_link_classifier_fuzz_stays_typed_and_consistent():
    rng = random.Random(0)
    cases = 0
    for _ in range(300):
        status = rng.choice(STATUS_POOL)
        body = rng.choice(BODY_POOL)
        verdict, reason = playwright_stage.classify_link(status, body)
        cases += 1
        assert verdict in ("ok", contracts.STATUS_CANDIDATE, contracts.STATUS_CONFIRMED)
        assert reason
        if status in (401, 403, 405, 429):
            assert verdict == contracts.STATUS_CANDIDATE, f"HTTP {status} must never confirm"
        if status in (404, 410):
            assert verdict == contracts.STATUS_CONFIRMED, f"HTTP {status} must always confirm"
        if status < 400 and verdict == contracts.STATUS_CONFIRMED:
            assert reason == "error page body"
        if status >= 500:
            assert verdict == contracts.STATUS_CANDIDATE
    assert cases >= 200


def test_stage_fuzz_invariants_hold_over_generated_pages(tmp_path, monkeypatch):
    rng = random.Random(0)
    runs = 0
    probes_seen = 0
    probes_expected = 0
    layout_seen = 0
    for trial in range(25):
        run_dir = tmp_path / f"run-{trial:02d}"
        run_dir.mkdir()
        urls, scenario = make_scenario(rng, page_count=rng.randint(2, 6))
        install_fake_playwright(monkeypatch, scenario)
        labels = {url: rng.choice(LABEL_POOL) for url in urls}
        context = make_context(run_dir, urls, labels)
        context.add_finding(
            stage="explorer", kind="dead_control", severity="P2",
            title=f'dead control "{labels[urls[0]]}"', url=urls[0],
            action=f'step 1: CLICK [1] "{labels[urls[0]]}"',
            timestamp="2026-09-29T00:00:00+00:00", confidence=0.5, status=contracts.STATUS_CANDIDATE,
        )
        playwright_stage.PlaywrightStage().run(context)

        assert context.provenance["playwright_stage"] == "on"
        keys = set()
        for finding in context.findings:
            assert finding.stage in contracts.FINDING_STAGES
            assert finding.kind in contracts.FINDING_KINDS
            assert finding.severity in contracts.SEVERITIES
            assert finding.status in contracts.FINDING_STATUSES
            if finding.status == contracts.STATUS_CONFIRMED and finding.kind == "dead_control":
                assert finding.severity == "P1"
            key = (finding.kind, finding.url, finding.action)
            assert key not in keys, f"duplicate finding {key}"
            keys.add(key)

        for url in urls:
            expected = layout_signatures(scenario["pages"][url]["layout"])
            layout_findings = [f for f in context.findings if f.kind == "layout" and f.url == url]
            assert len(layout_findings) == len(expected)

        for record_path in sorted((run_dir / contracts.ARTIFACT_EVIDENCE).glob("link *.json")):
            record = json.loads(record_path.read_text())
            probes_seen += 1
            outcome = scenario["links"].get(record["href"])
            if isinstance(outcome, Exception):
                assert record["verdict"] == contracts.STATUS_CONFIRMED
            elif isinstance(outcome, dict):
                if outcome["status"] in (404, 410):
                    assert record["verdict"] == contracts.STATUS_CONFIRMED
                if outcome["status"] in (401, 403, 405, 429):
                    assert record["verdict"] != contracts.STATUS_CONFIRMED
        probes_expected += expected_probe_count(urls, scenario)
        layout_seen += sum(len(scenario["pages"][url]["layout"]) for url in urls)
        runs += 1
    assert runs == 25
    assert probes_seen == probes_expected and probes_seen >= 200
    assert layout_seen >= 50
