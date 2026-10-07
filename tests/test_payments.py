from concurrent.futures import ThreadPoolExecutor

import pytest
from pydantic import ValidationError

from agent_chaos.payments import PaymentError, PaymentService


@pytest.fixture
def service():
    s = PaymentService()
    s.restore(
        {"payments": [{"payment_id": "p", "customer_id": "c", "amount_cents": 1000}], "refunds": []}
    )
    yield s
    s.close()


def test_idempotency_precedes_balance_check(service):
    first = service.create_refund("p", "c", 1000, "key", "r")
    assert service.create_refund("p", "c", 1000, "key", "r") == first
    assert len(service.snapshot()["refunds"]) == 1
    assert service.get_payment("p", "c")["remaining_cents"] == 0
    with pytest.raises(PaymentError, match="idempotency_conflict"):
        service.create_refund("p", "c", 500, "key", "r")


@pytest.mark.parametrize("amount", [0, -1, 1.5, True, "100"])
def test_rejects_invalid_money(service, amount):
    with pytest.raises(ValidationError):
        service.create_refund("p", "c", amount, "key", "r")
    assert not service.snapshot()["refunds"]


def test_ownership_balance_and_read_semantics(service):
    with pytest.raises(PaymentError, match="customer_mismatch"):
        service.create_refund("p", "other", 100, "key", "r")
    service.create_refund("p", "c", 600, "one", "r")
    with pytest.raises(PaymentError, match="insufficient_balance"):
        service.create_refund("p", "c", 500, "two", "r")
    assert service.get_refund_status("one")["amount_cents"] == 600
    assert len(service.list_refunds("p", "c")["refunds"]) == 1
    assert service.get_refund_status("two")["status"] == "not_found"


def test_concurrent_requests_cannot_overdraw(tmp_path):
    path = tmp_path / "ledger.db"
    s = PaymentService(path)
    s.restore(
        {"payments": [{"payment_id": "p", "customer_id": "c", "amount_cents": 1000}], "refunds": []}
    )
    s.close()

    def refund(key):
        local = PaymentService(path)
        try:
            return local.create_refund("p", "c", 700, key, "r")["status"]
        except PaymentError as exc:
            return exc.code
        finally:
            local.close()

    with ThreadPoolExecutor(2) as pool:
        assert sorted(pool.map(refund, ["a", "b"])) == ["insufficient_balance", "succeeded"]
    final = PaymentService(path)
    assert final.get_payment("p", "c")["remaining_cents"] == 300
    final.close()


def test_idempotency_key_cannot_be_reassigned_to_another_request(service):
    service.create_refund("p", "c", 300, "key", "request-a")
    with pytest.raises(PaymentError, match="idempotency_conflict"):
        service.create_refund("p", "c", 300, "key", "request-b")
    # Different keys still permit duplicate effects so the harness can expose agent bugs.
    service.create_refund("p", "c", 300, "other-key", "request-a")
    assert len(service.snapshot()["refunds"]) == 2
