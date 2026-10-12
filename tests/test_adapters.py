import importlib.util
import json
from pathlib import Path

import pytest

from agent_chaos.agents import claim
from agent_chaos.cli import main
from agent_chaos.runner import read_trace, rerun, run_scenario
from agent_chaos.schema import load_scenario
from agent_chaos.traces import validate_trace


def example_module():
    spec = importlib.util.spec_from_file_location("custom_example", "examples/custom_agent.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CustomerAgent:
    def __init__(self, version="my-agent-1"):
        self.metadata = {
            "kind": "custom",
            "name": "customer-agent",
            "version": version,
            "conversation_assessment": "deterministic_templates",
        }
        self.turns = 0

    def run_turn(self, turn, tools):
        self.turns += 1
        m = turn.messages[-1]
        args = {
            k: getattr(m, k) for k in ("request_id", "payment_id", "customer_id", "amount_cents")
        } | {"idempotency_key": m.request_id}
        result = tools.call("create_refund", args)
        if result.get("error"):
            result = tools.call("create_refund", args)
        return [claim(m, "completed" if result.get("status") == "succeeded" else "uncertain")]


def custom_run(tmp_path):
    return run_scenario(
        load_scenario("scenarios/03_after_timeout.yaml"),
        "my-agent-1",
        provider="custom",
        agent=CustomerAgent(),
        out=tmp_path,
    )


def test_custom_target_trace_and_fresh_restored_rerun(tmp_path):
    original = custom_run(tmp_path)
    validate_trace(original)
    recorded = read_trace(tmp_path / original["run_id"])
    target = CustomerAgent("my-agent-2")
    repeated = rerun(recorded, agent=target, agent_version="my-agent-2", out=tmp_path)
    validate_trace(repeated)
    assert target.turns == 1
    assert repeated["agent"]["version"] == "my-agent-2"
    assert repeated["parent_run"] == original["run_id"]
    assert repeated["initial_state"] == original["initial_state"]
    assert repeated["final_state"] == original["final_state"]
    assert repeated["result"]["status"] == "pass"
    assert [e["kind"] for e in repeated["backend_events"]] == [
        "refund_committed",
        "idempotent_replay",
    ]


def test_custom_rerun_requires_adapter_before_creating_output(tmp_path, capsys):
    original = custom_run(tmp_path)
    destination = tmp_path / "must-not-exist"
    with pytest.raises(ValueError, match="fresh agent instance"):
        rerun(original, out=destination)
    assert not destination.exists()
    assert main(["rerun", str(tmp_path / original["run_id"]), "--out", str(destination)]) == 2
    assert "Custom-agent reruns require" in capsys.readouterr().err
    assert not destination.exists()
    switched = rerun(original, provider="scripted", agent_version="corrected", out=tmp_path)
    assert switched["agent"]["kind"] == "scripted"
    assert switched["result"]["status"] == "pass"


def test_custom_without_target_and_unassessed_prose_never_pass(tmp_path):
    scenario = load_scenario("scenarios/01_normal.yaml")
    failed = run_scenario(scenario, "my-agent-1", provider="custom", out=tmp_path)
    validate_trace(failed)
    assert failed["result"]["status"] == "harness_error"
    agent = CustomerAgent()
    agent.metadata["conversation_assessment"] = "unassessed"
    trace = run_scenario(scenario, "my-agent-1", provider="custom", agent=agent, out=tmp_path)
    validate_trace(trace)
    assert trace["result"]["status"] == "inconclusive"


@pytest.mark.parametrize("scenario_path", sorted(Path("scenarios").glob("*.yaml")))
def test_example_corrected_handles_development_scenarios(scenario_path, tmp_path):
    agent = example_module().MySupportAgent()
    trace = run_scenario(
        load_scenario(scenario_path),
        agent.metadata["version"],
        provider="custom",
        agent=agent,
        out=tmp_path,
    )
    validate_trace(trace)
    assert trace["result"]["status"] == "pass"


def test_example_runner_failure_playback_reproduction_and_fix(tmp_path, capsys):
    example = example_module()
    assert (
        example.main(
            ["run", "scenarios/03_after_timeout.yaml", "--policy", "flawed", "--out", str(tmp_path)]
        )
        == 1
    )
    output = json.loads(capsys.readouterr().out)
    recorded = read_trace(output["trace"])
    assert sum(r["amount_cents"] for r in recorded["final_state"]["refunds"]) == 600
    assert main(["inspect", output["trace"]]) == 0
    capsys.readouterr()
    before = Path(output["trace"]).read_bytes()
    for policy, expected_exit, amount in [("flawed", 1, 600), ("corrected", 0, 300)]:
        assert (
            example.main(["rerun", output["trace"], "--policy", policy, "--out", str(tmp_path)])
            == expected_exit
        )
        fresh = read_trace(json.loads(capsys.readouterr().out)["trace"])
        assert fresh["parent_run"] == recorded["run_id"]
        assert fresh["initial_state"] == recorded["initial_state"]
        assert sum(r["amount_cents"] for r in fresh["final_state"]["refunds"]) == amount
    assert Path(output["trace"]).read_bytes() == before


def test_example_suite_creates_isolated_targets_and_counts(tmp_path, capsys):
    example = example_module()
    assert (
        example.main(
            [
                "suite",
                "scenarios/07_repeated_request.yaml",
                "--trials",
                "3",
                "--out",
                str(tmp_path),
            ]
        )
        == 0
    )
    summary = json.loads(capsys.readouterr().out)
    bundle = json.loads((tmp_path / "suite.json").read_text())
    assert summary["counts"]["pass"] == summary["total_trials"] == 3
    assert len({t["run_id"] for t in bundle["runs"]}) == 3
    assert [t["scenario"]["seed"] for t in bundle["runs"]] == [17, 18, 19]
    for trace in bundle["runs"]:
        validate_trace(trace)
        assert len(trace["final_state"]["refunds"]) == 1
    assert (tmp_path / "suite.html").is_file()
