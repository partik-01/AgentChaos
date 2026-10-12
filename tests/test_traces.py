import copy
import hashlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from agent_chaos.cli import main
from agent_chaos.runner import read_trace, rerun, run_scenario
from agent_chaos.schema import load_scenario
from agent_chaos.traces import Trace, validate_trace


@pytest.fixture
def recorded():
    return json.loads(Path("examples/timeout-flawed.json").read_text())


@pytest.mark.parametrize("path", sorted(Path("examples").glob("*.json")))
def test_existing_single_run_trace_contracts(path):
    data = json.loads(path.read_text())
    if "trace_version" in data:
        Trace.model_validate(data)
        assert validate_trace(data) is data


@pytest.mark.parametrize(
    "section",
    [
        "initial_state",
        "final_state",
        "messages",
        "configuration",
        "agent",
        "tool_events",
        "backend_events",
        "responses",
        "result",
        "trial_summary",
        "created_at",
        "source_commit",
        "scenario_sha256",
        "fault_schedule",
    ],
)
def test_missing_required_section_is_rejected(recorded, section):
    del recorded[section]
    with pytest.raises(ValidationError):
        Trace.model_validate(recorded)


@pytest.mark.parametrize(
    "section,field,value",
    [
        ("configuration", "seed", "17"),
        ("trial_summary", "failure_count", True),
        ("result", "status", "success"),
        ("agent", "cost_usd", float("inf")),
    ],
)
def test_bad_nested_types_are_rejected(recorded, section, field, value):
    recorded[section][field] = value
    with pytest.raises(ValidationError):
        Trace.model_validate(recorded)


def test_wrong_money_and_missing_event_fields_are_rejected(recorded):
    bad = copy.deepcopy(recorded)
    bad["final_state"]["refunds"][0]["amount_cents"] = "300"
    with pytest.raises(ValidationError):
        Trace.model_validate(bad)
    del recorded["tool_events"][0]["observed"]
    with pytest.raises(ValidationError):
        Trace.model_validate(recorded)


@pytest.mark.parametrize("timestamp", ["yesterday", "2026-10-12T10:00:00"])
def test_timestamp_requires_iso_format_and_timezone(recorded, timestamp):
    recorded["created_at"] = timestamp
    with pytest.raises(ValidationError):
        Trace.model_validate(recorded)


@pytest.mark.parametrize(
    "path,value,error",
    [
        (("scenario_sha256",), "0" * 64, "hash mismatch"),
        (("scenario", "description"), "changed", "hash mismatch"),
        (("messages", 0, "messages", 0, "text"), "changed", "match scenario turns"),
        (("configuration", "seed"), 99, "match scenario seed"),
        (("agent", "version"), "corrected", "match configuration"),
        (("agent", "kind"), "llm", "configured provider"),
        (("fault_schedule", 0, "draw"), 0.1, "match scenario and seed"),
        (("fault_schedule", 0, "enabled"), False, "match scenario and seed"),
        (("tool_events", 0, "index"), 1, "contiguous"),
        (("tool_events", 1, "occurrence"), 2, "tool occurrence"),
        (("tool_events", 1, "fault"), None, "scheduled invocation"),
        (("tool_events", 1, "phase"), "before", "execution phase"),
        (("tool_events", 1, "observed", "executed"), False, "fault semantics"),
        (("tool_events", 1, "backend_result", "amount_cents"), 200, "prior ledger"),
        (("tool_events", 1, "backend_events"), [], "backend effects"),
        (("backend_events",), [], "ordered tool backend events"),
        (("final_state", "refunds", 0, "amount_cents"), 200, "not explained"),
        (("responses", 0, "turn"), 1, "contiguous scenario prefix"),
        (("responses", 0, "tool_event_end"), 999, "event boundary"),
        (("result", "violations", 0, "event_indices"), [999], "missing event"),
        (("result", "status"), "pass", "verdict disagrees"),
        (("result", "expected_intents", 0, "expected_cents"), 0, "verdict disagrees"),
        (("trial_summary", "failure_count"), 0, "single-run result"),
        (("tool_events", 0, "latency_ms"), float("nan"), "invalid trace structure"),
    ],
)
def test_inconsistent_evidence_is_rejected(recorded, path, value, error):
    target = recorded
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(ValueError, match=error):
        validate_trace(recorded)


def test_duplicate_ledger_identifiers_and_missing_references(recorded):
    bad = copy.deepcopy(recorded)
    bad["initial_state"]["payments"].append(bad["initial_state"]["payments"][0])
    with pytest.raises(ValueError, match="duplicate payment_id"):
        validate_trace(bad)
    bad = copy.deepcopy(recorded)
    bad["final_state"]["refunds"][1]["idempotency_key"] = bad["final_state"]["refunds"][0][
        "idempotency_key"
    ]
    with pytest.raises(ValueError, match="duplicate idempotency key"):
        validate_trace(bad)
    recorded["final_state"]["refunds"][0]["payment_id"] = "missing"
    with pytest.raises(ValueError, match="missing payment"):
        validate_trace(recorded)


@pytest.mark.parametrize("version", ["flawed", "corrected"])
@pytest.mark.parametrize("path", sorted(Path("scenarios").glob("**/*.yaml")))
def test_current_scenarios_and_business_failures_are_valid_traces(tmp_path, version, path):
    data = run_scenario(load_scenario(path), version, out=tmp_path)
    before = copy.deepcopy(data)
    validate_trace(data)
    assert data == before


def test_partial_provider_failure_and_invalid_output_remain_readable(tmp_path):
    from agent_chaos.agents import AgentFailure

    class Broken:
        metadata = {"conversation_assessment": "unassessed"}

        def run_turn(self, turn, tools):
            m = turn.messages[0]
            tools.call(
                "create_refund",
                {
                    "payment_id": m.payment_id,
                    "customer_id": m.customer_id,
                    "amount_cents": m.amount_cents,
                    "request_id": m.request_id,
                    "idempotency_key": "one",
                },
            )
            raise RuntimeError("provider unavailable after commit")

    scenario = load_scenario("scenarios/01_normal.yaml")
    trace = run_scenario(scenario, agent=Broken(), out=tmp_path)
    assert trace["result"]["status"] == "harness_error"
    validate_trace(trace)

    class Invalid(Broken):
        def run_turn(self, turn, tools):
            raise AgentFailure("bad customer response")

    trace = run_scenario(scenario, agent=Invalid(), out=tmp_path)
    assert trace["result"]["status"] == "agent_failure"
    validate_trace(trace)


def test_rejected_unknown_tool_and_bad_arguments_are_recorded_behavior(tmp_path):
    class InvalidCalls:
        metadata = {"conversation_assessment": "unassessed"}

        def run_turn(self, turn, tools):
            tools.call("unknown", {})
            tools.call("create_refund", {"amount_cents": "bad"})
            return []

    trace = run_scenario(
        load_scenario("scenarios/01_normal.yaml"), agent=InvalidCalls(), out=tmp_path
    )
    assert trace["result"]["status"] == "agent_failure"
    validate_trace(trace)


@pytest.mark.parametrize("command", ["inspect", "playback", "export", "rerun", "minimize"])
def test_invalid_trace_cli_stops_before_execution_or_output(
    tmp_path, recorded, monkeypatch, capsys, command
):
    recorded["scenario_sha256"] = "0" * 64
    path = tmp_path / "damaged.json"
    path.write_text(json.dumps(recorded))
    out = tmp_path / "should-not-exist"

    def forbidden(*args, **kwargs):
        pytest.fail("invalid trace reached execution or export")

    monkeypatch.setattr("agent_chaos.runner.run_scenario", forbidden)
    monkeypatch.setattr("agent_chaos.cli.save_bundle", forbidden)
    argv = [command, str(path)]
    if command == "export":
        argv += ["--output", str(out / "report.json")]
    elif command in ("rerun", "minimize"):
        argv += ["--out", str(out)]
    assert main(argv) == 2
    assert "scenario hash mismatch" in capsys.readouterr().err
    assert not out.exists()


def test_direct_rerun_validates_before_run_directory_or_agent_creation(
    tmp_path, recorded, monkeypatch
):
    del recorded["initial_state"]

    def forbidden(*args, **kwargs):
        pytest.fail("invalid trace reached the runner")

    monkeypatch.setattr("agent_chaos.runner.run_scenario", forbidden)
    out = tmp_path / "should-not-exist"
    with pytest.raises(ValueError, match="initial_state"):
        rerun(recorded, out=out, provider="openai", model="must-not-call")
    assert not out.exists()


@pytest.mark.parametrize(
    "contents",
    [
        '{"trace_version": 1, "trace_version": 1}',
        '{"scenario": {"seed": 1, "seed": 2}}',
        "[]",
        "null",
        "true",
        "{broken",
        '{"trace_version": NaN}',
    ],
)
def test_invalid_json_roots_and_duplicate_keys_are_rejected(tmp_path, contents):
    path = tmp_path / "invalid.json"
    path.write_text(contents)
    with pytest.raises(ValueError):
        read_trace(path)


def test_directory_read_and_round_trip_preserve_original_evidence(tmp_path, recorded):
    directory = tmp_path / "recorded"
    directory.mkdir()
    path = directory / "trace.json"
    path.write_text(json.dumps(recorded, indent=2))
    before = path.read_bytes()
    assert read_trace(directory) == recorded
    assert path.read_bytes() == before
    fixed = rerun(recorded, agent_version="corrected", out=tmp_path / "rerun")
    assert fixed["result"]["status"] == "pass"
    assert fixed["initial_state"] == recorded["initial_state"]
    assert recorded["result"]["status"] == "agent_failure"


def test_edited_customer_prose_cannot_be_labeled_verified_templates(recorded):
    recorded["responses"][0]["claims"][0]["text"] = "No refund occurred."
    recorded["result"]["conversation_assessment"]["evidence"] = ["No refund occurred."]
    with pytest.raises(ValueError, match="deterministic claim template"):
        validate_trace(recorded)


@pytest.mark.parametrize("value", ["17", True, 17.0])
def test_nested_scenario_fields_are_strict_even_with_updated_hash(recorded, value):
    recorded["scenario"]["seed"] = value
    recorded["scenario_sha256"] = hashlib.sha256(
        json.dumps(recorded["scenario"], sort_keys=True).encode()
    ).hexdigest()
    with pytest.raises(ValueError, match="invalid trace structure"):
        validate_trace(recorded)


def test_recorded_scenario_cannot_silently_default_its_version(recorded):
    del recorded["scenario"]["version"]
    recorded["scenario_sha256"] = hashlib.sha256(
        json.dumps(recorded["scenario"], sort_keys=True).encode()
    ).hexdigest()
    with pytest.raises(ValueError, match="missing recorded scenario fields"):
        validate_trace(recorded)


@pytest.mark.parametrize("seed", range(5))
def test_probabilistic_read_fault_schedules_remain_valid(tmp_path, seed):
    from agent_chaos.schema import Fault

    scenario = load_scenario("scenarios/01_normal.yaml").model_copy(
        update={
            "seed": seed,
            "faults": [Fault(tool="get_payment", kind="after_timeout", probability=0.5)],
        }
    )
    validate_trace(run_scenario(scenario, out=tmp_path))


def test_existing_refunds_and_long_visibility_uncertainty_remain_valid(tmp_path):
    from agent_chaos.schema import Fault

    scenario = load_scenario("scenarios/01_normal.yaml")
    initial = {
        "payments": [p.model_dump() for p in scenario.payments],
        "refunds": [
            {
                "refund_id": "rf_000001",
                "payment_id": "pay_alice",
                "customer_id": "alice",
                "amount_cents": 100,
                "idempotency_key": "previous",
                "request_id": "previous",
                "status": "succeeded",
            }
        ],
    }
    trace = run_scenario(scenario, initial=initial, out=tmp_path)
    assert trace["result"]["status"] == "pass"
    validate_trace(trace)
    scenario = scenario.model_copy(
        update={
            "faults": [
                Fault(kind="visibility_delay", hidden_reads=100),
                Fault(kind="after_timeout", occurrence=2),
                Fault(kind="malformed", occurrence=3),
            ]
        }
    )
    trace = run_scenario(scenario, out=tmp_path)
    assert trace["result"]["status"] == "inconclusive"
    validate_trace(trace)


def test_agent_setup_error_remains_valid_without_model_api_call(tmp_path):
    trace = run_scenario(load_scenario("scenarios/01_normal.yaml"), provider="openai", out=tmp_path)
    assert trace["result"]["status"] == "harness_error"
    assert trace["tool_events"] == trace["responses"] == []
    validate_trace(trace)


def test_decreasing_response_boundary_and_false_harness_classification_are_rejected(tmp_path):
    trace = run_scenario(load_scenario("scenarios/07_repeated_request.yaml"), out=tmp_path)
    trace["responses"][1]["tool_event_end"] = 0
    with pytest.raises(ValueError, match="event boundary"):
        validate_trace(trace)
    trace = run_scenario(load_scenario("scenarios/01_normal.yaml"), out=tmp_path)
    trace["result"]["error"] = "invented provider error"
    with pytest.raises(ValueError, match="only harness errors"):
        validate_trace(trace)
