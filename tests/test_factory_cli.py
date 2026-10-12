import json
from pathlib import Path

import pytest

from agent_chaos.adapters import create_custom_agent, load_agent_factory
from agent_chaos.cli import main
from agent_chaos.runner import read_trace

FLAWED = "examples.custom_agent:make_flawed_agent"
CORRECTED = "examples.custom_agent:make_corrected_agent"


def test_cli_factory_failure_and_explicit_fixed_rerun(tmp_path, capsys):
    assert (
        main(
            [
                "run",
                "scenarios/03_after_timeout.yaml",
                "--agent-factory",
                FLAWED,
                "--out",
                str(tmp_path),
            ]
        )
        == 1
    )
    output = json.loads(capsys.readouterr().out)
    path = tmp_path / output["run_id"] / "trace.json"
    recorded = read_trace(path)
    assert recorded["agent"]["version"] == "example-v1-flawed"
    assert recorded["configuration"]["provider"] == "custom"
    assert sum(r["amount_cents"] for r in recorded["final_state"]["refunds"]) == 600
    assert main(["rerun", str(path), "--agent-factory", CORRECTED, "--out", str(tmp_path)]) == 0
    fixed_output = json.loads(capsys.readouterr().out)
    fixed = read_trace(tmp_path / fixed_output["run_id"])
    assert fixed["agent"]["version"] == "example-v1-corrected"
    assert fixed["initial_state"] == recorded["initial_state"]
    assert fixed["parent_run"] == recorded["run_id"]
    assert sum(r["amount_cents"] for r in fixed["final_state"]["refunds"]) == 300


def test_suite_factory_has_fresh_state_and_per_trial_seed(tmp_path, capsys):
    assert (
        main(
            [
                "suite",
                "scenarios/07_repeated_request.yaml",
                "--agent-factory",
                CORRECTED,
                "--trials",
                "3",
                "--seed",
                "8",
                "--out",
                str(tmp_path),
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["counts"]["pass"] == 3
    data = json.loads((tmp_path / "suite.json").read_text())
    assert [t["scenario"]["seed"] for t in data["runs"]] == [8, 9, 10]
    for trace in data["runs"]:
        assert len(trace["tool_events"]) > 0
        assert len(trace["final_state"]["refunds"]) == 1
        read_trace(tmp_path / trace["run_id"])
    assert (tmp_path / "suite.html").exists()


@pytest.mark.parametrize("reference", ["", "file.py", "m:f()", "m:a.b", "../x:f"])
def test_bad_factory_syntax_does_not_import(reference):
    with pytest.raises(ValueError, match="module:callable"):
        load_agent_factory(reference)


def test_local_module_loading_and_target_validation(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "custom_factory_test.py").write_text(
        "class Target:\n"
        "    metadata = {'kind': 'custom', 'version': '1', 'conversation_assessment': 'unassessed'}\n"
        "    def run_turn(self, turn, tools): return []\n"
        "def make(): return Target()\n"
        "not_callable = 4\n"
    )
    factory = load_agent_factory("custom_factory_test:make")
    assert create_custom_agent(factory).metadata["version"] == "1"
    with pytest.raises(ValueError, match="callable"):
        load_agent_factory("custom_factory_test:not_callable")
    with pytest.raises(ValueError, match="kind"):
        create_custom_agent(lambda: object())


def test_invalid_evidence_and_scenario_precede_factory_import(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "must_not_import_factory.py").write_text(
        "from pathlib import Path\nPath('imported').touch()\ndef make(): return object()\n"
    )
    (tmp_path / "invalid.json").write_text("{}")
    assert (
        main(
            [
                "rerun",
                "invalid.json",
                "--agent-factory",
                "must_not_import_factory:make",
                "--out",
                "out",
            ]
        )
        == 2
    )
    assert (
        main(
            [
                "run",
                "missing.yaml",
                "--agent-factory",
                "must_not_import_factory:make",
                "--out",
                "out",
            ]
        )
        == 2
    )
    assert not Path("imported").exists()
    assert not Path("out").exists()
    assert "harness_error" in capsys.readouterr().err


def test_conflicting_execution_options_fail_before_execution(tmp_path, capsys):
    assert (
        main(
            [
                "run",
                "scenarios/01_normal.yaml",
                "--agent-factory",
                CORRECTED,
                "--provider",
                "openai",
                "--out",
                str(tmp_path / "out"),
            ]
        )
        == 2
    )
    assert not (tmp_path / "out").exists()
    assert "omit" in capsys.readouterr().err
