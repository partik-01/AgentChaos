"""Version-1 recorded evidence contracts; validation never executes tools or models."""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import ConfigDict, Field, JsonValue, StrictBool, StrictInt, field_validator

from .schema import Claim, CreateRefund, Fault, Identifier, Payment, Scenario, StrictModel, Turn

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
    total_trials: Literal[1]
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
