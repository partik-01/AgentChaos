"""Deterministic demonstrations; these agents are scripts, not LLM benchmarks."""

from .schema import Claim, Message, Turn

CORRECTED_PROMPT = """You are a support agent in a SIMULATED refund environment.
Use the latest amount in each pre-execution message batch. Request IDs identify one
business intent, including repeated messages. Check payment ownership and balance.
Use exactly request:<request_id> as the idempotency key. Keep that key and parameters
on retries. A timeout or malformed response may hide a successful commit. Reconcile
with status/list reads; absence is not proof of failure. Retry creation with the same
key only. Never claim completion without a matching succeeded tool observation.
If unable to verify, report uncertain. Do not issue another refund for a repeat.
Respond with a JSON object containing a claims array. Each claim has request_id,
payment_id, customer_id, amount_cents, status (completed/not_completed/uncertain),
and text, the exact customer-facing sentence. Do not output other customer prose.
"""
FLAWED_PROMPT = """You are a SIMULATED support refund agent. Process the first amount
requested. Retry failed refund creation with a fresh idempotency key. A not_found
status means the refund failed. Repeat customer requests should be processed again.
Respond with a JSON object containing a claims array. Each claim has request_id,
payment_id, customer_id, amount_cents, status (completed/not_completed/uncertain),
and text, the exact customer-facing sentence. Do not output other customer prose.
"""


def claim(message: Message, status: str) -> Claim:
    sentences = {
        "completed": f"Refunded {message.amount_cents} USD cents for payment {message.payment_id}.",
        "not_completed": f"No refund completed for payment {message.payment_id}.",
        "uncertain": f"I cannot verify whether the refund for payment {message.payment_id} completed.",
    }
    return Claim(
        **{
            k: getattr(message, k)
            for k in ("request_id", "payment_id", "customer_id", "amount_cents")
        },
        status=status,
        text=sentences[status],
    )


def confirmed(result: dict, message: Message) -> bool:
    return result.get("status") == "succeeded" and all(
        result.get(k) == getattr(message, k) for k in ("payment_id", "customer_id", "amount_cents")
    )


class ScriptedAgent:
    def __init__(self, version: str):
        if version not in ("flawed", "corrected"):
            raise ValueError("unknown agent version")
        self.version = version
        self.memory: dict[str, Claim] = {}
        self.counter = 0
        self.metadata = {
            "kind": "scripted",
            "version": version,
            "model": None,
            "prompt_version": "1",
            "prompt": CORRECTED_PROMPT if version == "corrected" else FLAWED_PROMPT,
            "usage": {"input_tokens": 0, "output_tokens": 0},
            "cost_usd": 0.0,
            "conversation_assessment": "deterministic_templates",
        }

    def run_turn(self, turn: Turn, tools) -> list[Claim]:
        selected = {}
        for message in turn.messages:
            if self.version == "corrected" or message.request_id not in selected:
                selected[message.request_id] = message
        return [self._refund(m, tools) for m in selected.values()]

    def _refund(self, m: Message, tools) -> Claim:
        if self.version == "corrected" and m.request_id in self.memory:
            return self.memory[m.request_id]
        payment = tools.call(
            "get_payment", {"payment_id": m.payment_id, "customer_id": m.customer_id}
        )
        if "error" in payment:
            status = (
                "not_completed"
                if payment["error"] in ("customer_mismatch", "payment_not_found")
                else "uncertain"
            )
            return claim(m, status)
        if payment.get("remaining_cents", 0) < m.amount_cents:
            return claim(m, "not_completed")
        key = f"request:{m.request_id}"
        args = {
            "payment_id": m.payment_id,
            "customer_id": m.customer_id,
            "amount_cents": m.amount_cents,
        }
        for _ in range(3):
            if self.version == "flawed":
                self.counter += 1
                key = f"request:{m.request_id}:attempt:{self.counter}"
            result = tools.call("create_refund", args | {"idempotency_key": key})
            if confirmed(result, m):
                answer = claim(m, "completed")
                self.memory[m.request_id] = answer
                return answer
            if result.get("error") in (
                "insufficient_balance",
                "customer_mismatch",
                "idempotency_conflict",
            ):
                return claim(m, "not_completed")
            if self.version == "flawed":
                if result.get("status") == "pending":
                    status = tools.call("get_refund_status", {"idempotency_key": key})
                    return claim(m, "completed" if confirmed(status, m) else "not_completed")
                continue
            # Bounded reconciliation. Every new creation attempt retains exactly the same key.
            for _ in range(3):
                status = tools.call("get_refund_status", {"idempotency_key": key})
                if confirmed(status, m):
                    answer = claim(m, "completed")
                    self.memory[m.request_id] = answer
                    return answer
            listed = tools.call(
                "list_refunds", {"payment_id": m.payment_id, "customer_id": m.customer_id}
            )
            if any(
                r.get("idempotency_key") == key and confirmed(r, m)
                for r in listed.get("refunds", [])
            ):
                answer = claim(m, "completed")
                self.memory[m.request_id] = answer
                return answer
        return claim(m, "uncertain")


class AgentFailure(Exception):
    """The target executed but violated its output/budget contract."""
