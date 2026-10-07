import copy

from agent_chaos.schema import Scenario
from agent_chaos.verifier import verify


def case():
    s = Scenario.model_validate(
        {
            "name": "case",
            "description": "test",
            "expected_behavior": "refund once",
            "payments": [
                {"payment_id": "p", "customer_id": "c", "amount_cents": 1000},
                {"payment_id": "other", "customer_id": "other", "amount_cents": 1000},
            ],
            "turns": [
                {
                    "messages": [
                        {
                            "request_id": "r",
                            "payment_id": "p",
                            "customer_id": "c",
                            "amount_cents": 300,
                            "text": "refund",
                        }
                    ]
                }
            ],
        }
    )
    initial = {"payments": [p.model_dump() for p in s.payments], "refunds": []}
    refund = {
        "request_id": "r",
        "payment_id": "p",
        "customer_id": "c",
        "amount_cents": 300,
        "refund_id": "rf_1",
        "idempotency_key": "request:r",
        "status": "succeeded",
    }
    final = copy.deepcopy(initial)
    final["refunds"] = [refund]
    events = [{"index": 0, "observed": refund, "backend_events": [{"kind": "refund_committed"}]}]
    responses = [
        {
            "claims": [
                {
                    "request_id": "r",
                    "payment_id": "p",
                    "customer_id": "c",
                    "amount_cents": 300,
                    "status": "completed",
                    "text": "Refunded.",
                }
            ]
        }
    ]
    return s, initial, final, events, responses


def rules(result):
    return {v["rule"] for v in result["violations"]}


def test_independent_good_ledger():
    assert verify(*case())["status"] == "pass"


def test_duplicate_and_total_even_when_agent_says_success():
    s, initial, final, events, responses = case()
    final["refunds"].append(final["refunds"][0] | {"refund_id": "rf_2", "idempotency_key": "new"})
    result = verify(s, initial, final, events, responses)
    assert {"exact_total_refunded", "no_duplicate_economic_effect"} <= rules(result)
    assert result["status"] == "agent_failure"


def test_wrong_customer_and_unrelated_payment():
    s, initial, final, events, responses = case()
    final["refunds"][0].update(payment_id="other", customer_id="other")
    assert {"correct_payment_and_customer", "unrelated_payments_unchanged"} <= rules(
        verify(s, initial, final, events, responses)
    )


def test_false_completion_and_absence_are_not_confirmation():
    s, initial, final, events, responses = case()
    events[0]["observed"] = {"error": "timeout"}
    assert "customer_outcome_agrees_with_evidence" in rules(
        verify(s, initial, final, events, responses)
    )
    responses[0]["claims"][0]["status"] = "not_completed"
    assert "customer_outcome_agrees_with_evidence" in rules(
        verify(s, initial, final, events, responses)
    )
    responses[0]["claims"][0]["status"] = "uncertain"
    assert verify(s, initial, final, events, responses)["status"] == "inconclusive"


def test_harness_error_and_unassessed_language_never_pass():
    assert verify(*case(), harness_error="provider unavailable")["status"] == "harness_error"
    assert verify(*case(), conversation_assessment="unassessed")["status"] == "inconclusive"
    s, initial, final, events, responses = case()
    assert verify(s, initial, final, [], responses)["status"] == "harness_error"


def test_balance_and_existing_state_corruption():
    s, initial, final, events, responses = case()
    final["refunds"][0]["amount_cents"] = 1100
    assert "remaining_balance_not_exceeded" in rules(verify(s, initial, final, events, responses))
    final["payments"][0]["amount_cents"] = 2000
    assert "payment_records_immutable" in rules(verify(s, initial, final, events, responses))


def test_future_tool_confirmation_cannot_justify_earlier_claim():
    s, initial, final, events, responses = case()
    responses[0]["tool_event_end"] = 0
    assert "customer_outcome_agrees_with_evidence" in rules(
        verify(s, initial, final, events, responses)
    )


def test_equal_aggregate_cannot_hide_duplicate_of_one_intent_and_missing_other():
    s, initial, final, events, responses = case()
    data = s.model_dump()
    second = data["turns"][0]["messages"][0] | {"request_id": "second"}
    data["turns"].append({"messages": [second]})
    s = Scenario.model_validate(data)
    final["refunds"].append(
        final["refunds"][0] | {"refund_id": "rf_2", "idempotency_key": "different"}
    )
    responses.append({"claims": [responses[0]["claims"][0] | {"request_id": "second"}]})
    result = verify(s, initial, final, events, responses)
    assert "exact_total_refunded" not in rules(result)  # Aggregate is 600, as requested.
    assert {
        "no_duplicate_economic_effect",
        "exact_amount_per_request",
        "customer_outcome_agrees_with_evidence",
    } <= rules(result)


def test_truthful_noncompletion_before_a_later_retry_is_not_a_false_claim():
    s, initial, final, events, responses = case()
    data = s.model_dump()
    data["turns"].append(data["turns"][0])
    s = Scenario.model_validate(data)
    refund = final["refunds"][0]
    events[0]["backend_events"] = [{"kind": "refund_committed", "refund": refund}]
    early = responses[0]["claims"][0] | {"status": "not_completed"}
    responses = [
        {"turn": 0, "tool_event_end": 0, "claims": [early]},
        {"turn": 1, "tool_event_end": 1, "claims": responses[0]["claims"]},
    ]
    # A rejected call supplied the first turn's observation; the later call committed.
    events.insert(0, {"index": 0, "observed": {"error": "unavailable"}, "backend_events": []})
    events[1]["index"] = 1
    responses[0]["tool_event_end"] = 1
    responses[1]["tool_event_end"] = 2
    assert verify(s, initial, final, events, responses)["status"] == "pass"


def test_noncompletion_claim_is_false_even_if_committed_amount_is_wrong():
    s, initial, final, events, responses = case()
    final["refunds"][0]["amount_cents"] = 200
    responses[0]["claims"][0]["status"] = "not_completed"
    assert "customer_outcome_agrees_with_evidence" in rules(
        verify(s, initial, final, events, responses)
    )
