import copy
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from agent_chaos.traces import Trace


@pytest.fixture
def recorded():
    return json.loads(Path("examples/timeout-flawed.json").read_text())


@pytest.mark.parametrize("path", sorted(Path("examples").glob("*.json")))
def test_existing_single_run_trace_contracts(path):
    data = json.loads(path.read_text())
    if "trace_version" in data:
        Trace.model_validate(data)


@pytest.mark.parametrize(
    "section",
    [
        "initial_state",
        "final_state",
        "messages",
        "configuration",
        "agent",
        "tool_events",
        "backend_events",
        "responses",
        "result",
        "trial_summary",
        "created_at",
        "source_commit",
        "scenario_sha256",
        "fault_schedule",
    ],
)
def test_missing_required_section_is_rejected(recorded, section):
    del recorded[section]
    with pytest.raises(ValidationError):
        Trace.model_validate(recorded)


@pytest.mark.parametrize(
    "section,field,value",
    [
        ("configuration", "seed", "17"),
        ("trial_summary", "failure_count", True),
        ("result", "status", "success"),
        ("agent", "cost_usd", float("inf")),
    ],
)
def test_bad_nested_types_are_rejected(recorded, section, field, value):
    recorded[section][field] = value
    with pytest.raises(ValidationError):
        Trace.model_validate(recorded)


def test_wrong_money_and_missing_event_fields_are_rejected(recorded):
    bad = copy.deepcopy(recorded)
    bad["final_state"]["refunds"][0]["amount_cents"] = "300"
    with pytest.raises(ValidationError):
        Trace.model_validate(bad)
    del recorded["tool_events"][0]["observed"]
    with pytest.raises(ValidationError):
        Trace.model_validate(recorded)


@pytest.mark.parametrize("timestamp", ["yesterday", "2026-10-12T10:00:00"])
def test_timestamp_requires_iso_format_and_timezone(recorded, timestamp):
    recorded["created_at"] = timestamp
    with pytest.raises(ValidationError):
        Trace.model_validate(recorded)
