"""Version-1 recorded evidence contracts; validation never executes tools or models."""

import hashlib
import json
import random
import shlex
from collections import Counter
from datetime import datetime
from typing import Annotated, Literal

from pydantic import (
    ConfigDict,
    Field,
    JsonValue,
    StrictBool,
    StrictInt,
    ValidationError,
    field_validator,
)

from .schema import (
    TOOL_MODELS,
    Claim,
    CreateRefund,
    Fault,
    Identifier,
    Payment,
    Scenario,
    StrictModel,
    Turn,
)
from .verifier import verify

TRACE_VERSION = 1
Count = Annotated[StrictInt, Field(ge=0)]
Duration = Annotated[float, Field(ge=0, allow_inf_nan=False)]
JsonObject = dict[str, JsonValue]


class Record(StrictModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Refund(CreateRefund):
    refund_id: Identifier
    status: Literal["succeeded"]


class State(Record):
    payments: list[Payment]
    refunds: list[Refund]


class ScheduledFault(Fault):
    draw: Annotated[float, Field(ge=0, lt=1, allow_inf_nan=False)]
    enabled: StrictBool


class BackendEvent(Record):
    kind: Literal["refund_committed", "idempotent_replay"]
    refund: Refund


class ToolEvent(Record):
    index: Count
    tool: Annotated[str, Field(min_length=1)]
    occurrence: Annotated[StrictInt, Field(ge=1)]
    arguments: JsonObject
    fault: ScheduledFault | None
    phase: Literal["validation", "before", "execution", "after"]
    backend_result: JsonObject | None
    backend_events: list[BackendEvent]
    observed: JsonObject
    latency_ms: Duration


class Response(Record):
    turn: Count
    claims: list[Claim]
    tool_event_end: Count


class Configuration(Record):
    provider: Literal["scripted", "openai"]
    agent_version: Literal["flawed", "corrected"]
    model: str | None
    seed: StrictInt


class Usage(Record):
    input_tokens: Count
    output_tokens: Count


class ModelCall(Record):
    response: JsonObject
    latency_ms: Duration
    usage: JsonObject


class AgentMetadata(Record):
    # Custom agents and raw provider responses can add metadata without a trace version bump.
    model_config = ConfigDict(extra="allow", strict=True)
    __pydantic_extra__: dict[str, JsonValue] = Field(init=False)
    kind: str | None = None
    version: str | None = None
    model: str | None = None
    usage: Usage | None = None
    cost_usd: Duration | None = None
    conversation_assessment: str
    prompt: str | None = None
    prompt_version: str | None = None
    model_calls: list[ModelCall] | None = None


class Violation(Record):
    rule: Annotated[str, Field(min_length=1)]
    expected: JsonValue
    observed: JsonValue
    event_indices: list[Count]


class Intent(Record):
    request_id: Identifier
    payment_id: Identifier
    customer_id: Identifier
    amount_cents: Annotated[StrictInt, Field(gt=0)]
    text: str
    expected_cents: Count


class ConversationAssessment(Record):
    status: Literal["verified_templates", "unassessed"]
    evidence: list[str]
    uncertainty: str | None


class Result(Record):
    status: Literal["pass", "agent_failure", "harness_error", "inconclusive"]
    violations: list[Violation]
    expected_intents: list[Intent]
    conversation_assessment: ConversationAssessment
    error: Annotated[str, Field(min_length=1)] | None = None


class TrialSummary(Record):
    total_trials: Annotated[StrictInt, Field(ge=1, le=1)]
    failure_count: Count


class Trace(Record):
    trace_version: Literal[1]
    run_id: Identifier
    parent_run: Identifier | None
    created_at: str
    package_version: Annotated[str, Field(min_length=1)]
    source_commit: Annotated[str, Field(min_length=1)]
    scenario: Scenario
    scenario_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    initial_state: State
    messages: list[Turn]
    agent: AgentMetadata
    configuration: Configuration
    fault_schedule: list[ScheduledFault]
    tool_events: list[ToolEvent]
    backend_events: list[BackendEvent]
    responses: list[Response]
    final_state: State
    result: Result
    latency_ms: Duration
    reproduction_command: Annotated[str, Field(min_length=1)]
    trial_summary: TrialSummary
    export_note: str | None = None

    @field_validator("created_at")
    @classmethod
    def timezone_required(cls, value):
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError as exc:
            raise ValueError("created_at must be an ISO timestamp") from exc
        if parsed.utcoffset() is None:
            raise ValueError("created_at must include a timezone")
        return value


def require(condition, location, message):
    if not condition:
        raise ValueError(f"invalid trace at {location}: {message}")


def check_state(state, location):
    for table, field in (("payments", "payment_id"), ("refunds", "refund_id")):
        ids = [r[field] for r in state[table]]
        require(len(ids) == len(set(ids)), location, f"duplicate {field}")
    keys = [r["idempotency_key"] for r in state["refunds"]]
    require(len(keys) == len(set(keys)), location, "duplicate idempotency key")
    payments = {p["payment_id"] for p in state["payments"]}
    require(
        all(r["payment_id"] in payments for r in state["refunds"]),
        location,
        "refund references a missing payment",
    )


def authoritative_result(tool, args, payments, refunds):
    """Interpret ledger evidence in memory, without invoking the payment API."""
    if tool == "get_refund_status":
        return next(
            (r for r in refunds if r["idempotency_key"] == args["idempotency_key"]),
            {"status": "not_found", "idempotency_key": args["idempotency_key"]},
        ), None
    if tool == "create_refund":
        existing = next(
            (r for r in refunds if r["idempotency_key"] == args["idempotency_key"]), None
        )
        if existing:
            if any(existing[k] != args[k] for k in args):
                return None, "idempotency_conflict"
            return existing, "idempotent_replay"
    payment = payments.get(args["payment_id"])
    if payment is None:
        return None, "payment_not_found"
    if payment["customer_id"] != args["customer_id"]:
        return None, "customer_mismatch"
    refunded = sum(r["amount_cents"] for r in refunds if r["payment_id"] == args["payment_id"])
    if tool == "get_payment":
        return payment | {
            "refunded_cents": refunded,
            "remaining_cents": payment["amount_cents"] - refunded,
        }, None
    if tool == "list_refunds":
        return {
            "refunds": sorted(
                [r for r in refunds if r["payment_id"] == args["payment_id"]],
                key=lambda r: r["refund_id"],
            )
        }, None
    if args["amount_cents"] > payment["amount_cents"] - refunded:
        return None, "insufficient_balance"
    return args | {
        "refund_id": f"rf_{len(refunds) + 1:06d}",
        "status": "succeeded",
    }, "refund_committed"


def check_events(data):
    initial = data["initial_state"]
    payments = {p["payment_id"]: p for p in initial["payments"]}
    refunds = list(initial["refunds"])
    hidden = {}
    counts = Counter()
    flattened = []
    for index, event in enumerate(data["tool_events"]):
        where = f"tool_events[{index}]"
        tool, args = event["tool"], event["arguments"]
        counts[tool] += 1
        require(event["index"] == index, where, "indices must be contiguous from zero")
        require(event["occurrence"] == counts[tool], where, "incorrect tool occurrence")
        fault = next(
            (
                f
                for f in data["fault_schedule"]
                if f["tool"] == tool and f["occurrence"] == counts[tool] and f["enabled"]
            ),
            None,
        )
        require(event["fault"] == fault, where, "fault does not match scheduled invocation")
        try:
            if tool not in TOOL_MODELS:
                raise ValueError("unknown tool")
            TOOL_MODELS[tool].model_validate(args)
        except ValueError:
            require(event["phase"] == "validation", where, "invalid call must fail validation")
            require(
                event["observed"].get("error") == "invalid_arguments"
                and event["observed"].get("executed") is False
                and isinstance(event["observed"].get("detail"), str),
                where,
                "invalid call requires a rejected argument observation",
            )
            result, backend, observed, phase = None, [], event["observed"], "validation"
        else:
            result, backend = None, []
            if fault and fault["kind"] in ("before_failure", "rate_limit"):
                observed = {
                    "error": "unavailable" if fault["kind"] == "before_failure" else "rate_limited",
                    "executed": False,
                    "retry_after_ms": 100,
                }
                phase = "before"
            else:
                result, effect = authoritative_result(tool, args, payments, refunds)
                if result is None:
                    phase = "execution"
                    observed = {"error": effect, "executed": False}
                else:
                    phase = "after"
                    if effect:
                        backend = [{"kind": effect, "refund": result}]
                        if effect == "refund_committed":
                            refunds.append(result)
                    if fault and fault["kind"] == "visibility_delay":
                        hidden[result["idempotency_key"]] = fault["hidden_reads"]
                        observed = {
                            "status": "pending",
                            "idempotency_key": result["idempotency_key"],
                        }
                    elif fault and fault["kind"] == "after_timeout":
                        observed = {"error": "timeout", "executed": "unknown"}
                    elif fault and fault["kind"] == "malformed":
                        observed = {
                            "raw": "{broken-json",
                            "error": "malformed_response",
                            "executed": "unknown",
                        }
                    elif tool in ("get_refund_status", "list_refunds"):
                        keys = (
                            [result["idempotency_key"]]
                            if tool == "get_refund_status"
                            else [r["idempotency_key"] for r in result["refunds"]]
                        )
                        obscured = {key for key in keys if hidden.get(key, 0) > 0}
                        for key in obscured:
                            hidden[key] -= 1
                        observed = (
                            {"status": "not_found", "idempotency_key": result["idempotency_key"]}
                            if tool == "get_refund_status" and obscured
                            else {
                                "refunds": [
                                    r
                                    for r in result["refunds"]
                                    if r["idempotency_key"] not in obscured
                                ]
                            }
                            if tool == "list_refunds"
                            else result
                        )
                    else:
                        observed = result
        require(event["phase"] == phase, where, "incorrect execution phase")
        require(
            event["backend_result"] == result,
            where,
            "authoritative result disagrees with prior ledger",
        )
        require(
            event["backend_events"] == backend, where, "backend effects do not explain operation"
        )
        require(event["observed"] == observed, where, "observation disagrees with fault semantics")
        flattened.extend(backend)
    require(
        data["backend_events"] == flattened,
        "backend_events",
        "must equal ordered tool backend events",
    )
    require(
        data["final_state"]["payments"] == initial["payments"],
        "final_state",
        "unexplained payment changes",
    )
    require(
        sorted(refunds, key=lambda r: r["refund_id"]) == data["final_state"]["refunds"],
        "final_state",
        "refund ledger is not explained by backend events",
    )


def validate_trace(data: dict) -> dict:
    """Return original evidence unchanged after structural and consistency validation."""
    require(isinstance(data, dict), "root", "expected a single-run JSON object")
    require(
        type(data.get("trace_version")) is int and data["trace_version"] == TRACE_VERSION,
        "trace_version",
        "unsupported trace version",
    )
    try:
        json.dumps(data, allow_nan=False)
        parsed = Trace.model_validate(data)
    except (ValidationError, ValueError, TypeError) as exc:
        raise ValueError(f"invalid trace structure: {exc}") from exc
    digest = hashlib.sha256(json.dumps(data["scenario"], sort_keys=True).encode()).hexdigest()
    require(data["scenario_sha256"] == digest, "scenario_sha256", "scenario hash mismatch")
    require(data["messages"] == data["scenario"]["turns"], "messages", "must match scenario turns")
    config = data["configuration"]
    require(
        config["seed"] == parsed.scenario.seed, "configuration.seed", "must match scenario seed"
    )
    agent = data["agent"]
    for field, expected in (("version", config["agent_version"]), ("model", config["model"])):
        if field in agent:
            require(agent[field] == expected, f"agent.{field}", "must match configuration")
    if agent.get("kind") in ("scripted", "llm"):
        require(
            config["provider"] == ("scripted" if agent["kind"] == "scripted" else "openai"),
            "agent.kind",
            "must match configured provider",
        )
        require(
            all(
                k in agent
                for k in ("version", "model", "usage", "cost_usd", "prompt", "prompt_version")
            ),
            "agent",
            "built-in agents require version, model, usage, cost and prompt metadata",
        )
        require(
            isinstance(agent["prompt"], str) and isinstance(agent["prompt_version"], str),
            "agent.prompt",
            "prompt metadata must be strings",
        )
    if "model_calls" in agent:
        require(
            isinstance(agent["model_calls"], list), "agent.model_calls", "expected recorded calls"
        )
        totals = {"input_tokens": 0, "output_tokens": 0}
        for index, call in enumerate(agent["model_calls"]):
            require(
                call["usage"] == (call["response"].get("usage") or {}),
                f"agent.model_calls[{index}].usage",
                "must match provider response usage",
            )
            for key in totals:
                number = call["usage"].get(key, 0)
                require(
                    type(number) is int and number >= 0,
                    f"agent.model_calls[{index}].usage.{key}",
                    "expected nonnegative tokens",
                )
                totals[key] += number
        require(agent.get("usage") == totals, "agent.usage", "must sum recorded model calls")
    try:
        command = shlex.split(data["reproduction_command"])
    except ValueError as exc:
        raise ValueError("invalid trace at reproduction_command: invalid quoting") from exc
    require(
        len(command) == 3 and command[:2] == ["agent-chaos", "rerun"] and bool(command[2]),
        "reproduction_command",
        "expected an agent-chaos rerun command with one trace path",
    )
    rng = random.Random(parsed.scenario.seed)
    schedule = []
    for f in parsed.scenario.faults:
        draw = rng.random()
        schedule.append(f.model_dump() | {"draw": draw, "enabled": draw < f.probability})
    require(
        data["fault_schedule"] == schedule, "fault_schedule", "does not match scenario and seed"
    )
    for name in ("initial_state", "final_state"):
        check_state(data[name], name)
    check_events(data)
    end = 0
    for index, response in enumerate(data["responses"]):
        require(
            response["turn"] == index and index < len(parsed.scenario.turns),
            f"responses[{index}].turn",
            "turns must be a contiguous scenario prefix",
        )
        require(
            end <= response["tool_event_end"] <= len(data["tool_events"]),
            f"responses[{index}].tool_event_end",
            "invalid or decreasing event boundary",
        )
        end = response["tool_event_end"]
    for violation in data["result"]["violations"]:
        require(
            all(i < len(data["tool_events"]) for i in violation["event_indices"]),
            "result.violations.event_indices",
            "references a missing event",
        )
    result = data["result"]
    require(
        (result["status"] == "harness_error") == bool(result.get("error")),
        "result.error",
        "only harness errors require an error message",
    )
    expected = verify(
        parsed.scenario,
        data["initial_state"],
        data["final_state"],
        data["tool_events"],
        data["responses"],
        harness_error=result.get("error"),
        conversation_assessment=agent["conversation_assessment"],
    )
    invalid_output = [v for v in result["violations"] if v["rule"] == "agent_output_valid"]
    if invalid_output:
        require(
            len(invalid_output) == 1 and not result.get("error"),
            "result.violations",
            "invalid agent error classification",
        )
        item = invalid_output[0]
        require(
            item["expected"] == "valid final customer claims within the configured step budget"
            and isinstance(item["observed"], str)
            and bool(item["observed"])
            and item["event_indices"] == list(range(len(data["tool_events"]))),
            "result.violations.agent_output_valid",
            "invalid output-error evidence",
        )
        expected["status"] = "agent_failure"
        expected.pop("error", None)
        expected["violations"].append(item)
        expected["conversation_assessment"] = {
            "status": "unassessed",
            "evidence": [],
            "uncertainty": "invalid agent response",
        }
    require(result == expected, "result", "recorded verdict disagrees with deterministic evidence")
    if result["status"] in ("pass", "inconclusive"):
        require(
            len(data["responses"]) == len(parsed.scenario.turns)
            and end == len(data["tool_events"]),
            "responses",
            "successful execution requires all turns and final event coverage",
        )
    require(
        data["trial_summary"]
        == {"total_trials": 1, "failure_count": int(result["status"] == "agent_failure")},
        "trial_summary",
        "must agree with the single-run result",
    )
    return data
