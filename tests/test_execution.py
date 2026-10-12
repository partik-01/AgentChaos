import copy
import json
import multiprocessing
import os
import signal
import time
from pathlib import Path

import pytest

from agent_chaos.agents import ScriptedAgent
from agent_chaos.cli import main
from agent_chaos.execution import execution_limits
from agent_chaos.runner import read_trace, rerun, run_scenario
from agent_chaos.schema import load_scenario
from agent_chaos.traces import validate_trace

HANG = "examples.limited_agents:make_refund_then_hang"
READS = "examples.limited_agents:make_endless_reads"
GOOD = "examples.custom_agent:make_corrected_agent"


class CrashAfterRefund(ScriptedAgent):
    def run_turn(self, turn, tools):
        super().run_turn(turn, tools)
        os._exit(7)


class IgnoreTermination(ScriptedAgent):
    def run_turn(self, turn, tools):
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        super().run_turn(turn, tools)
        while True:
            time.sleep(1)


def scenario():
    return load_scenario("scenarios/01_normal.yaml")


def saved(trace, directory):
    assert read_trace(directory / trace["run_id"]) == trace
    assert (directory / trace["run_id"] / "report.html").is_file()
    return trace


def test_hang_preserves_committed_refund_and_stops_worker(tmp_path):
    children = {p.pid for p in multiprocessing.active_children()}
    start = time.monotonic()
    trace = saved(
        run_scenario(scenario(), agent_factory=HANG, timeout_seconds=1, out=tmp_path), tmp_path
    )
    assert time.monotonic() - start < 6
    assert trace["result"]["status"] == "agent_failure"
    assert trace["execution_stop"]["kind"] == "deadline"
    assert trace["execution_stop"]["phase"] == "agent"
    assert len(trace["tool_events"]) == 1
    assert trace["responses"] == []
    assert trace["final_state"]["refunds"][0]["amount_cents"] == 300
    assert not trace["agent"]["execution_metadata_complete"]
    assert "execution_deadline" in {v["rule"] for v in trace["result"]["violations"]}
    assert {p.pid for p in multiprocessing.active_children()} == children


def test_budget_blocks_next_call_even_if_target_retries_exceptions(tmp_path):
    trace = saved(
        run_scenario(scenario(), agent_factory=READS, max_tool_calls=3, out=tmp_path), tmp_path
    )
    assert trace["result"]["status"] == "agent_failure"
    assert len(trace["tool_events"]) == 3
    assert trace["backend_events"] == []
    assert trace["final_state"] == trace["initial_state"]
    assert trace["execution_stop"]["completed_tool_calls"] == 3
    assert trace["execution_stop"]["blocked_call"] == {
        "tool": "get_payment",
        "arguments": {"payment_id": "pay_alice"},
    }


def test_faulted_attempts_count_and_blocked_refund_has_no_effect(tmp_path):
    fixture = load_scenario("scenarios/03_after_timeout.yaml")
    trace = saved(run_scenario(fixture, "flawed", max_tool_calls=2, out=tmp_path), tmp_path)
    assert trace["result"]["status"] == "agent_failure"
    assert len(trace["tool_events"]) == 2
    assert trace["tool_events"][1]["fault"]["kind"] == "after_timeout"
    assert trace["execution_stop"]["blocked_call"]["tool"] == "create_refund"
    assert len(trace["final_state"]["refunds"]) == 1
    assert trace["final_state"]["refunds"][0]["amount_cents"] == 300


def test_deadline_evidence_cannot_claim_early_expiry(tmp_path):
    trace = run_scenario(scenario(), agent_factory=HANG, timeout_seconds=1, out=tmp_path)
    trace["execution_stop"]["elapsed_ms"] = 0
    with pytest.raises(ValueError, match="invalid deadline evidence"):
        validate_trace(trace)


def test_factory_import_itself_is_bounded(tmp_path, monkeypatch):
    fixture = scenario()
    monkeypatch.chdir(tmp_path)
    (tmp_path / "import_hang.py").write_text("import time\ntime.sleep(30)\n")
    trace = saved(
        run_scenario(fixture, agent_factory="import_hang:make", timeout_seconds=1, out=tmp_path),
        tmp_path,
    )
    assert trace["result"]["status"] == "harness_error"
    assert trace["execution_stop"]["phase"] == "initialization"


def test_suite_continues_after_target_budget_failure(tmp_path, capsys):
    assert (
        main(
            [
                "suite",
                "scenarios",
                "--agent-factory",
                GOOD,
                "--max-tool-calls",
                "1",
                "--trials",
                "1",
                "--out",
                str(tmp_path),
            ]
        )
        == 1
    )
    summary = json.loads(capsys.readouterr().out)
    assert summary["total_trials"] == 8
    assert summary["counts"]["pass"] > 0
    assert summary["counts"]["agent_failure"] > 0
    assert summary["counts"]["harness_error"] == 0
    for trace in json.loads((tmp_path / "suite.json").read_text())["runs"]:
        saved(trace, tmp_path)


def test_factory_defaults_and_unpicklable_instance_error(tmp_path):
    trace = run_scenario(scenario(), agent_factory=GOOD, out=tmp_path)
    assert trace["configuration"]["execution_limits"] == {
        "timeout_seconds": 60.0,
        "max_tool_calls": 100,
    }

    class LocalTarget(ScriptedAgent):
        pass

    failed = saved(
        run_scenario(scenario(), agent=LocalTarget("corrected"), timeout_seconds=10, out=tmp_path),
        tmp_path,
    )
    assert failed["result"]["status"] == "harness_error"
    assert "pickle" in failed["result"]["error"].lower()


@pytest.mark.parametrize("path", sorted(Path("scenarios").glob("*.yaml")))
def test_bounded_builtin_keeps_financial_and_fault_behavior(path, tmp_path):
    fixture = load_scenario(path)
    inline = run_scenario(fixture, out=tmp_path)
    bounded = saved(run_scenario(fixture, timeout_seconds=10, out=tmp_path), tmp_path)
    assert bounded["result"] == inline["result"]
    assert bounded["final_state"] == inline["final_state"]
    assert bounded["fault_schedule"] == inline["fault_schedule"]
    assert bounded["responses"] == inline["responses"]


def test_exact_budget_passes_and_rerun_preserves_or_overrides_limits(tmp_path):
    trace = saved(
        run_scenario(scenario(), agent_factory=GOOD, max_tool_calls=1, out=tmp_path), tmp_path
    )
    assert trace["result"]["status"] == "pass"
    assert trace["execution_stop"] is None
    assert trace["agent"]["execution_metadata_complete"]
    again = saved(rerun(trace, agent_factory=GOOD, out=tmp_path), tmp_path)
    assert again["configuration"]["execution_limits"] == trace["configuration"]["execution_limits"]
    changed = rerun(trace, agent_factory=GOOD, max_tool_calls=4, timeout_seconds=10, out=tmp_path)
    assert changed["configuration"]["execution_limits"] == {
        "timeout_seconds": 10.0,
        "max_tool_calls": 4,
    }


def test_initialization_deadline_and_exception_are_harness_errors(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "stuck_factory.py").write_text(
        "import time\n"
        "def hang():\n    time.sleep(30)\n"
        "def fail():\n    raise RuntimeError('broken setup')\n"
    )
    fixture = load_scenario(Path(__file__).resolve().parents[1] / "scenarios/01_normal.yaml")
    for factory in ("stuck_factory:hang", "stuck_factory:fail"):
        trace = saved(
            run_scenario(fixture, agent_factory=factory, timeout_seconds=1, out=tmp_path), tmp_path
        )
        assert trace["result"]["status"] == "harness_error"
        assert trace["final_state"] == trace["initial_state"]
        assert trace["tool_events"] == []
        if factory.endswith("hang"):
            assert trace["execution_stop"]["phase"] == "initialization"
        else:
            assert "broken setup" in trace["result"]["error"]


def test_worker_crash_retains_backend_evidence(tmp_path):
    trace = saved(
        run_scenario(
            scenario(), agent=CrashAfterRefund("corrected"), timeout_seconds=10, out=tmp_path
        ),
        tmp_path,
    )
    assert trace["result"]["status"] == "harness_error"
    assert trace["execution_stop"] is None
    assert trace["final_state"]["refunds"][0]["amount_cents"] == 300
    assert not trace["agent"]["execution_metadata_complete"]


@pytest.mark.skipif(os.name != "posix", reason="POSIX SIGTERM behavior")
def test_worker_ignoring_terminate_is_killed(tmp_path):
    children = {p.pid for p in multiprocessing.active_children()}
    trace = saved(
        run_scenario(
            scenario(), agent=IgnoreTermination("corrected"), timeout_seconds=1, out=tmp_path
        ),
        tmp_path,
    )
    assert trace["result"]["status"] == "agent_failure"
    assert trace["final_state"]["refunds"][0]["amount_cents"] == 300
    assert {p.pid for p in multiprocessing.active_children()} == children


def test_suite_records_each_initialization_failure_and_continues(tmp_path, capsys):
    assert (
        main(
            [
                "suite",
                "scenarios/01_normal.yaml",
                "--agent-factory",
                "missing_target_module:make",
                "--trials",
                "2",
                "--out",
                str(tmp_path),
            ]
        )
        == 2
    )
    summary = json.loads(capsys.readouterr().out)
    assert summary["total_trials"] == 2
    assert summary["counts"]["harness_error"] == 2
    assert summary["counts"]["pass"] == 0
    for trace in json.loads((tmp_path / "suite.json").read_text())["runs"]:
        saved(trace, tmp_path)


@pytest.mark.parametrize("change", ["count", "blocked", "phase", "limits", "verdict"])
def test_tampered_stop_evidence_rejected(tmp_path, change):
    trace = run_scenario(scenario(), agent_factory=READS, max_tool_calls=1, out=tmp_path)
    bad = copy.deepcopy(trace)
    if change == "count":
        bad["execution_stop"]["completed_tool_calls"] = 0
    elif change == "blocked":
        bad["execution_stop"]["blocked_call"] = None
    elif change == "phase":
        bad["execution_stop"]["phase"] = "initialization"
    elif change == "limits":
        del bad["configuration"]["execution_limits"]
    else:
        bad["result"]["status"] = "pass"
    with pytest.raises(ValueError):
        validate_trace(bad)


@pytest.mark.parametrize(
    "seconds,calls",
    [(0, 1), (-1, 1), (float("nan"), 1), (float("inf"), 1), (True, 1), (1, 0), (1, True), (1, 1.5)],
)
def test_invalid_limits_rejected_before_run_creation(tmp_path, seconds, calls):
    with pytest.raises(ValueError):
        execution_limits(seconds, calls)
    with pytest.raises(ValueError):
        run_scenario(scenario(), timeout_seconds=seconds, max_tool_calls=calls, out=tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_legacy_trace_and_explicit_null_limits_rerun(tmp_path):
    legacy = run_scenario(scenario(), out=tmp_path)
    assert "execution_limits" not in legacy["configuration"]
    assert rerun(legacy, out=tmp_path)["result"]["status"] == "pass"
    legacy["configuration"]["execution_limits"] = None
    assert rerun(legacy, out=tmp_path)["result"]["status"] == "pass"


def test_bounded_provider_setup_failure_can_be_rerun(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    trace = saved(
        run_scenario(
            scenario(),
            provider="openai",
            model="unused-offline-test",
            timeout_seconds=10,
            out=tmp_path,
        ),
        tmp_path,
    )
    assert trace["result"]["status"] == "harness_error"
    assert rerun(trace, out=tmp_path)["result"]["status"] == "harness_error"
