"""Python integration boundary for a target running in the refund sandbox."""

import importlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Protocol

from .schema import Claim, Turn


class RefundTools(Protocol):
    """Observed tool results only; adapters must not access the payment database."""

    def call(self, tool: str, arguments: dict) -> dict: ...


class RefundAgent(Protocol):
    """Create a fresh instance for every trial, including each rerun."""

    metadata: dict[str, Any]

    def run_turn(self, turn: Turn, tools: RefundTools) -> list[Claim]: ...


def load_agent_factory(reference: str):
    """Import explicitly selected code; never call this with data from a trace."""
    if not re.fullmatch(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*:[A-Za-z_]\w*", reference):
        raise ValueError("agent factory must be module:callable, e.g. my_agent:create_agent")
    module_name, attribute = reference.split(":")
    # Console scripts do not normally put the user's working directory on sys.path.
    # This makes explicitly selected local modules usable alongside installed ones.
    sys.path.insert(0, str(Path.cwd()))
    try:
        factory = getattr(importlib.import_module(module_name), attribute)
    finally:
        sys.path.pop(0)
    if not callable(factory):
        raise ValueError("agent factory must be callable")
    return factory


def create_custom_agent(factory) -> RefundAgent:
    from .traces import AgentMetadata

    agent = factory()
    metadata = getattr(agent, "metadata", None)
    if not isinstance(metadata, dict) or metadata.get("kind") != "custom":
        raise ValueError("factory target must provide metadata with kind='custom'")
    version = metadata.get("version")
    if not isinstance(version, str) or not version.strip():
        raise ValueError("factory target metadata requires a nonempty version")
    if metadata.get("conversation_assessment") not in ("unassessed", "deterministic_templates"):
        raise ValueError("factory target must declare conversation_assessment")
    json.dumps(metadata, allow_nan=False)
    AgentMetadata.model_validate(metadata)
    if not callable(getattr(agent, "run_turn", None)):
        raise ValueError("factory target must provide run_turn(turn, tools)")
    return agent
