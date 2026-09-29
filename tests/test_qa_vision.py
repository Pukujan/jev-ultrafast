"""Offline contracts for the vision stage. httpx transports are faked."""

import base64
import json
import time

import httpx
import pytest

from jev_ultrafast.qa import contracts, vision_stage

TAGS_URL = "http://ollama.test:11434/api/tags"
CHAT_URL = "http://ollama.test:11434/api/chat"
COMPLETIONS_URL = "https://vision.test/v1/chat/completions"


def make_context(tmp_path, *, vision_mode="ollama", vision_model=None, vision_confirmed=False):
    config = contracts.RunConfig(
        target_url="http://target.test/", vision_mode=vision_mode,
        vision_model=vision_model, vision_confirmed=vision_confirmed,
    )
    return contracts.RunContext(config=config, run_id="run-1", run_dir=str(tmp_path), started_at=time.time())


def stage(tmp_path, handler, *, mode="ollama", model=None, confirmed=False):
    context = make_context(tmp_path, vision_mode=mode, vision_model=model, vision_confirmed=confirmed)
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return context, vision_stage.VisionStage(client=client)


def add_screenshots(tmp_path, count, run_url="http://target.test/"):
    evidence = tmp_path / contracts.ARTIFACT_EVIDENCE
    evidence.mkdir()
    for step in range(1, count + 1):
        (evidence / f"step {step:02d} view {step}.png").write_bytes(b"\x89PNG fake %d" % step)
    return run_url


def events_for(context, steps, url="http://target.test/"):
    for step in steps:
        context.add_event(contracts.PageEvent(
            step=step, timestamp_ms=step, url=url, title="", operation="CLICK", target=None,
            label="", action_id=f"a{step}", executed=True, page_changed=True,
        ))


def ollama_tags(*models):
    return {"models": [{"name": name, "size": size, "details": {"parameter_size": params}}
                        for name, size, params in models]}


def test_off_mode_records_nothing_and_calls_nothing(tmp_path):
    def handler(request):
        raise AssertionError("off vision must not call anything")

    context, stage_ = stage(tmp_path, handler, mode="off")
    stage_.run(context)
    assert "vision_stage" not in context.provenance  # the CLI owns the off marker
    assert context.findings == []


def test_ollama_without_installed_model_skips_with_honest_reason(tmp_path, monkeypatch):
    monkeypatch.setenv("VISION_OLLAMA_URL", "http://ollama.test:11434")
    calls = []

    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(200, json=ollama_tags(("llama3.2:3b", 2_000_000_000, "3B")))

    context, stage_ = stage(tmp_path, handler)
    stage_.run(context)
    assert context.provenance["vision_stage"] == "skipped-no-model"
    assert context.provenance["vision_reason"] == "no local vision model installed; skipped"
    assert calls == [TAGS_URL]  # one probe, never a pull
    assert context.findings == []


def test_ollama_offers_only_installed_image_capable_models_and_never_pulls(tmp_path, monkeypatch):
    monkeypatch.setenv("VISION_OLLAMA_URL", "http://ollama.test:11434")
    calls = []

    def handler(request):
        calls.append((request.method, str(request.url)))
        if request.url.path == "/api/tags":
            return httpx.Response(200, json=ollama_tags(
                ("llava:1.6b", 1_100_000_000, "1.6B"),
                ("llama3.2:3b", 2_000_000_000, "3B"),
                ("moondream2:latest", 900_000_000, "1.9B"),
            ))
        body = json.loads(request.content)
        assert body["model"] == "llava:1.6b"  # smallest within the 2B-class guard
        assert body["messages"][0]["images"] == [base64.b64encode(b"\x89PNG fake 1").decode("ascii")]
        return httpx.Response(200, json={"message": {"content": "none"}})

    context, stage_ = stage(tmp_path, handler)
    events_for(context, [1])
    add_screenshots(tmp_path, 1)
    stage_.run(context)
    assert context.provenance["vision_candidates"] == ["llava:1.6b", "moondream2:latest"]
    assert context.provenance["vision_stage"] == "ran"
    assert context.provenance["vision_reviewed"] == 1
    assert context.provenance["vision_model"] == "llava:1.6b"
    assert context.findings == []  # "none" adds nothing; no pass either
    assert ("GET", TAGS_URL) in calls and ("POST", CHAT_URL) in calls
    assert not any("/api/pull" in url for _method, url in calls)


def test_ollama_bigger_model_allowed_only_because_installed(tmp_path, monkeypatch):
    monkeypatch.setenv("VISION_OLLAMA_URL", "http://ollama.test:11434")

    def handler(request):
        if request.url.path == "/api/tags":
            return httpx.Response(200, json=ollama_tags(("llama3.2-vision:11b", 7_000_000_000, "11B")))
        return httpx.Response(200, json={"message": {"content": "none"}})

    context, stage_ = stage(tmp_path, handler, model="llama3.2-vision:11b")
    events_for(context, [1])
    add_screenshots(tmp_path, 1)
    stage_.run(context)
    assert context.provenance["vision_model"] == "llama3.2-vision:11b"
    assert context.provenance["vision_stage"] == "ran"


def test_ollama_missing_requested_model_skips_without_fetch(tmp_path, monkeypatch):
    monkeypatch.setenv("VISION_OLLAMA_URL", "http://ollama.test:11434")
    calls = []

    def handler(request):
        calls.append((request.method, str(request.url)))
        return httpx.Response(200, json=ollama_tags(("llava:1.6b", 1_100_000_000, "1.6B")))

    context, stage_ = stage(tmp_path, handler, model="qwen2.5vl:7b")
    stage_.run(context)
    assert context.provenance["vision_stage"] == "skipped-no-model"
    assert "qwen2.5vl:7b" in context.provenance["vision_reason"]
    assert [method for method, _url in calls] == ["GET"]  # no pull, no chat


def test_ollama_unreachable_records_skip(tmp_path, monkeypatch):
    monkeypatch.setenv("VISION_OLLAMA_URL", "http://ollama.test:11434")

    def handler(request):
        raise httpx.ConnectError("connection refused")

    context, stage_ = stage(tmp_path, handler)
    stage_.run(context)
    assert context.provenance["vision_stage"] == "skipped-no-model"
    assert "unreachable" in context.provenance["vision_reason"]


def test_openrouter_without_confirmation_is_declined(tmp_path, monkeypatch):
    monkeypatch.setenv("VISION_API_KEY", "sk-test")
    monkeypatch.setenv("VISION_MODEL", "provider/vision-model")

    def handler(request):
        raise AssertionError("declined vision must not send anything")

    context, stage_ = stage(tmp_path, handler, mode="openrouter", confirmed=False)
    events_for(context, [1])
    add_screenshots(tmp_path, 1)
    stage_.run(context)
    assert context.provenance["vision_stage"] == "declined"
    assert context.findings == []


def test_openrouter_runs_on_vision_credentials_only(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)  # must succeed without it
    monkeypatch.delenv("OPENROUTER_MODEL", raising=False)
    monkeypatch.setenv("VISION_API_KEY", "sk-vision")
    monkeypatch.setenv("VISION_BASE_URL", "https://vision.test/v1")
    monkeypatch.setenv("VISION_MODEL", "provider/vision-model")
    seen = {}

    def handler(request):
        seen["auth"] = request.headers.get("authorization")
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"choices": [{"message": {"content": "none"}}]})

    context, stage_ = stage(tmp_path, handler, mode="openrouter", confirmed=True)
    events_for(context, [1])
    add_screenshots(tmp_path, 1)
    stage_.run(context)
    assert context.provenance["vision_stage"] == "ran"
    assert context.provenance["vision_provider"] == "openrouter"
    assert context.provenance["vision_model"] == "provider/vision-model"
    assert seen["auth"] == "Bearer sk-vision"
    assert str(list(seen["body"]["messages"][0]["content"]))
    assert seen["body"]["model"] == "provider/vision-model"
    assert context.findings == []


def test_openrouter_defect_answers_become_candidate_visual_findings(tmp_path, monkeypatch):
    monkeypatch.setenv("VISION_API_KEY", "sk-vision")
    monkeypatch.setenv("VISION_MODEL", "provider/vision-model")
    answers = iter([
        "The nav bar overlaps the hero text near the top right corner.",
        "none",
        "Footer spacing is uneven under the signup form.",
    ])

    def handler(request):
        return httpx.Response(200, json={"choices": [{"message": {"content": next(answers)}}]})

    context, stage_ = stage(tmp_path, handler, mode="openrouter", confirmed=True)
    events_for(context, [1, 2, 3])
    add_screenshots(tmp_path, 3)
    stage_.run(context)

    visual = [f for f in context.findings if f.kind == "visual"]
    assert len(visual) == 2
    for finding in visual:
        assert finding.stage == "vision"
        assert finding.status == contracts.STATUS_CANDIDATE  # never confirmed
        assert finding.severity == "P2"
        assert finding.evidence_refs and finding.evidence_refs[0].startswith("evidence/step")
    assert visual[0].url == "http://target.test/"
    assert "nav bar overlaps" in visual[0].detail
    assert context.provenance["vision_reviewed"] == 3


def test_review_caps_at_five_screenshots(tmp_path, monkeypatch):
    monkeypatch.setenv("VISION_API_KEY", "sk-vision")
    monkeypatch.setenv("VISION_MODEL", "provider/vision-model")
    calls = []

    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(200, json={"choices": [{"message": {"content": "none"}}]})

    context, stage_ = stage(tmp_path, handler, mode="openrouter", confirmed=True)
    events_for(context, range(1, 8))
    add_screenshots(tmp_path, 7)
    stage_.run(context)
    assert len(calls) == 5
    assert context.provenance["vision_reviewed"] == 5


def test_missing_vision_credentials_skip_without_openrouter_fallback(tmp_path, monkeypatch):
    monkeypatch.delenv("VISION_API_KEY", raising=False)
    monkeypatch.delenv("VISION_MODEL", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-not-yours")  # must stay ignored

    def handler(request):
        raise AssertionError("no credentials means no request")

    context, stage_ = stage(tmp_path, handler, mode="openrouter", confirmed=True)
    stage_.run(context)
    assert context.provenance["vision_stage"] == "skipped-no-model"
    assert "VISION_API_KEY" in context.provenance["vision_reason"]
    assert context.findings == []


def test_review_failure_is_recorded_not_raised(tmp_path, monkeypatch):
    monkeypatch.setenv("VISION_API_KEY", "sk-vision")
    monkeypatch.setenv("VISION_MODEL", "provider/vision-model")

    def handler(request):
        return httpx.Response(500, json={"error": "boom"})

    context, stage_ = stage(tmp_path, handler, mode="openrouter", confirmed=True)
    events_for(context, [1])
    add_screenshots(tmp_path, 1)
    stage_.run(context)
    assert context.provenance["vision_stage"] == "ran"
    assert context.provenance["vision_reviewed"] == 0
    assert context.provenance["vision_errors"]
    assert context.findings == []  # a failed review never becomes a pass


def test_module_never_reads_openrouter_key_names():
    source = open(vision_stage.__file__, encoding="utf-8").read()
    for forbidden in ("OPENROUTER_API_KEY", "OPENROUTER_MODEL", "OPENROUTER_BASE_URL"):
        assert forbidden not in source


@pytest.mark.parametrize("answer", ["none", "None.", "", "  no defects  "])
def test_clean_answers_add_nothing(tmp_path, monkeypatch, answer):
    monkeypatch.setenv("VISION_API_KEY", "sk-vision")
    monkeypatch.setenv("VISION_MODEL", "provider/vision-model")

    def handler(request):
        return httpx.Response(200, json={"choices": [{"message": {"content": answer}}]})

    context, stage_ = stage(tmp_path, handler, mode="openrouter", confirmed=True)
    events_for(context, [1])
    add_screenshots(tmp_path, 1)
    stage_.run(context)
    assert context.findings == []
    assert context.provenance["vision_reviewed"] == 1
