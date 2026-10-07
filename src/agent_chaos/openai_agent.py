"""Optional real model integration using the OpenAI Responses API only."""

import json
import time

from pydantic import Field

from .agents import CORRECTED_PROMPT, FLAWED_PROMPT, AgentFailure
from .schema import TOOL_MODELS, Claim, StrictModel, Turn


class ClaimsEnvelope(StrictModel):
    claims: list[Claim] = Field(min_length=1)


class OpenAIAgent:
    def __init__(self, version: str, model: str | None, *, client=None, max_steps=16):
        if not model:
            raise ValueError("--model is required for live OpenAI runs")
        if version not in ("flawed", "corrected"):
            raise ValueError("unknown agent version")
        if client is None:
            from openai import OpenAI

            # Disable hidden SDK retries so usage and attempts remain explicit.
            client = OpenAI(max_retries=0, timeout=30)
        self.client = client
        self.model = model
        self.max_steps = max_steps
        self.history: list[dict] = []
        self.prompt = CORRECTED_PROMPT if version == "corrected" else FLAWED_PROMPT
        self.metadata = {
            "kind": "llm",
            "provider": "openai",
            "version": version,
            "model": model,
            "prompt_version": "1",
            "prompt": self.prompt,
            "usage": {"input_tokens": 0, "output_tokens": 0},
            "cost_usd": None,
            "cost_note": "Provider does not supply cost; no pricing estimate configured.",
            "conversation_assessment": "unassessed",
            "model_calls": [],
            "max_steps_per_turn": max_steps,
            "sdk_retries": 0,
            "timeout_seconds": 30,
        }
        self.tools = [
            {
                "type": "function",
                "name": name,
                "strict": True,
                "description": f"Simulated payment API: {name}. Money is integer USD cents.",
                "parameters": schema.model_json_schema(),
            }
            for name, schema in TOOL_MODELS.items()
        ]

    def run_turn(self, turn: Turn, tools) -> list[Claim]:
        self.history.append(
            {
                "role": "user",
                "content": json.dumps(
                    {"pre_execution_messages": [m.model_dump() for m in turn.messages]}
                ),
            }
        )
        for _ in range(self.max_steps):
            start = time.perf_counter()
            response = self.client.responses.create(
                model=self.model,
                instructions=self.prompt,
                input=self.history,
                tools=self.tools,
                parallel_tool_calls=False,
                store=False,
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "refund_claims",
                        "strict": True,
                        "schema": ClaimsEnvelope.model_json_schema(),
                    }
                },
            )
            raw = response.model_dump(mode="json")
            usage = raw.get("usage") or {}
            self.metadata["usage"]["input_tokens"] += usage.get("input_tokens", 0)
            self.metadata["usage"]["output_tokens"] += usage.get("output_tokens", 0)
            self.metadata["model_calls"].append(
                {
                    "response": raw,
                    "latency_ms": (time.perf_counter() - start) * 1000,
                    "usage": usage,
                }
            )
            self.history.extend(raw["output"])
            calls = [item for item in raw["output"] if item.get("type") == "function_call"]
            if not calls:
                try:
                    return ClaimsEnvelope.model_validate_json(response.output_text).claims
                except ValueError as exc:
                    raise AgentFailure(f"invalid customer response: {exc}") from exc
            for call in calls:
                try:
                    arguments = json.loads(call["arguments"])
                    if not isinstance(arguments, dict):
                        raise ValueError("tool arguments must be an object")
                except ValueError:
                    arguments = {"invalid_json_arguments": call["arguments"]}
                observed = tools.call(call["name"], arguments)
                self.history.append(
                    {
                        "type": "function_call_output",
                        "call_id": call["call_id"],
                        "output": json.dumps(observed),
                    }
                )
        raise AgentFailure("tool/model step budget exhausted without a final customer response")
