"""Offline execution-limit examples. Deliberately broken scripts, no model calls."""

import time

from examples.custom_agent import MySupportAgent


class RefundThenHang(MySupportAgent):
    def run_turn(self, turn, tools):
        super().run_turn(turn, tools)  # Authoritative refund commits first.
        while True:
            time.sleep(1)


class EndlessReads(MySupportAgent):
    def run_turn(self, turn, tools):
        while True:
            try:
                tools.call("get_payment", {"payment_id": turn.messages[0].payment_id})
            except Exception:
                # A parent-enforced limit cannot be swallowed by this retry loop.
                continue


def make_refund_then_hang():
    target = RefundThenHang()
    target.metadata["version"] = "example-refund-then-hang-v1"
    return target


def make_endless_reads():
    target = EndlessReads()
    target.metadata["version"] = "example-endless-reads-v1"
    return target
