"""Jev arm transports: openrouter, typesafe, opencode.

Runner selection is provider selection. The openrouter arm reuses the exact
OpenRouter Decisions wiring; typesafe and opencode take their endpoints from
env only and fail closed with a message naming the missing variable. No URL
is invented: what env does not supply, the arm refuses.
"""

from __future__ import annotations

import importlib
import os

from .contracts import JEV_PROVIDERS, PROVIDER_OPENCODE, PROVIDER_OPENROUTER, PROVIDER_TYPESAFE


class TransportUnavailable(RuntimeError):
    """This Jev arm cannot start; the message names what is missing."""


def _model():
    # Lazy so tests can stand the seam in and the factory stays import-light.
    return importlib.import_module("jev_ultrafast.model")


class EnvEndpointTransport:
    """POST the shared systemone body to an operator-supplied endpoint.

    Endpoint and key come from env only. The request rides the same
    post_json(url, key, body) seam as the OpenRouter path, so the existing
    monkeypatch pattern applies.
    """

    def __init__(self, name, url, key, model_slug):
        self.name = name
        self.url = url
        self.key = key
        self.model_slug = model_slug

    def prepare(self, body):
        return body

    def request(self, body):
        return _model().post_json(self.url, self.key, body)


class JevDecider:
    """contracts.Decider over one Jev arm transport via the model seam."""

    def __init__(self, transport):
        self.transport = transport
        self.name = transport.name
        self.model_slug = transport.model_slug

    def decide(self, state, goal, history):
        return _model().decide(self.transport, state, goal, history)


def openrouter_transport():
    return _model().OpenRouterTransport()


def typesafe_transport():
    url = os.environ.get("TYPESAFE_SYSTEMONE_URL")
    if not url:
        raise TransportUnavailable("The typesafe arm needs TYPESAFE_SYSTEMONE_URL; it is not set.")
    key = os.environ.get("TYPESAFE_API_KEY")
    if not key:
        raise TransportUnavailable("The typesafe arm needs TYPESAFE_API_KEY; it is not set.")
    model_slug = os.environ.get("TYPESAFE_MODEL", "typesafe/jev-1.13")
    return EnvEndpointTransport(PROVIDER_TYPESAFE, url, key, model_slug)


def opencode_transport():
    base = os.environ.get("OPENCODE_BASE_URL")
    if not base:
        raise TransportUnavailable("The opencode arm needs OPENCODE_BASE_URL; it is not set.")
    key = os.environ.get("OPENCODE_API_KEY")
    if not key:
        raise TransportUnavailable("The opencode arm needs OPENCODE_API_KEY; it is not set.")
    url = base.rstrip("/") + "/v1/systemone"
    return EnvEndpointTransport(PROVIDER_OPENCODE, url, key, "opencode/systemone")


def jev_decider(provider, *, transport=None):
    if provider not in JEV_PROVIDERS:
        raise ValueError(f"Unknown jev provider {provider!r}; expected one of {', '.join(JEV_PROVIDERS)}.")
    if transport is None:
        if provider == PROVIDER_OPENROUTER:
            transport = openrouter_transport()
        elif provider == PROVIDER_TYPESAFE:
            transport = typesafe_transport()
        else:
            transport = opencode_transport()
    return JevDecider(transport)
