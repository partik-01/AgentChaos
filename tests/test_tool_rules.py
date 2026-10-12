import copy
import hashlib
import json

import pytest
from pydantic import TypeAdapter, ValidationError

from agent_chaos.agents import claim
from agent_chaos.cli import main
from agent_chaos.reports import render_html
from agent_chaos.runner import read_trace, rerun, run_scenario
from agent_chaos.schema import Scenario, ToolRule, load_scenario
from agent_chaos.tool_rules import check_tool_rules
from agent_chaos.traces import validate_trace


def rule(kind, **kwargs):
    return TypeAdapter(ToolRule).validate_python({"id": "policy", "kind": kind, **kwargs})


def event(index, tool="create_refund", **args):
    return {
        "index": index,
        "tool": tool,
        "arguments": args,
        "observed": {"error": "timeout"},
        "backend_events": [],
    }


def test_order_requires_earlier_matching_payment_and_customer():
    policy = rule(
        "call_order",
        before="get_payment",
        after="create_refund",
        match_fields=["payment_id", "customer_id"],
    )
    calls = [
        event(0, "get_payment", payment_id="other", customer_id="alice"),
        event(1, payment_id="p", customer_id="alice"),
        event(2, "get_payment", payment_id="p", customer_id="alice"),
        event(3, payment_id="p", customer_id="alice"),
    ]
    failures = check_tool_rules([policy], calls)
    assert len(failures) == 1
    assert failures[0]["event_indices"] == [1]
    assert failures[0]["expected"]["matching_arguments"] == {
        "payment_id": "p",
        "customer_id": "alice",
    }
    assert not check_tool_rules([policy], calls[2:])  # An earlier faulted attempt counts.


def test_order_empty_matching_is_global_and_zero_after_calls_is_allowed():
    policy = rule("call_order", before="get_payment", after="create_refund")
    assert not check_tool_rules([policy], [])
    assert not check_tool_rules([policy], [event(0, "get_payment"), event(1)])
    assert check_tool_rules([policy], [event(0), event(1, "get_payment")])[0]["event_indices"] == [
        0
    ]


def test_max_counts_attempts_and_groups_requests_including_zero_limit():
    calls = [event(0, request_id="a"), event(1, request_id="b"), event(2, request_id="a")]
    assert not check_tool_rules(
        [rule("max_calls", tool="create_refund", max=2, group_by=["request_id"])], calls
    )
    failure = check_tool_rules(
        [rule("max_calls", tool="create_refund", max=1, group_by=["request_id"])], calls
    )[0]
    assert failure["event_indices"] == [0, 2]
    assert failure["observed"] == {"call_count": 2}
    assert check_tool_rules([rule("max_calls", tool="create_refund", max=0)], calls)[0][
        "observed"
    ] == {"call_count": 3}
    assert not check_tool_rules([rule("max_calls", tool="get_payment", max=0)], calls)


def test_consistency_uses_first_call_exact_values_and_separate_requests():
    policy = rule(
        "consistent_args",
        tool="create_refund",
        fields=["idempotency_key", "amount_cents"],
        group_by=["request_id"],
    )
    calls = [
        event(0, request_id="a", idempotency_key="one", amount_cents=300),
        event(1, request_id="b", idempotency_key="two", amount_cents=500),
        event(2, request_id="a", idempotency_key="one", amount_cents=300),
        event(3, request_id="a", idempotency_key="new", amount_cents=300),
    ]
    failure = check_tool_rules([policy], calls)[0]
    assert failure["event_indices"] == [0, 3]
    assert failure["expected"]["arguments"] == {"idempotency_key": "one", "amount_cents": 300}
    assert not check_tool_rules([policy], calls[:3])
    calls[0]["arguments"]["amount_cents"] = 1
    calls[2]["arguments"]["amount_cents"] = 1
    calls[3]["arguments"] = calls[0]["arguments"] | {"amount_cents": True}
    assert check_tool_rules([policy], calls)


@pytest.mark.parametrize(
    "policy",
    [
        rule(
            "call_order", before="get_payment", after="create_refund", match_fields=["payment_id"]
        ),
        rule("max_calls", tool="create_refund", max=3, group_by=["request_id"]),
        rule("consistent_args", tool="create_refund", fields=["idempotency_key"]),
    ],
)
def test_missing_fields_in_invalid_calls_are_not_skipped(policy):
    failure = check_tool_rules([policy], [event(0)])[0]
    assert failure["event_indices"] == [0]
    assert failure["observed"]["missing_arguments"]


def test_nested_invalid_values_can_be_grouped_without_crashing():
    policy = rule("max_calls", tool="create_refund", max=1, group_by=["request_id"])
    assert check_tool_rules([policy], [event(0, request_id=[]), event(1, request_id=[])])


@pytest.mark.parametrize(
    "data",
    [
        {"kind": "unknown"},
        {"kind": "max_calls", "tool": "unknown", "max": 3},
        {"kind": "max_calls", "tool": "create_refund", "max": -1},
        {"kind": "max_calls", "tool": "create_refund", "max": True},
        {"kind": "max_calls", "tool": "create_refund", "max": "3"},
        {"kind": "max_calls", "tool": "create_refund", "max": 3, "group_by": ["typo"]},
        {
            "kind": "max_calls",
            "tool": "create_refund",
            "max": 3,
            "group_by": ["request_id", "request_id"],
        },
        {"kind": "max_calls", "tool": "create_refund", "max": 3, "extra": 1},
        {"kind": "call_order", "before": "create_refund", "after": "create_refund"},
        {
            "kind": "call_order",
            "before": "get_payment",
            "after": "create_refund",
            "match_fields": ["request_id"],
        },
        {"kind": "consistent_args", "tool": "create_refund", "fields": []},
        {
            "kind": "consistent_args",
            "tool": "create_refund",
            "fields": ["idempotency_key"],
            "group_by": ["idempotency_key"],
        },
    ],
)
def test_bad_rule_configuration_is_rejected(data):
    with pytest.raises(ValidationError):
        TypeAdapter(ToolRule).validate_python({"id": "bad", **data})


def policy_scenario():
    return load_scenario("scenarios/tool_rules/refund_policy.yaml")


def test_duplicate_ids_rejected_before_execution():
    data = policy_scenario().model_dump()
    data["tool_rules"][1]["id"] = data["tool_rules"][0]["id"]
    with pytest.raises(ValidationError, match="unique"):
        Scenario.model_validate(data)


class TooManyCalls:
    metadata = {
        "kind": "custom",
        "version": "policy-test",
        "conversation_assessment": "deterministic_templates",
    }

    def run_turn(self, turn, tools):
        message = turn.messages[-1]
        args = {
            k: getattr(message, k)
            for k in ("request_id", "payment_id", "customer_id", "amount_cents")
        } | {"idempotency_key": "stable"}
        for _ in range(4):
            tools.call("create_refund", args)
        return [claim(message, "completed")]


def test_financially_correct_run_can_fail_policy_and_corrected_rerun_passes(tmp_path):
    trace = run_scenario(
        policy_scenario(), "policy-test", agent=TooManyCalls(), provider="custom", out=tmp_path
    )
    assert trace["result"]["status"] == "agent_failure"
    assert {v["rule"] for v in trace["result"]["violations"]} == {
        "tool_rule:check-payment-first",
        "tool_rule:bounded-refund-attempts",
    }
    assert sum(r["amount_cents"] for r in trace["final_state"]["refunds"]) == 300
    recorded = read_trace(tmp_path / trace["run_id"])
    assert "tool_rule:bounded-refund-attempts" in render_html(recorded)
    fixed = rerun(recorded, provider="scripted", agent_version="corrected", out=tmp_path)
    assert fixed["result"]["status"] == "pass"
    assert fixed["scenario"]["tool_rules"] == recorded["scenario"]["tool_rules"]
    validate_trace(fixed)
    changed = copy.deepcopy(trace)
    changed["result"]["violations"] = []
    changed["result"]["status"] = "pass"
    changed["trial_summary"]["failure_count"] = 0
    with pytest.raises(ValueError, match="verdict"):
        validate_trace(changed)


def test_old_trace_compatibility_and_added_policy_requires_reverification(tmp_path):
    original = read_trace("examples/timeout-corrected.json")
    assert "tool_rules" not in original["scenario"]
    altered = copy.deepcopy(original)
    altered["scenario"]["tool_rules"] = [
        {"id": "forbid", "kind": "max_calls", "tool": "create_refund", "max": 0}
    ]
    altered["scenario_sha256"] = hashlib.sha256(
        json.dumps(altered["scenario"], sort_keys=True).encode()
    ).hexdigest()
    with pytest.raises(ValueError, match="verdict"):
        validate_trace(altered)
    fresh = rerun(original, out=tmp_path)
    validate_trace(fresh)


def test_custom_cli_target_exposes_order_policy_violation(tmp_path, capsys):
    assert (
        main(
            [
                "run",
                "scenarios/tool_rules/refund_policy.yaml",
                "--agent-factory",
                "examples.custom_agent:make_corrected_agent",
                "--out",
                str(tmp_path),
            ]
        )
        == 1
    )
    output = json.loads(capsys.readouterr().out)
    assert {v["rule"] for v in output["violations"]} == {"tool_rule:check-payment-first"}
    assert main(["inspect", str(tmp_path / output["run_id"])]) == 0


def test_policy_failures_do_not_mask_harness_errors(tmp_path):
    class Broken(TooManyCalls):
        def run_turn(self, turn, tools):
            super().run_turn(turn, tools)
            raise RuntimeError("broken adapter")

    trace = run_scenario(
        policy_scenario(), "policy-test", agent=Broken(), provider="custom", out=tmp_path
    )
    assert trace["result"]["status"] == "harness_error"
    assert any(v["rule"].startswith("tool_rule:") for v in trace["result"]["violations"])
    validate_trace(trace)
