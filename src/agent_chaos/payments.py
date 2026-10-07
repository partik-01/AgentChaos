"""Authoritative, transactional simulated payment ledger. No external payment APIs."""
import sqlite3
from pathlib import Path

from .schema import CreateRefund, GetPayment, GetStatus, TOOL_MODELS


class PaymentError(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class PaymentService:
    def __init__(self, path: str | Path = ":memory:"):
        self.db = sqlite3.connect(str(path), isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
            PRAGMA foreign_keys = ON;
            CREATE TABLE IF NOT EXISTS payments (
                payment_id TEXT PRIMARY KEY, customer_id TEXT NOT NULL,
                amount_cents INTEGER NOT NULL CHECK(amount_cents > 0));
            CREATE TABLE IF NOT EXISTS refunds (
                refund_id TEXT PRIMARY KEY, payment_id TEXT NOT NULL REFERENCES payments,
                customer_id TEXT NOT NULL, amount_cents INTEGER NOT NULL CHECK(amount_cents > 0),
                idempotency_key TEXT NOT NULL UNIQUE, status TEXT NOT NULL CHECK(status='succeeded'));
        """)
        self.events: list[dict] = []

    def close(self):
        self.db.close()

    def snapshot(self) -> dict:
        return {table: [dict(r) for r in self.db.execute(f"SELECT * FROM {table} ORDER BY 1")]
                for table in ("payments", "refunds")}

    def restore(self, snapshot: dict):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            self.db.execute("DELETE FROM refunds")
            self.db.execute("DELETE FROM payments")
            for p in snapshot["payments"]:
                self.db.execute("INSERT INTO payments VALUES (:payment_id,:customer_id,:amount_cents)", p)
            for r in snapshot["refunds"]:
                self.db.execute("""INSERT INTO refunds VALUES
                    (:refund_id,:payment_id,:customer_id,:amount_cents,:idempotency_key,:status)""", r)
            self.db.execute("COMMIT")
        except Exception:
            self.db.execute("ROLLBACK")
            raise
        self.events.clear()

    def get_payment(self, payment_id: str, customer_id: str) -> dict:
        args = GetPayment(payment_id=payment_id, customer_id=customer_id)
        row = self.db.execute("SELECT * FROM payments WHERE payment_id=?", (args.payment_id,)).fetchone()
        if row is None:
            raise PaymentError("payment_not_found")
        if row["customer_id"] != args.customer_id:
            raise PaymentError("customer_mismatch")
        refunded = self.db.execute("SELECT COALESCE(SUM(amount_cents),0) FROM refunds WHERE payment_id=?",
                                   (args.payment_id,)).fetchone()[0]
        return dict(row) | {"refunded_cents": refunded, "remaining_cents": row["amount_cents"] - refunded}

    def get_refund_status(self, idempotency_key: str) -> dict:
        args = GetStatus(idempotency_key=idempotency_key)
        row = self.db.execute("SELECT * FROM refunds WHERE idempotency_key=?",
                              (args.idempotency_key,)).fetchone()
        return dict(row) if row else {"status": "not_found", "idempotency_key": idempotency_key}

    def list_refunds(self, payment_id: str, customer_id: str) -> dict:
        self.get_payment(payment_id, customer_id)
        return {"refunds": [dict(r) for r in self.db.execute(
            "SELECT * FROM refunds WHERE payment_id=? ORDER BY refund_id", (payment_id,))]}

    def create_refund(self, payment_id: str, customer_id: str, amount_cents: int,
                      idempotency_key: str) -> dict:
        args = CreateRefund(payment_id=payment_id, customer_id=customer_id,
                            amount_cents=amount_cents, idempotency_key=idempotency_key)
        self.db.execute("BEGIN IMMEDIATE")
        try:
            existing = self.get_refund_status(idempotency_key)
            if existing["status"] != "not_found":
                if any(existing[k] != getattr(args, k) for k in
                       ("payment_id", "customer_id", "amount_cents")):
                    raise PaymentError("idempotency_conflict")
                self.db.execute("COMMIT")
                self.events.append({"kind": "idempotent_replay", "refund": existing})
                return existing
            payment = self.get_payment(payment_id, customer_id)
            if amount_cents > payment["remaining_cents"]:
                raise PaymentError("insufficient_balance")
            # Stable IDs are useful for offline evidence. Transactions serialize allocation.
            number = self.db.execute("SELECT COUNT(*) FROM refunds").fetchone()[0] + 1
            refund = args.model_dump() | {"refund_id": f"rf_{number:06d}", "status": "succeeded"}
            self.db.execute("""INSERT INTO refunds VALUES
                (:refund_id,:payment_id,:customer_id,:amount_cents,:idempotency_key,:status)""", refund)
            self.db.execute("COMMIT")
            self.events.append({"kind": "refund_committed", "refund": refund})
            return refund
        except Exception:
            if self.db.in_transaction:
                self.db.execute("ROLLBACK")
            raise

    def execute(self, tool: str, arguments: dict) -> dict:
        # Strict validation is applied even to LLM-supplied arguments.
        parsed = TOOL_MODELS[tool].model_validate(arguments)
        return getattr(self, tool)(**parsed.model_dump())
