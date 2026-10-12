from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

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


@pytest.fixture
def ledger_path(tmp_path):
    path = tmp_path / "ledger.db"
    s = PaymentService(path)
    try:
        s.restore(
            {
                "payments": [
                    {"payment_id": "p", "customer_id": "c", "amount_cents": 1000},
                    {"payment_id": "other", "customer_id": "other", "amount_cents": 500},
                ],
                "refunds": [],
            }
        )
    finally:
        s.close()
    return path


def race_refunds(path, requests):
    # Each worker owns its SQLite connection; all finish setup before competing.
    ready = Barrier(len(requests), timeout=10)

    def refund(arguments):
        local = PaymentService(path)
        try:
            ready.wait()
            try:
                result = local.create_refund(**arguments)
                return {"refund": result, "error": None, "events": local.events}
            except PaymentError as exc:
                assert not local.db.in_transaction
                return {"refund": None, "error": exc.code, "events": local.events}
        finally:
            local.close()

    with ThreadPoolExecutor(len(requests)) as pool:
        return list(pool.map(refund, requests))


def refund_arguments(amount, key, request="request"):
    return dict(
        payment_id="p",
        customer_id="c",
        amount_cents=amount,
        idempotency_key=key,
        request_id=request,
    )


def test_concurrent_requests_cannot_overdraw(ledger_path):
    results = race_refunds(ledger_path, [refund_arguments(700, key) for key in ("a", "b")])
    assert sum(r["error"] == "insufficient_balance" for r in results) == 1
    assert sum(r["refund"] is not None for r in results) == 1
    assert sum(len(r["events"]) for r in results) == 1
    final = PaymentService(ledger_path)
    try:
        assert final.get_payment("p", "c")["remaining_cents"] == 300
        assert len(final.snapshot()["refunds"]) == 1
    finally:
        final.close()


@pytest.mark.parametrize("trial", range(5))
def test_concurrent_identical_keys_commit_once_and_replay_at_zero_balance(ledger_path, trial):
    arguments = refund_arguments(1000, "same-key")
    results = race_refunds(ledger_path, [arguments] * 4)
    assert all(r["error"] is None for r in results)
    assert all(r["refund"] == results[0]["refund"] for r in results)
    kinds = [e["kind"] for r in results for e in r["events"]]
    assert kinds.count("refund_committed") == 1
    assert kinds.count("idempotent_replay") == 3
    final = PaymentService(ledger_path)
    try:
        assert final.snapshot()["refunds"] == [results[0]["refund"]]
        assert final.get_payment("p", "c")["remaining_cents"] == 0
        assert final.get_payment("other", "other")["remaining_cents"] == 500
    finally:
        final.close()


@pytest.mark.parametrize("trial", range(5))
def test_concurrent_conflicting_key_has_one_winner_without_parameter_changes(ledger_path, trial):
    arguments = [refund_arguments(amount, "same-key") for amount in (200, 300, 400, 500)]
    results = race_refunds(ledger_path, arguments)
    winners = [(args, result) for args, result in zip(arguments, results) if result["refund"]]
    assert len(winners) == 1
    args, winner = winners[0]
    assert all(winner["refund"][key] == value for key, value in args.items())
    assert sum(r["error"] == "idempotency_conflict" for r in results) == 3
    assert [e["kind"] for r in results for e in r["events"]] == ["refund_committed"]
    final = PaymentService(ledger_path)
    try:
        assert final.snapshot()["refunds"] == [winner["refund"]]
        assert final.get_payment("p", "c")["remaining_cents"] == 1000 - args["amount_cents"]
    finally:
        final.close()


@pytest.mark.parametrize("trial", range(5))
def test_competing_distinct_keys_exhaust_only_the_remaining_partial_balance(ledger_path, trial):
    seed = PaymentService(ledger_path)
    try:
        previous = seed.create_refund(**refund_arguments(400, "previous", "previous"))
    finally:
        seed.close()
    results = race_refunds(
        ledger_path, [refund_arguments(300, f"key-{i}", f"request-{i}") for i in range(4)]
    )
    assert sum(r["refund"] is not None for r in results) == 2
    assert sum(r["error"] == "insufficient_balance" for r in results) == 2
    assert [e["kind"] for r in results for e in r["events"]] == ["refund_committed"] * 2
    final = PaymentService(ledger_path)
    try:
        rows = final.snapshot()["refunds"]
        assert len(rows) == 3
        assert previous in rows
        assert sum(r["amount_cents"] for r in rows) == 1000
        assert len({r["refund_id"] for r in rows}) == 3
        assert final.get_payment("p", "c")["remaining_cents"] == 0
        assert final.get_payment("other", "other")["remaining_cents"] == 500
    finally:
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
