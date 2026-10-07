"""Strict, versioned scenario and tool contracts. Money is always integer cents."""

from pathlib import Path
from typing import Annotated, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator

Cents = Annotated[StrictInt, Field(gt=0)]
Identifier = Annotated[str, Field(min_length=1, max_length=200)]
ToolName = Literal["get_payment", "create_refund", "get_refund_status", "list_refunds"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Payment(StrictModel):
    payment_id: Identifier
    customer_id: Identifier
    amount_cents: Cents


class Message(StrictModel):
    request_id: Identifier
    payment_id: Identifier
    customer_id: Identifier
    amount_cents: Cents
    text: str


class Turn(StrictModel):
    messages: list[Message] = Field(min_length=1)


class Fault(StrictModel):
    tool: ToolName = "create_refund"
    occurrence: Annotated[StrictInt, Field(ge=1)] = 1
    kind: Literal["before_failure", "after_timeout", "visibility_delay", "rate_limit", "malformed"]
    probability: float = Field(default=1, ge=0, le=1)
    hidden_reads: Annotated[StrictInt, Field(ge=1)] = 3

    @model_validator(mode="after")
    def valid_point(self):
        if self.kind == "visibility_delay" and self.tool != "create_refund":
            raise ValueError("visibility_delay must attach to create_refund")
        return self


class Scenario(StrictModel):
    version: Literal[1] = 1
    name: Identifier
    description: str
    expected_behavior: str
    seed: int = 0
    payments: list[Payment] = Field(min_length=1)
    turns: list[Turn] = Field(min_length=1)
    faults: list[Fault] = Field(default_factory=list)
    split: Literal["development", "heldout", "generated"] = "development"

    @model_validator(mode="after")
    def consistent(self):
        ids = [p.payment_id for p in self.payments]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate payment IDs")
        slots = [(f.tool, f.occurrence) for f in self.faults]
        if len(slots) != len(set(slots)):
            raise ValueError("only one fault per tool invocation")
        seen = {}
        executed_amounts = {}
        for turn in self.turns:
            for m in turn.messages:
                identity = (m.payment_id, m.customer_id)
                if m.request_id in seen and seen[m.request_id] != identity:
                    raise ValueError("request ID cannot change payment/customer")
                seen[m.request_id] = identity
                if (
                    m.request_id in executed_amounts
                    and executed_amounts[m.request_id] != m.amount_cents
                ):
                    raise ValueError("amount changes after an execution turn are unsupported")
            for m in turn.messages:
                executed_amounts[m.request_id] = m.amount_cents
        return self


def load_scenario(path: str | Path) -> Scenario:
    return Scenario.model_validate(yaml.safe_load(Path(path).read_text()))


class CreateRefund(StrictModel):
    request_id: Identifier
    payment_id: Identifier
    customer_id: Identifier
    amount_cents: Cents
    idempotency_key: Identifier


class GetPayment(StrictModel):
    payment_id: Identifier
    customer_id: Identifier


class GetStatus(StrictModel):
    idempotency_key: Identifier


TOOL_MODELS = {
    "get_payment": GetPayment,
    "create_refund": CreateRefund,
    "get_refund_status": GetStatus,
    "list_refunds": GetPayment,
}


class Claim(StrictModel):
    request_id: Identifier
    payment_id: Identifier
    customer_id: Identifier
    amount_cents: Cents
    status: Literal["completed", "not_completed", "uncertain"]
    text: str
