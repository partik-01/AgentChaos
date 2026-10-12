"""Python integration boundary for a target running in the refund sandbox."""

from typing import Any, Protocol

from .schema import Claim, Turn


class RefundTools(Protocol):
    """Observed tool results only; adapters must not access the payment database."""

    def call(self, tool: str, arguments: dict) -> dict: ...


class RefundAgent(Protocol):
    """Create a fresh instance for every trial, including each rerun."""

    metadata: dict[str, Any]

    def run_turn(self, turn: Turn, tools: RefundTools) -> list[Claim]: ...
