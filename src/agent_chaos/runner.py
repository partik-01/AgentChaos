"""Record isolated runs; reruns restore embedded initial state, not current fixtures."""

import hashlib
import json
import shlex
import subprocess
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from . import __version__
from .adapters import RefundAgent
from .agents import AgentFailure, ScriptedAgent
from .execution import apply_execution_stop, execute_bounded, execution_limits
from .faults import FaultMiddleware
from .payments import PaymentService
from .schema import Scenario
from .traces import TRACE_VERSION, validate_trace
from .verifier import verify


def source_version() -> str:
    try:
        root = Path(__file__).resolve().parents[2]
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=root, stderr=subprocess.DEVNULL, text=True
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def run_scenario(
    scenario: Scenario,
    agent_version="corrected",
    *,
    out: str | Path = "runs",
    initial: dict | None = None,
    provider="scripted",
    model: str | None = None,
    agent: RefundAgent | None = None,
    agent_factory: str | None = None,
    timeout_seconds: float | None = None,
    max_tool_calls: int | None = None,
    parent_run: str | None = None,
) -> dict:
    if agent is not None and agent_factory is not None:
        raise ValueError("supply an agent instance or agent_factory, not both")
    limits = (
        execution_limits(timeout_seconds, max_tool_calls)
        if (agent_factory is not None or timeout_seconds is not None or max_tool_calls is not None)
        else None
    )
    if agent_factory:
        provider = "custom"
    start = time.perf_counter()
    run_id = uuid.uuid4().hex[:16]
    directory = Path(out).resolve() / run_id
    directory.mkdir(parents=True, exist_ok=False)
    service = PaymentService(directory / "payments.sqlite")
    initial = initial or {"payments": [p.model_dump() for p in scenario.payments], "refunds": []}
    service.restore(initial)
    initial = service.snapshot()
    middleware = FaultMiddleware(service, scenario.faults, scenario.seed)
    responses = []
    error = None
    agent_error = None
    execution_stop = None
    metadata = {
        "kind": provider,
        "version": agent_version,
        "model": model,
        "usage": None,
        "cost_usd": None,
        "conversation_assessment": "unassessed",
    }
    if limits is not None:
        if agent is not None:
            metadata = agent.metadata
        if provider == "scripted" and agent is None:
            metadata = ScriptedAgent(agent_version).metadata
        if agent_factory:
            metadata["factory_reference"] = agent_factory
        outcome = execute_bounded(
            scenario,
            middleware,
            metadata,
            limits,
            provider=provider,
            version=agent_version,
            model=model,
            agent=agent,
            factory=agent_factory,
        )
        metadata = outcome["metadata"]
        responses = outcome["responses"]
        error, agent_error = outcome["error"], outcome["agent_error"]
        execution_stop = outcome["stop"]
        if agent_factory and metadata.get("version"):
            agent_version = metadata["version"]
            model = metadata.get("model")
        metadata = dict(
            metadata,
            execution_metadata_complete=execution_stop is None
            and error is None
            and agent_error is None,
        )
    else:
        try:
            if agent is None:
                if provider == "scripted":
                    agent = ScriptedAgent(agent_version)
                elif provider == "openai":
                    from .openai_agent import OpenAIAgent

                    agent = OpenAIAgent(agent_version, model)
                else:
                    raise ValueError(f"unknown provider: {provider}")
            metadata = agent.metadata
            for index, turn in enumerate(scenario.turns):
                claims = agent.run_turn(turn, middleware)
                responses.append(
                    {
                        "turn": index,
                        "claims": [c.model_dump() for c in claims],
                        "tool_event_end": len(middleware.events),
                    }
                )
        except AgentFailure as exc:
            agent_error = str(exc)
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
    final = service.snapshot()
    service.close()
    result = verify(
        scenario,
        initial,
        final,
        middleware.events,
        responses,
        harness_error=error,
        conversation_assessment=metadata.get("conversation_assessment", "unassessed"),
    )
    if agent_error:
        result["status"] = "agent_failure"
        result.pop("error", None)
        result["violations"].append(
            {
                "rule": "agent_output_valid",
                "expected": "valid final customer claims within the configured step budget",
                "observed": agent_error,
                "event_indices": [e["index"] for e in middleware.events],
            }
        )
        result["conversation_assessment"] = {
            "status": "unassessed",
            "evidence": [],
            "uncertainty": "invalid agent response",
        }
    apply_execution_stop(result, execution_stop, limits, middleware.events)
    scenario_data = scenario.model_dump()
    trace = {
        "trace_version": TRACE_VERSION,
        "run_id": run_id,
        "parent_run": parent_run,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "package_version": __version__,
        "source_commit": source_version(),
        "scenario": scenario_data,
        "scenario_sha256": hashlib.sha256(
            json.dumps(scenario_data, sort_keys=True).encode()
        ).hexdigest(),
        "initial_state": initial,
        "messages": [t.model_dump() for t in scenario.turns],
        "agent": metadata,
        "configuration": {
            "provider": provider,
            "agent_version": agent_version,
            "model": model,
            "seed": scenario.seed,
        },
        "fault_schedule": middleware.schedule,
        "tool_events": middleware.events,
        "backend_events": [b for e in middleware.events for b in e["backend_events"]],
        "responses": responses,
        "final_state": final,
        "result": result,
        "latency_ms": (time.perf_counter() - start) * 1000,
        "reproduction_command": f"agent-chaos rerun {shlex.quote(str(directory / 'trace.json'))}",
        "trial_summary": {
            "total_trials": 1,
            "failure_count": int(result["status"] == "agent_failure"),
        },
    }
    if limits is not None:
        trace["configuration"]["execution_limits"] = limits
        trace["execution_stop"] = execution_stop
    # Reports also embed evidence. A failed write raises a CLI harness error, never prints a pass.
    write_json(directory / "trace.json", trace)
    from .reports import write_html

    write_html(directory / "report.html", trace)
    return trace


def write_json(path: str | Path, data: dict):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    temporary.replace(path)


def read_trace(path: str | Path) -> dict:
    path = Path(path)
    if path.is_dir():
        path = path / "trace.json"
    return validate_trace(
        json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_json_keys)
    )


def unique_json_keys(pairs):
    data = {}
    for key, value in pairs:
        if key in data:
            raise ValueError(f"invalid trace JSON: duplicate key {key!r}")
        data[key] = value
    return data


def rerun(
    trace: dict,
    *,
    out="runs",
    agent_version=None,
    provider=None,
    model=None,
    agent: RefundAgent | None = None,
    agent_factory: str | None = None,
    timeout_seconds: float | None = None,
    max_tool_calls: int | None = None,
) -> dict:
    validate_trace(trace)
    config = trace["configuration"]
    custom = config["provider"] == "custom" or trace["agent"].get("kind") not in (
        "scripted",
        "llm",
        "openai",
    )
    if custom and agent is None and agent_factory is None and provider is None:
        raise ValueError(
            "Custom-agent reruns require a fresh agent instance via Python rerun(..., agent=...). "
            "Use CLI --agent-factory module:callable or the adapter's runner; "
            "traces never load adapter code. "
            "To deliberately switch to a built-in agent, specify provider explicitly."
        )
    return run_scenario(
        Scenario.model_validate(trace["scenario"]),
        agent_version or config["agent_version"],
        out=out,
        initial=trace["initial_state"],
        provider=provider or config["provider"],
        model=model or config.get("model"),
        agent=agent,
        agent_factory=agent_factory,
        timeout_seconds=timeout_seconds
        if timeout_seconds is not None
        else (config.get("execution_limits") or {}).get("timeout_seconds"),
        max_tool_calls=max_tool_calls
        if max_tool_calls is not None
        else (config.get("execution_limits") or {}).get("max_tool_calls"),
        parent_run=trace["run_id"],
    )


def summarize(traces: list[dict]) -> dict:
    statuses = ("pass", "agent_failure", "harness_error", "inconclusive")
    counts = {s: sum(t["result"]["status"] == s for t in traces) for s in statuses}
    rows = []
    for name in sorted({t["scenario"]["name"] for t in traces}):
        group = [t for t in traces if t["scenario"]["name"] == name]
        rows.append(
            {
                "scenario": name,
                "total_trials": len(group),
                **{s: sum(t["result"]["status"] == s for t in group) for s in statuses},
            }
        )
    return {
        "total_trials": len(traces),
        "failure_count": counts["agent_failure"],
        "counts": counts,
        "by_scenario": rows,
        "note": "Fault seeds reproduce schedules; live model reruns can vary.",
    }
