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


@pytest.mark.parametrize("already_refunded", [1, 400, 999])
def test_restored_partial_refunds_enforce_exact_remaining_balance(service, already_refunded):
    initial = {
        "payments": [
            {"payment_id": "p", "customer_id": "c", "amount_cents": 1000},
            {"payment_id": "other", "customer_id": "other", "amount_cents": 500},
        ],
        "refunds": [
            {
                "refund_id": "rf_000001",
                "payment_id": "p",
                "customer_id": "c",
                "amount_cents": already_refunded,
                "idempotency_key": "previous",
                "request_id": "previous",
                "status": "succeeded",
            }
        ],
    }
    service.restore(initial)
    before = service.snapshot()
    remaining = 1000 - already_refunded
    assert service.get_payment("p", "c")["remaining_cents"] == remaining
    with pytest.raises(PaymentError, match="insufficient_balance"):
        service.create_refund("p", "c", remaining + 1, "new", "new")
    assert service.snapshot() == before
    assert service.events == []
    assert not service.db.in_transaction
    assert service.get_refund_status("new")["status"] == "not_found"

    # A rejected key is reusable: the exact remaining amount succeeds after rollback.
    refund = service.create_refund("p", "c", remaining, "new", "new")
    assert service.get_payment("p", "c")["remaining_cents"] == 0
    assert service.create_refund("p", "c", remaining, "new", "new") == refund
    assert service.list_refunds("p", "c")["refunds"] == before["refunds"] + [refund]
    assert service.get_payment("other", "other")["remaining_cents"] == 500
    assert service.snapshot()["payments"] == before["payments"]
    assert [e["kind"] for e in service.events] == ["refund_committed", "idempotent_replay"]
    after = service.snapshot()
    with pytest.raises(PaymentError, match="insufficient_balance"):
        service.create_refund("p", "c", 1, "too-late", "too-late")
    assert service.snapshot() == after
    assert len(service.events) == 2
    assert not service.db.in_transaction


@pytest.mark.parametrize(
    "field,value",
    [
        ("payment_id", "other"),
        ("customer_id", "other"),
        ("amount_cents", 301),
        ("request_id", "other"),
    ],
)
def test_conflicting_key_parameters_leave_ledger_and_transaction_unchanged(service, field, value):
    arguments = dict(
        payment_id="p",
        customer_id="c",
        amount_cents=300,
        idempotency_key="key",
        request_id="request",
    )
    original = service.create_refund(**arguments)
    before = service.snapshot()
    with pytest.raises(PaymentError, match="idempotency_conflict"):
        service.create_refund(**(arguments | {field: value}))
    assert service.snapshot() == before
    assert len(service.events) == 1
    assert not service.db.in_transaction
    assert service.create_refund(**arguments) == original
    assert [e["kind"] for e in service.events] == ["refund_committed", "idempotent_replay"]
