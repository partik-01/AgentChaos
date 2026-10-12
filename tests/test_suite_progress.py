import json
from pathlib import Path

import pytest

from agent_chaos import cli
from agent_chaos.reports import write_html
from agent_chaos.runner import read_trace


@pytest.mark.parametrize(
    "failure,code,state",
    [
        (RuntimeError("runner failed after first trial"), 2, "harness_error"),
        (KeyboardInterrupt(), 130, "interrupted"),
    ],
)
def test_partial_trials_remain_accessible_on_stop(
    tmp_path, monkeypatch, capsys, failure, code, state
):
    original = cli.run_scenario
    calls = 0

    def run(*args, **kwargs):
        nonlocal calls
        calls += 1
        checkpoint = json.loads((tmp_path / "suite.json").read_text())
        assert checkpoint["progress"]["state"] == "running"
        assert checkpoint["progress"]["completed_trials"] == calls - 1
        assert checkpoint["progress"]["active_trial"]["trial"] == calls
        assert checkpoint["progress"]["remaining_trials"] == 4 - calls
        assert "Incomplete suite" in (tmp_path / "suite.html").read_text()
        if calls == 2:
            assert len(checkpoint["runs"]) == 1
            assert read_trace(tmp_path / checkpoint["runs"][0]["run_id"]) == checkpoint["runs"][0]
            raise failure
        return original(*args, **kwargs)

    monkeypatch.setattr(cli, "run_scenario", run)
    assert (
        cli.main(["suite", "scenarios/01_normal.yaml", "--trials", "3", "--out", str(tmp_path)])
        == code
    )
    result = json.loads(capsys.readouterr().out)
    assert result["reports"]["json"] == str(tmp_path / "suite.json")
    checkpoint = json.loads((tmp_path / "suite.json").read_text())
    assert result["progress"] == checkpoint["progress"]
    assert checkpoint["progress"]["state"] == state
    assert checkpoint["progress"]["completed_trials"] == 1
    assert checkpoint["progress"]["remaining_trials"] == 2
    assert checkpoint["progress"]["active_trial"]["trial"] == 2
    assert checkpoint["summary"]["total_trials"] == 1
    assert checkpoint["summary"]["counts"]["pass"] == 1
    assert checkpoint["summary"]["counts"]["harness_error"] == 0  # No invented trial.
    run_id = checkpoint["runs"][0]["run_id"]
    html = (tmp_path / "suite.html").read_text()
    assert "Incomplete suite" in html
    assert f"href='{run_id}/trace.json'" in html
    assert f"href='{run_id}/report.html'" in html
    assert calls == 2


def test_factory_error_is_recorded_and_later_trial_finishes(tmp_path, monkeypatch, capsys):
    scenario = Path("scenarios/01_normal.yaml").resolve()
    monkeypatch.chdir(tmp_path)
    (tmp_path / "mixed_factory.py").write_text(
        "from pathlib import Path\n"
        "from agent_chaos.agents import ScriptedAgent\n"
        "def make():\n"
        "    path = Path('attempts.txt')\n"
        "    count = int(path.read_text()) + 1 if path.exists() else 1\n"
        "    path.write_text(str(count))\n"
        "    if count == 2: raise RuntimeError('factory failed on second trial')\n"
        "    agent = ScriptedAgent('corrected')\n"
        "    agent.metadata.update(kind='custom', version='mixed-v1')\n"
        "    return agent\n"
    )
    out = tmp_path / "evidence"
    assert (
        cli.main(
            [
                "suite",
                str(scenario),
                "--agent-factory",
                "mixed_factory:make",
                "--trials",
                "3",
                "--out",
                str(out),
            ]
        )
        == 2
    )
    summary = json.loads(capsys.readouterr().out)
    assert summary["counts"] == {
        "pass": 2,
        "agent_failure": 0,
        "harness_error": 1,
        "inconclusive": 0,
    }
    assert summary["progress"]["state"] == "completed"
    assert summary["progress"]["remaining_trials"] == 0
    assert summary["progress"]["active_trial"] is None
    data = json.loads((out / "suite.json").read_text())
    assert [t["result"]["status"] for t in data["runs"]] == ["pass", "harness_error", "pass"]
    for trace in data["runs"]:
        assert read_trace(out / trace["run_id"]) == trace
    assert "Incomplete suite" not in (out / "suite.html").read_text()


def test_error_before_first_trace_never_counts_as_pass(tmp_path, monkeypatch, capsys):
    def fail(*args, **kwargs):
        raise OSError("cannot create run")

    monkeypatch.setattr(cli, "run_scenario", fail)
    assert cli.main(["suite", "scenarios/01_normal.yaml", "--out", str(tmp_path)]) == 2
    result = json.loads(capsys.readouterr().out)
    assert result["total_trials"] == 0
    assert result["counts"]["pass"] == 0
    assert result["progress"]["state"] == "harness_error"
    assert result["progress"]["remaining_trials"] == 3


def test_html_replace_failure_preserves_previous_report(tmp_path, monkeypatch):
    path = tmp_path / "suite.html"
    path.write_text("previous readable report")
    original = Path.replace

    def fail_html(self, target):
        if Path(target) == path:
            raise OSError("simulated replacement failure")
        return original(self, target)

    monkeypatch.setattr(Path, "replace", fail_html)
    with pytest.raises(OSError, match="replacement failure"):
        write_html(path, {"summary": {}})
    assert path.read_text() == "previous readable report"


def test_invalid_scenario_does_not_replace_previous_suite(tmp_path, capsys):
    prior = tmp_path / "suite.json"
    prior.write_text('{"prior": true}')
    invalid = tmp_path / "invalid.yaml"
    invalid.write_text("version: nope\n")
    assert cli.main(["suite", str(invalid), "--out", str(tmp_path)]) == 2
    assert "harness_error" in capsys.readouterr().err
    assert prior.read_text() == '{"prior": true}'


def test_checkpoint_storage_failure_leaves_last_readable_snapshot(tmp_path, monkeypatch, capsys):
    original = cli.write_json

    def save(path, data):
        active = data.get("progress", {}).get("active_trial")
        if active and active["trial"] == 2:
            raise OSError("checkpoint storage unavailable")
        original(path, data)

    monkeypatch.setattr(cli, "write_json", save)
    assert cli.main(["suite", "scenarios/01_normal.yaml", "--out", str(tmp_path)]) == 2
    assert "checkpoint storage unavailable" in capsys.readouterr().err
    checkpoint = json.loads((tmp_path / "suite.json").read_text())
    assert checkpoint["progress"]["state"] == "running"
    assert checkpoint["progress"]["completed_trials"] == 1
    assert checkpoint["progress"]["remaining_trials"] == 2
    assert read_trace(tmp_path / checkpoint["runs"][0]["run_id"]) == checkpoint["runs"][0]
    assert "Incomplete suite" in (tmp_path / "suite.html").read_text()
