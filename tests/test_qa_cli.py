"""Offline tests for the jev-qa CLI: sibling modules stand in through sys.modules."""

import re
import sys
import types

import pytest

from jev_ultrafast.qa import cli
from jev_ultrafast.qa import explorer as explorer_mod
from jev_ultrafast.qa.contracts import PageEvent

RUN_URL = "https://example.test/"
CURRENT = {}


class FakeExplorer:
    def __init__(self, config, context, browser_factory=None, decider=None):
        self.config = config
        self.context = context
        self.browser_factory = browser_factory
        self.decider = decider
        CURRENT["f"].explorers.append(self)

    def run(self):
        f = CURRENT["f"]
        f.names.append("explorer.run")
        for step, fingerprint in enumerate(f.event_fingerprints, start=1):
            self.context.add_event(
                PageEvent(
                    step=step,
                    timestamp_ms=1000 + step,
                    url=RUN_URL,
                    title="Home",
                    operation="CLICK",
                    target="1",
                    label="Sign in",
                    action_id="e1",
                    executed=True,
                    page_changed=True,
                    fingerprint=fingerprint,
                    runner=self.config.runner,
                    confidence=0.9,
                )
            )
        self.context.provenance["explorer_terminal"] = "done"
        return "done"


@pytest.fixture
def fake(monkeypatch):
    class F:
        pass

    f = F()
    f.names = []
    f.calls = []
    f.explorers = []
    f.inputs = None
    f.discover_result = {"backend": "mlx", "model": "laya-mini", "max_options_per_question": 8}
    f.discover_error = None
    f.candidates = []
    f.confirm_answer = True
    f.reconcile_summary = {"watcher_pid": None}
    f.event_fingerprints = ["fp-1", "fp-2", "fp-3"]

    def rec(name, result=None):
        def call(*args, **kwargs):
            f.names.append(name)
            f.calls.append((name, args, kwargs))
            return result() if callable(result) else result

        return call

    def discover():
        f.names.append("laya.discover")
        f.calls.append(("laya.discover", (), {}))
        if f.discover_error is not None:
            raise f.discover_error
        return dict(f.discover_result)

    laya = types.ModuleType("jev_ultrafast.qa.laya")

    class LayaUnavailable(RuntimeError):
        pass

    f.LayaUnavailable = LayaUnavailable
    laya.LayaUnavailable = LayaUnavailable
    laya.discover = discover
    laya.laya_decider = rec("laya.laya_decider", lambda: "laya-decider")

    providers = types.ModuleType("jev_ultrafast.qa.providers")
    providers.discover = rec("providers.discover", lambda: list(f.candidates))
    providers.confirm_candidate = rec("providers.confirm_candidate", lambda: f.confirm_answer)
    providers.secure_entry = rec("providers.secure_entry", lambda: "sk-test-key")
    providers.insert_key = rec("providers.insert_key", lambda: {"name": "OPENROUTER_API_KEY", "opted_out": False})
    providers.read_env_value = rec("providers.read_env_value", lambda: None)
    providers.env_file_path = rec("providers.env_file_path", lambda: "/tmp/fake.env")

    class JevDeciderStub:
        name = "openrouter"
        model_slug = "typesafe/jev-1.13"

    jev_runner = types.ModuleType("jev_ultrafast.qa.jev_runner")
    jev_runner.jev_decider = rec("jev_runner.jev_decider", lambda: JevDeciderStub())

    keywatch = types.ModuleType("jev_ultrafast.qa.keywatch")
    keywatch.reconcile = rec("keywatch.reconcile", lambda: dict(f.reconcile_summary))
    keywatch.spawn_watcher = rec("keywatch.spawn_watcher")

    playwright_stage = types.ModuleType("jev_ultrafast.qa.playwright_stage")

    class PlaywrightStage:
        def run(self, context):
            f.names.append("playwright_stage.run")

    playwright_stage.PlaywrightStage = PlaywrightStage

    vision_stage = types.ModuleType("jev_ultrafast.qa.vision_stage")

    class VisionStage:
        def run(self, context):
            f.names.append("vision_stage.run")

    vision_stage.VisionStage = VisionStage

    artifacts = types.ModuleType("jev_ultrafast.qa.artifacts")
    for name in ("write_events", "write_workflow", "write_defects", "write_run"):
        setattr(artifacts, name, rec(f"artifacts.{name}"))

    report = types.ModuleType("jev_ultrafast.qa.report")
    report.build_report = rec("report.build_report")
    report.open_report = rec("report.open_report")

    for module in (laya, providers, jev_runner, keywatch, playwright_stage, vision_stage, artifacts, report):
        monkeypatch.setitem(sys.modules, module.__name__, module)

    monkeypatch.setattr(cli, "Explorer", FakeExplorer)

    def browser_sentinel(url):
        f.names.append("browser.Browser")
        raise AssertionError("the browser must not open here")

    monkeypatch.setattr(explorer_mod, "Browser", browser_sentinel)

    def fake_input(prompt=""):
        if f.inputs is None:
            raise AssertionError(f"unexpected prompt: {prompt!r}")
        return f.inputs.pop(0)

    monkeypatch.setattr("builtins.input", fake_input)

    CURRENT["f"] = f
    yield f
    CURRENT.pop("f", None)


def test_absent_runner_defaults_to_laya_without_openrouter_key(fake, monkeypatch, tmp_path):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    rc = cli.main(["--url", RUN_URL, "--yes", "--out", str(tmp_path)])
    assert rc == 0
    assert "laya.discover" in fake.names
    assert "laya.laya_decider" in fake.names
    assert not [name for name in fake.names if name.startswith("providers.")]
    explorer = fake.explorers[0]
    assert explorer.config.runner == "laya"
    assert explorer.config.provider is None
    assert explorer.decider == "laya-decider"
    assert explorer.context.provenance["backend"] == "mlx"
    assert explorer.context.provenance["model"] == "laya-mini"
    assert explorer.context.provenance["max_options_per_question"] == 8
    assert explorer.context.provenance["playwright_stage"] == "on"
    assert explorer.context.provenance["vision_stage"] == "off"


def test_blank_prompted_runner_defaults_to_laya(fake, tmp_path):
    fake.inputs = ["", "", ""]  # runner, playwright, vision: bare returns take defaults
    rc = cli.main(["--url", RUN_URL, "--out", str(tmp_path)])
    assert rc == 0
    assert fake.explorers[0].config.runner == "laya"
    assert "playwright_stage.run" in fake.names
    assert "vision_stage.run" not in fake.names


def test_path_like_url_exits_2_before_anything(fake, capsys, tmp_path):
    for bad in ("./repo", "file:///tmp/target", "example.test", "git@github.com:org/repo"):
        rc = cli.main(["--url", bad, "--yes", "--out", str(tmp_path)])
        assert rc == 2
    assert "URL-only" in capsys.readouterr().out
    assert fake.names == []
    assert "browser.Browser" not in fake.names


def test_missing_url_with_yes_fails_closed(fake, tmp_path):
    rc = cli.main(["--yes", "--out", str(tmp_path)])
    assert rc == 2
    assert fake.names == []


def test_prompted_invalid_url_exits_2(fake, capsys, tmp_path):
    fake.inputs = ["not a url"]
    rc = cli.main(["--out", str(tmp_path)])
    assert rc == 2
    assert "URL-only" in capsys.readouterr().out
    assert fake.names == []


def test_laya_unavailable_fails_closed_before_browser(fake, capsys, tmp_path):
    fake.discover_error = fake.LayaUnavailable(
        "Laya runtime missing. Start it with: git clone https://github.com/ChenneyZhuang/laya-browser-agent "
        "&& pip install -e '.[mlx]' && localdecide serve"
    )
    rc = cli.main(["--url", RUN_URL, "--yes", "--out", str(tmp_path)])
    assert rc == 2
    assert "localdecide serve" in capsys.readouterr().out
    assert fake.names == ["laya.discover"]
    assert fake.explorers == []
    assert "browser.Browser" not in fake.names


def test_jev_blank_provider_defaults_openrouter(fake, tmp_path):
    fake.candidates = [{"name": "OPENROUTER_API_KEY", "provider": "openrouter", "sources": ("env-file",)}]
    rc = cli.main(["--url", RUN_URL, "--runner", "jev", "--yes", "--out", str(tmp_path)])
    assert rc == 0
    assert "providers.discover" in fake.names
    assert "jev_runner.jev_decider" in fake.names
    assert "laya.discover" not in fake.names
    discover_calls = [args for name, args, _ in fake.calls if name == "providers.discover"]
    assert discover_calls == [("openrouter",)]
    explorer = fake.explorers[0]
    assert explorer.config.runner == "jev"
    assert explorer.config.provider == "openrouter"
    assert explorer.context.provenance["backend"] == "openrouter"
    assert explorer.context.provenance["model"] == "typesafe/jev-1.13"


def test_yes_without_any_credential_fails_closed(fake, capsys, tmp_path):
    fake.candidates = []
    rc = cli.main(["--url", RUN_URL, "--runner", "jev", "--yes", "--out", str(tmp_path)])
    assert rc == 2
    assert "rerun interactively" in capsys.readouterr().out
    assert "providers.secure_entry" not in fake.names
    assert "explorer.run" not in fake.names


def test_jev_typed_key_is_inserted_and_watch_spawned(fake, tmp_path):
    fake.candidates = []
    fake.inputs = ["", "", "", ""]  # provider, cleanup question, playwright, vision
    rc = cli.main(["--url", RUN_URL, "--runner", "jev", "--out", str(tmp_path)])
    assert rc == 0
    insert_calls = [args for name, args, _ in fake.calls if name == "providers.insert_key"]
    assert insert_calls == [("/tmp/fake.env", "OPENROUTER_API_KEY", "sk-test-key")]
    assert "keywatch.reconcile" in fake.names
    assert "keywatch.spawn_watcher" in fake.names


def test_opted_out_cleanup_skips_the_watcher(fake, tmp_path):
    fake.candidates = []
    fake.inputs = ["", "n", "", ""]  # decline idle cleanup
    rc = cli.main(["--url", RUN_URL, "--runner", "jev", "--out", str(tmp_path)])
    assert rc == 0
    assert "providers.insert_key" in fake.names
    assert "keywatch.spawn_watcher" not in fake.names


def test_reconcile_left_a_live_watcher_so_cli_does_not_double_spawn(fake, tmp_path):
    fake.candidates = []
    fake.reconcile_summary = {"watcher_pid": 4242}
    fake.inputs = ["", "", "", ""]
    rc = cli.main(["--url", RUN_URL, "--runner", "jev", "--out", str(tmp_path)])
    assert rc == 0
    assert "providers.insert_key" in fake.names
    assert "keywatch.spawn_watcher" not in fake.names


def test_yes_skips_every_prompt(fake, tmp_path):
    fake.inputs = None  # any prompt fails the test
    rc = cli.main(["--url", RUN_URL, "--yes", "--out", str(tmp_path)])
    assert rc == 0


def test_run_dir_name_matches_the_legend(fake, tmp_path):
    rc = cli.main(["--url", RUN_URL, "--yes", "--out", str(tmp_path)])
    assert rc == 0
    folders = [path for path in tmp_path.iterdir() if path.is_dir()]
    assert len(folders) == 1
    name = folders[0].name
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2} [a-z0-9.\-]+ [a-z0-9 ]+", name)
    assert "example.test" in name
    assert fake.explorers[0].context.run_dir == str(folders[0])
    assert fake.explorers[0].context.run_id == name


def test_goal_first_words_shape_the_purpose(fake, tmp_path):
    rc = cli.main(["--url", RUN_URL, "--goal", "Check checkout flow end to end", "--yes", "--out", str(tmp_path)])
    assert rc == 0
    folders = [path for path in tmp_path.iterdir() if path.is_dir()]
    assert folders[0].name.endswith("check checkout flow")


def test_events_ordered_and_countable(fake, tmp_path):
    rc = cli.main(["--url", RUN_URL, "--yes", "--out", str(tmp_path)])
    assert rc == 0
    event_calls = [args for name, args, _ in fake.calls if name == "artifacts.write_events"]
    run_dir, events = event_calls[0]
    assert [event.step for event in events] == [1, 2, 3]
    assert [event.timestamp_ms for event in events] == [1001, 1002, 1003]
    assert str(run_dir).startswith(str(tmp_path))


def test_artifacts_and_report_run_in_order(fake, tmp_path):
    rc = cli.main(["--url", RUN_URL, "--yes", "--out", str(tmp_path)])
    assert rc == 0
    assert fake.names == [
        "laya.discover",
        "laya.laya_decider",
        "explorer.run",
        "playwright_stage.run",
        "keywatch.reconcile",
        "artifacts.write_events",
        "artifacts.write_workflow",
        "artifacts.write_defects",
        "artifacts.write_run",
        "report.build_report",
        "report.open_report",
    ]


def test_no_browser_flag_suppresses_report_open(fake, tmp_path):
    rc = cli.main(["--url", RUN_URL, "--yes", "--no-browser", "--out", str(tmp_path)])
    assert rc == 0
    assert "report.build_report" in fake.names
    assert "report.open_report" not in fake.names


def test_no_playwright_skips_the_stage(fake, tmp_path):
    rc = cli.main(["--url", RUN_URL, "--no-playwright", "--yes", "--out", str(tmp_path)])
    assert rc == 0
    assert "playwright_stage.run" not in fake.names
    assert fake.explorers[0].context.provenance["playwright_stage"] == "skipped"


def test_vision_default_off_skips_the_stage(fake, tmp_path):
    rc = cli.main(["--url", RUN_URL, "--yes", "--out", str(tmp_path)])
    assert rc == 0
    assert "vision_stage.run" not in fake.names


def test_keywatch_reconcile_runs_but_no_spawn_without_a_new_key(fake, tmp_path):
    rc = cli.main(["--url", RUN_URL, "--yes", "--out", str(tmp_path)])
    assert rc == 0
    assert "keywatch.reconcile" in fake.names
    assert "keywatch.spawn_watcher" not in fake.names


def test_max_steps_reaches_the_config(fake, tmp_path):
    rc = cli.main(["--url", RUN_URL, "--max-steps", "7", "--yes", "--out", str(tmp_path)])
    assert rc == 0
    assert fake.explorers[0].config.max_steps == 7
