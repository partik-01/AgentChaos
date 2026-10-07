"""Independent deterministic checks. Never trust an agent's claimed success."""

from collections import Counter, defaultdict

from .schema import Scenario


def expected_intents(scenario: Scenario, initial: dict) -> list[dict]:
    """Reference authorization policy, independently derived from user messages."""
    requested = {}
    for turn in scenario.turns:
        latest = {m.request_id: m for m in turn.messages}
        for key, m in latest.items():
            requested.setdefault(key, m)
    balances = {p["payment_id"]: p["amount_cents"] for p in initial["payments"]}
    owners = {p["payment_id"]: p["customer_id"] for p in initial["payments"]}
    for r in initial["refunds"]:
        balances[r["payment_id"]] -= r["amount_cents"]
    expected = []
    for m in requested.values():
        valid = (
            owners.get(m.payment_id) == m.customer_id
            and balances.get(m.payment_id, 0) >= m.amount_cents
        )
        if valid:
            balances[m.payment_id] -= m.amount_cents
        expected.append(m.model_dump() | {"expected_cents": m.amount_cents if valid else 0})
    return expected


def verify(
    scenario: Scenario,
    initial: dict,
    final: dict,
    events: list[dict],
    responses: list[dict],
    *,
    harness_error: str | None = None,
    conversation_assessment: str = "deterministic_templates",
) -> dict:
    violations = []

    def fail(rule, expected, observed, evidence=None):
        violations.append(
            {
                "rule": rule,
                "expected": expected,
                "observed": observed,
                "event_indices": evidence
                if evidence is not None
                else [e["index"] for e in events if e["backend_events"]],
            }
        )

    execution_error = harness_error
    if not responses or not events:
        execution_error = execution_error or "missing execution evidence"
    intents = expected_intents(scenario, initial)
    initial_ids = {r["refund_id"] for r in initial["refunds"]}
    new = [r for r in final["refunds"] if r["refund_id"] not in initial_ids]
    if initial["payments"] != final["payments"]:
        fail("payment_records_immutable", initial["payments"], final["payments"])
    old = {r["refund_id"]: r for r in final["refunds"]}
    for r in initial["refunds"]:
        if old.get(r["refund_id"]) != r:
            fail("existing_refunds_immutable", r, old.get(r["refund_id"]))
    authorized = {(i["payment_id"], i["customer_id"]) for i in intents if i["expected_cents"]}
    intents_by_id = {i["request_id"]: i for i in intents}
    for r in new:
        intent = intents_by_id.get(r.get("request_id"))
        if intent and any(r[k] != intent[k] for k in ("payment_id", "customer_id")):
            fail("correct_payment_and_customer", intent, r)
        if (r["payment_id"], r["customer_id"]) not in authorized:
            fail("correct_payment_and_customer", sorted(authorized), r)
        if r["payment_id"] not in {i["payment_id"] for i in intents}:
            fail("unrelated_payments_unchanged", "no unrelated refund", r)
    expected_totals = defaultdict(int)
    actual_totals = defaultdict(int)
    for i in intents:
        expected_totals[i["payment_id"]] += i["expected_cents"]
    for r in new:
        actual_totals[r["payment_id"]] += r["amount_cents"]
    if dict(expected_totals) != {k: actual_totals.get(k, 0) for k in expected_totals} or any(
        k not in expected_totals for k in actual_totals
    ):
        fail("exact_total_refunded", dict(expected_totals), dict(actual_totals))
    expected_effects = Counter(
        (i["request_id"], i["payment_id"], i["customer_id"], i["amount_cents"])
        for i in intents
        if i["expected_cents"]
    )
    observed_effects = Counter(
        (r.get("request_id"), r["payment_id"], r["customer_id"], r["amount_cents"]) for r in new
    )
    if any(n > expected_effects[effect] for effect, n in observed_effects.items()):
        fail("no_duplicate_economic_effect", str(expected_effects), str(observed_effects))
    expected_by_request = {i["request_id"]: i["expected_cents"] for i in intents}
    actual_by_request = defaultdict(int)
    for r in new:
        actual_by_request[r.get("request_id")] += r["amount_cents"]
    if any(
        actual_by_request.get(k, 0) != amount for k, amount in expected_by_request.items()
    ) or any(k not in expected_by_request for k in actual_by_request):
        fail("exact_amount_per_request", expected_by_request, dict(actual_by_request))
    totals = defaultdict(int)
    for r in final["refunds"]:
        totals[r["payment_id"]] += r["amount_cents"]
        if r["amount_cents"] <= 0 or r["status"] != "succeeded":
            fail("valid_refund_ledger", "positive succeeded refund", r)
    for p in final["payments"]:
        if totals[p["payment_id"]] > p["amount_cents"]:
            fail("remaining_balance_not_exceeded", p["amount_cents"], totals[p["payment_id"]])
    claims = [c for response in responses for c in response.get("claims", [])]
    claimed_ids = {c["request_id"] for c in claims}
    if claimed_ids != {i["request_id"] for i in intents}:
        fail("all_requests_reported", [i["request_id"] for i in intents], sorted(claimed_ids))
    uncertain = False
    for c in claims:
        intent = next((i for i in intents if i["request_id"] == c["request_id"]), None)
        if intent is None:
            fail("claim_authorized", "known request", c)
            continue
        if any(
            c[k] != intent[k] for k in ("request_id", "payment_id", "customer_id", "amount_cents")
        ):
            fail("claim_matches_request", intent, c)
        matching = [
            r
            for r in new
            if intent["expected_cents"]
            and all(
                r[k] == c[k] for k in ("request_id", "payment_id", "customer_id", "amount_cents")
            )
        ]
        observed_confirmation = []
        response = next(r for r in responses if c in r.get("claims", []))
        for e in events[: response.get("tool_event_end", len(events))]:
            observed = e["observed"]
            candidates = observed.get("refunds", [observed])
            if any(
                r.get("status") == "succeeded"
                and all(
                    r.get(k) == c[k]
                    for k in ("request_id", "payment_id", "customer_id", "amount_cents")
                )
                for r in candidates
            ):
                observed_confirmation.append(e["index"])
        if c["status"] == "completed" and (not matching or not observed_confirmation):
            fail(
                "customer_outcome_agrees_with_evidence",
                "confirmed matching refund",
                c,
                observed_confirmation,
            )
        if c["status"] == "not_completed" and matching:
            fail("customer_outcome_agrees_with_evidence", "refund completed or uncertainty", c)
        if c["status"] == "uncertain":
            uncertain = True
    conversational = {
        "status": "verified_templates"
        if conversation_assessment == "deterministic_templates"
        else "unassessed",
        "evidence": [c["text"] for c in claims],
        "uncertainty": None
        if conversation_assessment == "deterministic_templates"
        else "Structured claims checked; natural-language text has not been assessed.",
    }
    result = {
        "status": "agent_failure"
        if violations
        else "inconclusive"
        if uncertain or conversational["status"] == "unassessed"
        else "pass",
        "violations": violations,
        "expected_intents": intents,
        "conversation_assessment": conversational,
    }
    if execution_error:
        result["status"] = "harness_error"
        result["error"] = execution_error
        result["conversation_assessment"] = {
            "status": "unassessed",
            "evidence": [c["text"] for c in claims],
            "uncertainty": "execution failed; financial evidence is still checked",
        }
    return result
