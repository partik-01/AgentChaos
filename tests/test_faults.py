import pytest

from agent_chaos.faults import FaultMiddleware
from agent_chaos.payments import PaymentService
from agent_chaos.schema import Fault


@pytest.fixture
def service():
    s = PaymentService()
    s.restore({"payments": [{"payment_id": "p", "customer_id": "c", "amount_cents": 1000}], "refunds": []})
    yield s
    s.close()


ARGS = dict(payment_id="p", customer_id="c", amount_cents=300, idempotency_key="k")


@pytest.mark.parametrize("kind,committed,error", [
    ("before_failure", False, "unavailable"), ("rate_limit", False, "rate_limited"),
    ("after_timeout", True, "timeout"), ("malformed", True, "malformed_response")])
def test_fault_timing(service, kind, committed, error):
    middleware = FaultMiddleware(service, [Fault(kind=kind)], 42)
    assert middleware.call("create_refund", ARGS)["error"] == error
    assert bool(service.snapshot()["refunds"]) is committed
    event = middleware.events[0]
    assert bool(event["backend_events"]) is committed
    assert event["fault"]["kind"] == kind
    assert event["arguments"] == ARGS


def test_delayed_visibility_uses_reads_and_never_changes_ledger(service):
    m = FaultMiddleware(service, [Fault(kind="visibility_delay", hidden_reads=2)], 1)
    assert m.call("create_refund", ARGS)["status"] == "pending"
    snapshot = service.snapshot()
    assert m.call("get_refund_status", {"idempotency_key": "k"})["status"] == "not_found"
    assert m.call("list_refunds", {"payment_id": "p", "customer_id": "c"}) == {"refunds": []}
    assert m.call("get_refund_status", {"idempotency_key": "k"})["status"] == "succeeded"
    assert service.snapshot() == snapshot
    assert m.events[1]["backend_result"]["status"] == "succeeded"


def test_seed_and_call_position(service):
    faults = [Fault(kind="after_timeout", probability=0.5, occurrence=2)]
    a = FaultMiddleware(service, faults, 7)
    b = FaultMiddleware(service, faults, 7)
    assert a.schedule == b.schedule
    assert a.call("create_refund", ARGS)["status"] == "succeeded"
    assert a.call("create_refund", ARGS)["error"] == "timeout"
    assert len(service.snapshot()["refunds"]) == 1


def test_invalid_arguments_do_not_execute(service):
    m = FaultMiddleware(service, [], 0)
    assert m.call("create_refund", ARGS | {"amount_cents": True})["error"] == "invalid_arguments"
    assert not service.snapshot()["refunds"]
