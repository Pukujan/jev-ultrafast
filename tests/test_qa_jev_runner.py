"""Offline tests for the Jev arm transports: mapping, fail-closed env, seams."""

import pytest

from jev_ultrafast import model
from jev_ultrafast.qa import jev_runner


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in (
        "TYPESAFE_SYSTEMONE_URL",
        "TYPESAFE_API_KEY",
        "TYPESAFE_MODEL",
        "OPENCODE_BASE_URL",
        "OPENCODE_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)


class FakeTransport:
    def __init__(self, name="fake", model_slug="fake/model"):
        self.name = name
        self.model_slug = model_slug

    def prepare(self, body):
        return body

    def request(self, body):
        return {"answers": {}}


class OpenRouterTransportStub:
    name = "openrouter"
    model_slug = "typesafe/jev-1.13"

    instances = []

    def __init__(self):
        OpenRouterTransportStub.instances.append(self)

    def prepare(self, body):
        return body

    def request(self, body):
        return {}


def test_openrouter_maps_to_the_model_transport(monkeypatch):
    OpenRouterTransportStub.instances = []
    monkeypatch.setattr(model, "OpenRouterTransport", OpenRouterTransportStub, raising=False)
    decider = jev_runner.jev_decider("openrouter")
    assert isinstance(decider.transport, OpenRouterTransportStub)
    assert decider.name == "openrouter"
    assert decider.model_slug == "typesafe/jev-1.13"
    assert len(OpenRouterTransportStub.instances) == 1


def test_openrouter_factory_reads_no_key_upfront(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setattr(model, "OpenRouterTransport", OpenRouterTransportStub, raising=False)
    decider = jev_runner.jev_decider("openrouter")
    assert decider.name == "openrouter"


def test_injected_transport_is_used_as_is():
    transport = FakeTransport()
    decider = jev_runner.jev_decider("openrouter", transport=transport)
    assert decider.transport is transport


def test_unknown_provider_is_rejected():
    with pytest.raises(ValueError):
        jev_runner.jev_decider("nope")


def test_typesafe_needs_its_endpoint_variable():
    with pytest.raises(jev_runner.TransportUnavailable, match="TYPESAFE_SYSTEMONE_URL"):
        jev_runner.jev_decider("typesafe")


def test_typesafe_needs_its_key_variable(monkeypatch):
    monkeypatch.setenv("TYPESAFE_SYSTEMONE_URL", "http://127.0.0.1:9/systemone")
    with pytest.raises(jev_runner.TransportUnavailable, match="TYPESAFE_API_KEY"):
        jev_runner.jev_decider("typesafe")


def test_typesafe_transport_takes_env_only(monkeypatch):
    monkeypatch.setenv("TYPESAFE_SYSTEMONE_URL", "http://127.0.0.1:9/systemone")
    monkeypatch.setenv("TYPESAFE_API_KEY", "ts-key")
    monkeypatch.setenv("TYPESAFE_MODEL", "typesafe/custom")
    transport = jev_runner.jev_decider("typesafe").transport
    assert transport.name == "typesafe"
    assert transport.url == "http://127.0.0.1:9/systemone"
    assert transport.key == "ts-key"
    assert transport.model_slug == "typesafe/custom"
    assert transport.prepare({"a": 1}) == {"a": 1}


def test_opencode_needs_its_base_variable():
    with pytest.raises(jev_runner.TransportUnavailable, match="OPENCODE_BASE_URL"):
        jev_runner.jev_decider("opencode")


def test_opencode_needs_its_key_variable(monkeypatch):
    monkeypatch.setenv("OPENCODE_BASE_URL", "http://127.0.0.1:10")
    with pytest.raises(jev_runner.TransportUnavailable, match="OPENCODE_API_KEY"):
        jev_runner.jev_decider("opencode")


def test_opencode_transport_posts_to_systemone_under_the_base(monkeypatch):
    monkeypatch.setenv("OPENCODE_BASE_URL", "http://127.0.0.1:10/")
    monkeypatch.setenv("OPENCODE_API_KEY", "oc-key")
    transport = jev_runner.jev_decider("opencode").transport
    assert transport.url == "http://127.0.0.1:10/v1/systemone"
    assert transport.key == "oc-key"


def test_env_transport_request_rides_the_post_json_seam(monkeypatch):
    seen = []

    def post(url, key, body):
        seen.append((url, key, body))
        return {"answers": {}}

    monkeypatch.setattr(model, "post_json", post)
    transport = jev_runner.EnvEndpointTransport("typesafe", "http://127.0.0.1:9/systemone", "ts-key", "slug")
    assert transport.request({"body": 1}) == {"answers": {}}
    assert seen == [("http://127.0.0.1:9/systemone", "ts-key", {"body": 1})]


def test_decide_delegates_to_the_model_seam(monkeypatch):
    seen = []

    def decide(transport, state, goal, history):
        seen.append((transport, state, goal, history))
        return {"operation": "DONE"}

    monkeypatch.setattr(model, "decide", decide, raising=False)
    transport = FakeTransport()
    decider = jev_runner.jev_decider("openrouter", transport=transport)
    result = decider.decide({"url": "u"}, "goal", [{"action": "x"}])
    assert result == {"operation": "DONE"}
    assert seen == [(transport, {"url": "u"}, "goal", [{"action": "x"}])]
