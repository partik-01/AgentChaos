"""Bounded proposal generation. Proposals are validated, never automatic fixes."""

import json
import random
from pathlib import Path

import yaml
from pydantic import Field

from .schema import Fault, Scenario, StrictModel, Turn


class Proposal(StrictModel):
    turns: list[Turn] = Field(min_length=1, max_length=8)
    faults: list[Fault] = Field(max_length=12)


GENERATOR_PROMPT = """Propose a refund-agent chaos scenario within a SIMULATED environment.
Return only JSON with turns and faults. Keep the provided payment fixture. Turn
messages require request_id, payment_id, customer_id, amount_cents (positive integer
USD cents), and text. Group changes before execution in the same turn. Repeat an ID
only for the same payment/customer and same amount across turns. Faults require tool,
occurrence (1-based), kind, probability, hidden_reads. Tools: get_payment, create_refund,
get_refund_status, list_refunds. Kinds: before_failure, rate_limit, after_timeout,
malformed, visibility_delay. Visibility_delay attaches only to create_refund. Do not
reuse a tool/occurrence pair. At most 8 turns, 16 messages and 12 faults. Propose
ambiguous failure combinations, safe enough to execute against this fixture only.
"""


def validate_proposal(base: Scenario, proposal: dict, *, name: str, seed: int) -> Scenario:
    parsed = Proposal.model_validate(proposal)
    if sum(len(t.messages) for t in parsed.turns) > 16:
        raise ValueError("proposal exceeds 16 messages")
    # Fixture is copied from base; the generator cannot provide or replace payment state.
    return Scenario.model_validate(
        base.model_dump()
        | {
            "name": name,
            "seed": seed,
            "split": "generated",
            "description": "Generated proposal: validated refund interactions and fault sequence.",
            "expected_behavior": "Honor authorized latest amounts once; reconcile ambiguity or report uncertainty.",
            "turns": [t.model_dump() for t in parsed.turns],
            "faults": [f.model_dump() for f in parsed.faults],
        }
    )


def random_scenario(base: Scenario, seed: int) -> Scenario:
    """Random baseline, not a model-generated scenario or a scripted agent."""
    rng = random.Random(seed)
    kind = rng.choice(
        ["before_failure", "rate_limit", "after_timeout", "malformed", "visibility_delay"]
    )
    fault = Fault(
        kind=kind,
        occurrence=rng.randint(1, 3),
        probability=rng.choice([0.5, 1.0]),
        hidden_reads=rng.randint(1, 6),
    )
    return Scenario.model_validate(
        base.model_dump()
        | {
            "name": f"random-{seed}",
            "seed": seed,
            "split": "generated",
            "faults": [fault.model_dump()],
            "description": "Seeded random creation-fault baseline.",
            "expected_behavior": "Honor the base interactions once despite a seeded random fault.",
        }
    )


def generate_scenario(base: Scenario, seed: int, *, provider="scripted", model=None, client=None):
    if provider == "scripted":
        # Offline proposal policy intentionally targets ambiguous commits. Clearly labeled.
        rng = random.Random(seed)
        latest = base.turns[0].messages[-1]
        turns = [base.turns[0].model_dump()]
        if rng.choice([False, True]):
            turns.append(
                {
                    "messages": [
                        latest.model_dump() | {"text": "Please confirm my same refund request."}
                    ]
                }
            )
        faults = [
            Fault(
                kind=rng.choice(["after_timeout", "malformed", "visibility_delay"]),
                hidden_reads=rng.randint(1, 6),
            ).model_dump()
        ]
        candidate = validate_proposal(
            base, {"turns": turns, "faults": faults}, name=f"generated-{seed}", seed=seed
        )
        return candidate, {
            "kind": "scripted_proposal",
            "model": None,
            "seed": seed,
            "usage": {"input_tokens": 0, "output_tokens": 0},
            "cost_usd": 0.0,
            "note": "Deterministic offline proposal policy; not an LLM generation agent.",
        }
    if provider != "openai" or not model:
        raise ValueError("OpenAI generation requires --model")
    if client is None:
        from openai import OpenAI

        client = OpenAI(max_retries=0, timeout=30)
    request = {
        "model": model,
        "instructions": GENERATOR_PROMPT,
        "store": False,
        "input": json.dumps({"fixture": base.model_dump(), "proposal_seed_label": seed}),
        "text": {"format": {"type": "json_object"}},
    }
    response = client.responses.create(**request)
    candidate = validate_proposal(
        base, json.loads(response.output_text), name=f"generated-{seed}", seed=seed
    )
    return candidate, {
        "kind": "llm_proposal",
        "model": model,
        "seed": seed,
        "request": request,
        "response": response.model_dump(mode="json"),
        "cost_usd": None,
        "note": "Locally validated proposal. Seed does not make model generation deterministic.",
    }


def write_scenario(path: str | Path, scenario: Scenario):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(scenario.model_dump(), sort_keys=False))
