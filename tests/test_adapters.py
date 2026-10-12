import pytest

from agent_chaos.agents import claim
from agent_chaos.cli import main
from agent_chaos.runner import read_trace, rerun, run_scenario
from agent_chaos.schema import load_scenario
from agent_chaos.traces import validate_trace


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
