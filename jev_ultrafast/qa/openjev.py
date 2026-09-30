"""OpenJev arm: an APUS-OpenJev-4B decision model served by local Ollama.

OpenJev is not a chat model and it does not speak the hosted Jev wire format.
It is a fine-tuned Qwen3.5 that scores caller-supplied candidates: each
question is rendered into the training contract prompt (state, instructions,
2-16 candidates labelled A-P), Ollama returns one token with its logit
distribution, and label probabilities are renormalized into the answers shape
``model.decide()`` already validates. Requests go to a loopback Ollama
endpoint only; page content never leaves the machine.

Four facts from the model card drive this module:

* Thinking must stay off. Ollama renders this architecture with its built-in
  Qwen3.5 renderer, which opens a thinking block unless the prompt is sent
  raw with the no-thinking prefill the GGUF examples use. Left on, Frozen80
  drops from 66/80 to 45/80, so the prompt shape is pinned by golden tests.
* The contract allows 2-16 candidates per question. Browser element tables
  exceed that, so a wide question splits into interleaved chunks (one scoring
  call per chunk) and the chunk winners compete in a further pass, recursing
  while the winner set itself outgrows the cap. Each round's distribution
  sums to one, so p(option) = p_round(winner) * p_round(option) stays exact
  and normalized over every option, which ``validate_choice`` requires.
* Ollama reports at most 20 ``top_logprobs`` and cannot pin named tokens. A
  label it did not report sits strictly below the lowest probability it did
  report, over any token: an upper bound, never an invention. The answer
  carries ``distribution_complete`` so a scored-over-half-the-options result
  is visible in the evidence instead of looking certain.
* The checkpoint loads lazily inside the first generate call, not on
  ``/api/tags``. ``preflight`` therefore issues one throwaway 1-token
  scoring request so a missing model, a cold load, or an out-of-memory
  failure stops the run before any browser opens.

Probabilities are uncalibrated softmax over candidate tokens. They answer
"which option does the model prefer", not "how likely is it correct".
"""

from __future__ import annotations

import json
import math
import os
import time
import urllib.error
import urllib.parse
import urllib.request

LABELS = "ABCDEFGHIJKLMNOP"
MAX_CANDIDATES = len(LABELS)

OPENJEV_BASE_URL_ENV = "OPENJEV_OLLAMA_URL"
OPENJEV_MODEL_ENV = "OPENJEV_MODEL"
OPENJEV_DEFAULT_BASE_URL = "http://127.0.0.1:11434"
OPENJEV_DEFAULT_MODEL = "hf.co/apus-ailab/APUS-OpenJev-v1-4B-GGUF:Q4_K_M"
DEFAULT_TIMEOUT_SECONDS = 120.0
PREFLIGHT_TIMEOUT_SECONDS = 600.0  # a cold local load is minutes, not milliseconds
_LOOPBACK = {"127.0.0.1", "localhost", "::1"}

# Raw-mode no-thinking prefill, matching examples/openjev_local.py in the GGUF
# release. Assembled from parts so the ChatML delimiters stay readable here.
_IM_START = "<" + "|im_start|" + ">"
_IM_END = "<" + "|im_end|" + ">"
_THINK_OPEN = "<th" + "ink>"
_THINK_CLOSE = "</th" + "ink>"
CHAT = (
    f"{_IM_START}user\n{{prompt}}{_IM_END}\n"
    f"{_IM_START}assistant\n{_THINK_OPEN}\n\n{_THINK_CLOSE}\n\n"
)


class OpenJevUnavailable(RuntimeError):
    """The local decision model is missing or unreachable; nothing executed."""


def base_url(override=None):
    """Resolve the Ollama endpoint and refuse anything that is not loopback."""
    raw = (override or os.environ.get(OPENJEV_BASE_URL_ENV) or OPENJEV_DEFAULT_BASE_URL).strip()
    if not raw:
        raw = OPENJEV_DEFAULT_BASE_URL
    if "://" not in raw:
        raw = "http://" + raw
    parsed = urllib.parse.urlparse(raw)
    if (parsed.hostname or "").lower() not in _LOOPBACK:
        raise OpenJevUnavailable(
            f"{OPENJEV_BASE_URL_ENV} must point at a loopback address; {raw!r} would send "
            "page content off this machine."
        )
    return raw.rstrip("/")


def model_name(override=None):
    return (override or os.environ.get(OPENJEV_MODEL_ENV) or OPENJEV_DEFAULT_MODEL).strip()


def candidate_description(criterion):
    """One option's description text, in the contract's own words."""
    if isinstance(criterion, str):
        return criterion.strip() or "option"
    data = criterion if isinstance(criterion, dict) else {"element": str(criterion)}
    parts = [str(data.get("element") or data.get("label") or "").strip()]
    value = str(data.get("current_value") or "").strip()
    if value:
        parts.append(f"value={value!r}")
    for key in ("role", "checked", "selected", "expanded"):
        if key in data:
            parts.append(f"{key}={data[key]}")
    return " ".join(part for part in parts if part) or "option"


def render_prompt(state_text, instructions, descriptions):
    """Training contract prompt: shared state, sorted JSON task, letter request.

    Mirrors openjev_contracts.render_prompt from the GGUF release: criteria are
    {label, description} pairs serialized with sorted keys, and the reply line
    names only the legal letters for this candidate count.
    """
    task = {
        "criteria": [{"description": text, "label": label} for label, text in zip(LABELS, descriptions)],
        "instructions": instructions,
        "primitive": "choice",
    }
    body = json.dumps(task, ensure_ascii=False, sort_keys=True)
    letters = ", ".join(LABELS[: len(descriptions)])
    return f"Shared state:\n{state_text}\n\n{body}\nReturn only the selected letter: {letters}.\nAnswer:"


def generate_payload(state_text, instructions, descriptions, model):
    """One raw scoring request: greedy, one token, the label logit set."""
    return {
        "model": model,
        "prompt": CHAT.format(prompt=render_prompt(state_text, instructions, descriptions)),
        "raw": True,
        "stream": False,
        "logprobs": True,
        "top_logprobs": 20,
        "options": {"temperature": 0, "num_predict": 1, "num_ctx": 9216},
    }


def _label_logprobs(data):
    """({label-or-token: logprob}, saw_any_logprobs) from one generate reply."""
    positions = data.get("logprobs") or []
    if not positions:
        raise OpenJevUnavailable("OpenJev answered without logprobs; nothing executed.")
    entries = positions[0].get("top_logprobs") or []
    reported = {}
    for item in entries:
        token = str(item.get("token") or "")
        if token:
            reported[token] = float(item.get("logprob", 0.0))
    if not reported:
        raise OpenJevUnavailable("OpenJev returned no token probabilities; nothing executed.")
    return reported


def _distribution(state_text, instructions, ids, descriptions, *, post, model, limit, depth=0):
    """Probabilities over every id, asking the model in contract-sized rounds.

    Returns (probs, complete). A round splits into interleaved chunks of at
    most `limit` options, scores each, then recurses on the chunk winners when
    there are too many of them to ask in one round. Multiplying each option by
    its winner's share keeps the product a true distribution: every round
    sums to one over its own candidates.
    """
    if depth > 4:
        raise ValueError("OpenJev coarse-to-fine did not converge; the option set is too large.")
    if len(ids) == 1:
        return {ids[0]: 1.0}, True  # degenerate question: no model call needed
    if len(ids) <= limit:
        payload = generate_payload(state_text, instructions, descriptions, model)
        reported = _label_logprobs(post(payload))
        labels = LABELS[: len(ids)]
        visible = {label: reported[label] for label in labels if label in reported}
        if not visible:
            # The model answered with something other than a candidate letter.
            # That is a bad answer, not a dead runtime: the explorer stops the
            # walk cleanly instead of treating a local server fault as fatal.
            raise ValueError(f"OpenJev returned no candidate letter; got {sorted(reported)[:6]}")
        floor = min(reported.values()) - 1.0  # below anything the server reported at all
        probs = _normalize(labels, visible, floor)
        by_id = {option_id: probs[label] for label, option_id in zip(labels, ids)}
        return by_id, all(label in visible for label in labels)
    chunks = _interleaved(len(ids), limit)
    chunk_probs = {}
    winners = []
    complete = True
    for offsets in chunks:
        sub_ids = [ids[index] for index in offsets]
        sub_desc = [descriptions[index] for index in offsets]
        local, local_complete = _distribution(
            state_text, instructions, sub_ids, sub_desc, post=post, model=model, limit=limit, depth=depth + 1
        )
        chunk_probs.update(local)
        winners.append(max(sub_ids, key=lambda option_id: local[option_id]))
        complete = complete and local_complete
    winner_desc = [descriptions[ids.index(winner)] for winner in winners]
    final, final_complete = _distribution(
        state_text, instructions, winners, winner_desc, post=post, model=model, limit=limit, depth=depth + 1
    )
    complete = complete and final_complete
    probs = {
        option_id: final[winner] * chunk_probs[option_id]
        for offsets, winner in zip(chunks, winners)
        for option_id in (ids[index] for index in offsets)
    }
    return probs, complete


def _normalize(labels, logprobs, floor):
    """Softmax over the candidate labels; unreported labels sit below the floor."""
    values = {label: logprobs.get(label, floor) for label in labels}
    peak = max(values.values())
    weights = {label: math.exp(value - peak) for label, value in values.items()}
    total = sum(weights.values()) or 1.0
    return {label: weight / total for label, weight in weights.items()}


def _interleaved(count, size):
    """Chunk index lists so each chunk samples across the whole option range."""
    parts = -(-count // size)
    return [list(range(index, count, parts)) for index in range(parts)]


def choose_question(state_text, instructions, ids, descriptions, *, post, model, limit=MAX_CANDIDATES):
    """Choice over N candidates, chunked coarse-to-fine when N exceeds the cap.

    Returns one Jev-shaped answer: choice, confidence, and probabilities that
    sum to one across every candidate.
    """
    if not ids:
        raise ValueError("OpenJev needs at least one candidate.")
    probs, complete = _distribution(
        state_text, instructions, ids, descriptions, post=post, model=model, limit=limit
    )
    top = max(probs, key=lambda option_id: probs[option_id])
    rounded = {option_id: round(value, 6) for option_id, value in probs.items()}
    drift = round(1.0 - sum(rounded.values()), 6)
    if abs(drift) >= 1e-9:
        rounded[top] = round(rounded[top] + drift, 6)
    return {
        "choice": top,
        "confidence": rounded[top],
        "probabilities": rounded,
        "distribution_complete": bool(complete),
    }


def _instructions_text(instructions):
    """Jev keeps instructions as a dict/array; the contract wants one string."""
    if isinstance(instructions, str):
        return instructions
    if isinstance(instructions, dict):
        parts = [str(instructions.get("goal") or "")]
        if instructions.get("operation"):
            parts.append(f"operation: {instructions['operation']}")
        rules = instructions.get("rules") or []
        if isinstance(rules, str):
            rules = [rules]
        if rules:
            parts.append("rules: " + " ".join(str(rule) for rule in rules))
        return " ".join(part for part in parts if part).strip()
    if isinstance(instructions, list):
        return " ".join(str(item) for item in instructions)
    return str(instructions or "")


def state_text(state):
    """Render the shared state block: page facts, then the element table."""
    if isinstance(state, str):
        return state
    page = (state or {}).get("page") or {}
    lines = [f"{key}: {page[key]}" for key in ("url", "title") if page.get(key)]
    visible = " ".join(str(page.get("text") or "").split())
    if visible:
        lines.append("visible text: " + visible[:1500])
    for element in (state or {}).get("elements") or []:
        label = element.get("label") if isinstance(element, dict) else str(element)
        if label:
            lines.append(str(label))
    recent = (state or {}).get("recent_actions") or []
    if recent:
        lines.append("recent: " + "; ".join(str(step.get("action")) for step in recent[-5:]))
    return "\n".join(lines) or "empty page"


def _get_json(url, timeout=15.0):
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        raise OpenJevUnavailable(f"OpenJev preflight got HTTP {exc.code} at {url}") from None
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise OpenJevUnavailable(f"OpenJev preflight could not reach {url} ({exc})") from None


class OpenJevTransport:
    """contracts.Transport for OpenJev-on-Ollama: same body in, answers out.

    The body ``model.build_request_body`` already produces is decomposed into
    one scoring call per question and reassembled into the Jev answers shape,
    so ``parse_result`` and ``validate_choice`` run unchanged. Local transport:
    no Authorization header, no non-loopback host.
    """

    name = "openjev"

    def __init__(self, url=None, model=None, timeout=DEFAULT_TIMEOUT_SECONDS, poster=None, getter=None):
        self.base = base_url(url)
        self.model_slug = model_name(model)
        self.timeout = float(timeout)
        self._poster = poster
        self._getter = getter
        self.question_meta = {}
        self.warm = None

    @property
    def endpoint(self):
        return self.base + "/api/generate"

    def prepare(self, body):
        return body  # the dialect rewrite happens per question in request()

    def _post(self, payload, timeout=None):
        if self._poster is not None:
            return self._poster(payload)
        request = urllib.request.Request(
            self.endpoint,
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout or self.timeout) as response:
                return json.loads(response.read().decode())
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")[:200] if exc.fp else ""
            raise OpenJevUnavailable(f"OpenJev HTTP {exc.code} at {self.endpoint}: {detail}") from None
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise OpenJevUnavailable(
                f"OpenJev is not reachable at {self.base} ({exc}); start Ollama or pick another arm."
            ) from None

    def _get(self, path, timeout=15.0):
        if self._getter is not None:
            return self._getter(path)
        return _get_json(self.base + path, timeout=timeout)

    def preflight(self):
        """Fail closed before any browser work: server up, model present, loadable.

        The model loads lazily inside the first generate call, so a green
        /api/tags still leaves an unloadable checkpoint (missing blob, out of
        memory) fatal mid-walk. The throwaway scoring request answers one
        letter about a placeholder state and proves the checkpoint resident.
        """
        version = (self._get("/api/version") or {}).get("version", "")
        tags = (self._get("/api/tags") or {}).get("models") or []
        names = {str(entry.get("name") or "") for entry in tags}
        if self.model_slug not in names:
            raise OpenJevUnavailable(
                f"Ollama at {self.base} has no {self.model_slug!r}. Pull it first: "
                f"ollama pull {self.model_slug}. No decision was made and no browser was opened."
            )
        probe = generate_payload(
            "Preflight probe.", "Which letter?", ["the first option", "the second option"], self.model_slug
        )
        started = time.perf_counter()
        answer = self._post(probe, timeout=PREFLIGHT_TIMEOUT_SECONDS)
        _label_logprobs(answer)  # raises OpenJevUnavailable if the warm-up did not score
        self.warm = {"load_ms": round((time.perf_counter() - started) * 1000, 1)}
        return {"base": self.base, "version": version, "model": self.model_slug, **self.warm}

    def request(self, body):
        shared = state_text(body.get("state") or {})
        answers = {}
        meta = {}
        for name, question in (body.get("questions") or {}).items():
            criteria = question.get("criteria") or {}
            if isinstance(criteria, dict):
                ids = list(criteria)
                descriptions = [candidate_description(criteria[key]) for key in ids]
            else:
                ids = [str(index) for index in range(len(criteria))]
                descriptions = [candidate_description(item) for item in criteria]
            answer = choose_question(
                shared,
                _instructions_text(question.get("instructions", "")),
                ids,
                descriptions,
                post=self._post,
                model=self.model_slug,
            )
            answers[name] = answer
            meta[name] = {"candidates": len(ids), "distribution_complete": answer["distribution_complete"]}
        self.question_meta = meta
        return {"answers": answers, "model": self.model_slug, "usage": {}, "latency_ms": None}


def openjev_decider(url=None, model=None, transport=None):
    """Decider over the OpenJev transport, reusing the shared decide() tail."""
    from .. import model as decisions

    chosen = transport or OpenJevTransport(url=url, model=model)

    class OpenJevDecider:
        name = chosen.name
        model_slug = chosen.model_slug

        def __init__(self):
            self.transport = chosen

        def decide(self, state, goal, history):
            return decisions.decide(self.transport, state, goal, history)

    return OpenJevDecider()
