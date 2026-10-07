import json
from pathlib import Path

import pytest

from agent_chaos.agents import AgentFailure
from agent_chaos.cli import main
from agent_chaos.reports import render_html
from agent_chaos.runner import read_trace, rerun, run_scenario, summarize
from agent_chaos.schema import load_scenario


@pytest.mark.parametrize("path", sorted(Path("scenarios").glob("*.yaml")), ids=lambda p: p.stem)
def test_corrected_handles_fixed_scenarios(path, tmp_path):
    trace = run_scenario(load_scenario(path), out=tmp_path)
    assert trace["result"]["status"] == "pass"
    assert Path(trace["reproduction_command"].split(" ", 2)[-1]).is_file()


@pytest.mark.parametrize("number", [3, 4, 5, 6, 7, 8])
def test_flawed_exposes_known_failures(number, tmp_path):
    path = next(Path("scenarios").glob(f"{number:02d}_*.yaml"))
    trace = run_scenario(load_scenario(path), "flawed", out=tmp_path)
    assert trace["result"]["status"] == "agent_failure"
    if number in (3, 4, 7, 8):
        assert len(trace["final_state"]["refunds"]) == 2
        assert sum(r["amount_cents"] for r in trace["final_state"]["refunds"]) == 600


def test_offline_playback_rerun_with_fix_and_export(tmp_path, capsys):
    scenario = load_scenario("scenarios/03_after_timeout.yaml")
    failed = run_scenario(scenario, "flawed", out=tmp_path)
    path = tmp_path / failed["run_id"] / "trace.json"
    before = path.read_bytes()
    assert main(["playback", str(path)]) == 0
    assert path.read_bytes() == before
    recorded = read_trace(path)
    reproduced = rerun(recorded, out=tmp_path)
    assert reproduced["final_state"] == failed["final_state"]
    assert reproduced["fault_schedule"] == failed["fault_schedule"]
    fixed = rerun(recorded, out=tmp_path, agent_version="corrected")
    assert fixed["result"]["status"] == "pass"
    assert fixed["initial_state"] == failed["initial_state"]
    assert fixed["parent_run"] == failed["run_id"]
    output = tmp_path / "export.json"
    assert main(["export", str(path), "--output", str(output)]) == 0
    assert json.loads(output.read_text())["run_id"] == failed["run_id"]
    assert output.with_suffix(".html").exists()


def test_provider_or_target_errors_never_pass(tmp_path):
    scenario = load_scenario("scenarios/01_normal.yaml")

    class Broken:
        metadata = {"conversation_assessment": "unassessed"}

        def run_turn(self, *args):
            raise RuntimeError("provider unavailable")

    trace = run_scenario(scenario, out=tmp_path, agent=Broken())
    assert trace["result"]["status"] == "harness_error"
    assert summarize([trace])["counts"]["pass"] == 0

    class Invalid(Broken):
        def run_turn(self, *args):
            raise AgentFailure("bad output")

    assert (
        run_scenario(scenario, out=tmp_path, agent=Invalid())["result"]["status"] == "agent_failure"
    )


def test_suite_counts_and_holdout_exclusion(tmp_path, capsys):
    assert main(["suite", "scenarios", "--trials", "2", "--out", str(tmp_path)]) == 0
    data = json.loads((tmp_path / "suite.json").read_text())
    assert data["summary"]["total_trials"] == 16
    assert not any(r["scenario"]["split"] == "heldout" for r in data["runs"])
    assert main(["suite", str(tmp_path / "empty")]) == 2


def test_html_escapes_customer_content(tmp_path):
    trace = run_scenario(load_scenario("scenarios/01_normal.yaml"), out=tmp_path)
    trace["messages"][0]["messages"][0]["text"] = '<script>alert("x")</script>'
    page = render_html(trace)
    assert "<script>" not in page
    assert "&lt;script&gt;" in page


def test_cli_agent_failure_exit_and_invalid_input(tmp_path, capsys):
    assert (
        main(
            ["run", "scenarios/03_after_timeout.yaml", "--agent", "flawed", "--out", str(tmp_path)]
        )
        == 1
    )
    assert main(["run", "missing.yaml"]) == 2


def test_versioned_trace_rejects_unknown_format(tmp_path):
    path = tmp_path / "trace.json"
    path.write_text('{"trace_version": 900}')
    with pytest.raises(ValueError, match="unsupported"):
        read_trace(path)
