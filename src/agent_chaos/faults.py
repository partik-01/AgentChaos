"""Fault boundary: ledger effects and agent observations are separate evidence."""
import copy
import random
import time
from collections import defaultdict

from pydantic import ValidationError

from .payments import PaymentError, PaymentService
from .schema import Fault, TOOL_MODELS


class FaultMiddleware:
    def __init__(self, service: PaymentService, faults: list[Fault], seed: int):
        self.service = service
        self.faults = faults
        self.counts: dict[str, int] = defaultdict(int)
        # Precompute decisions so agent-dependent extra calls cannot shift another fault's draw.
        rng = random.Random(seed)
        self.schedule = [f.model_dump() | {"draw": rng.random()} for f in faults]
        for slot in self.schedule:
            slot["enabled"] = slot["draw"] < slot["probability"]
        self.hidden: dict[str, int] = {}
        self.events: list[dict] = []

    def _observe(self, tool: str, result: dict) -> dict:
        if tool not in ("get_refund_status", "list_refunds"):
            return result
        keys = ([result["idempotency_key"]] if tool == "get_refund_status"
                else [r["idempotency_key"] for r in result["refunds"]])
        obscured = {key for key in keys if self.hidden.get(key, 0) > 0}
        for key in obscured:
            self.hidden[key] -= 1
        if tool == "get_refund_status" and obscured:
            return {"status": "not_found", "idempotency_key": result["idempotency_key"]}
        if tool == "list_refunds":
            return {"refunds": [r for r in result["refunds"] if r["idempotency_key"] not in obscured]}
        return result

    def call(self, tool: str, arguments: dict) -> dict:
        start = time.perf_counter()
        self.counts[tool] += 1
        occurrence = self.counts[tool]
        fault = next((s for s in self.schedule if s["tool"] == tool
                      and s["occurrence"] == occurrence and s["enabled"]), None)
        before = len(self.service.events)
        backend_result = None
        phase = "validation"
        try:
            if tool not in TOOL_MODELS:
                raise ValueError("unknown_tool")
            TOOL_MODELS[tool].model_validate(arguments)
            phase = "before"
            if fault and fault["kind"] in ("before_failure", "rate_limit"):
                code = "unavailable" if fault["kind"] == "before_failure" else "rate_limited"
                observed = {"error": code, "executed": False, "retry_after_ms": 100}
            else:
                phase = "execution"
                backend_result = self.service.execute(tool, arguments)
                phase = "after"
                if fault and fault["kind"] == "visibility_delay":
                    self.hidden[backend_result["idempotency_key"]] = fault["hidden_reads"]
                    # A delayed publication also obscures the initial creation confirmation.
                    observed = {"status": "pending", "idempotency_key": backend_result["idempotency_key"]}
                elif fault and fault["kind"] == "after_timeout":
                    observed = {"error": "timeout", "executed": "unknown"}
                elif fault and fault["kind"] == "malformed":
                    observed = {"raw": "{broken-json", "error": "malformed_response", "executed": "unknown"}
                else:
                    observed = self._observe(tool, backend_result)
        except PaymentError as exc:
            observed = {"error": exc.code, "executed": False}
        except (ValidationError, ValueError, TypeError) as exc:
            observed = {"error": "invalid_arguments", "detail": str(exc), "executed": False}
        event = {"index": len(self.events), "tool": tool, "occurrence": occurrence,
                 "arguments": copy.deepcopy(arguments), "fault": copy.deepcopy(fault),
                 "phase": phase, "backend_result": copy.deepcopy(backend_result),
                 "backend_events": copy.deepcopy(self.service.events[before:]),
                 "observed": copy.deepcopy(observed),
                 "latency_ms": (time.perf_counter() - start) * 1000}
        self.events.append(event)
        return copy.deepcopy(observed)
