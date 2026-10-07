"""Record isolated runs; reruns restore embedded initial state, not current fixtures."""
import hashlib
import json
import subprocess
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from . import __version__
from .agents import AgentFailure, ScriptedAgent
from .faults import FaultMiddleware
from .payments import PaymentService
from .schema import Scenario
from .verifier import verify

TRACE_VERSION = 1


def source_version() -> str:
    try:
        root = Path(__file__).resolve().parents[2]
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root,
                                       stderr=subprocess.DEVNULL, text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def run_scenario(scenario: Scenario, agent_version="corrected", *, out: str | Path = "runs",
                 initial: dict | None = None, provider="scripted", model: str | None = None,
                 agent=None, parent_run: str | None = None) -> dict:
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
    metadata = {"kind": provider, "version": agent_version, "model": model,
                "usage": None, "cost_usd": None, "conversation_assessment": "unassessed"}
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
            responses.append({"turn": index, "claims": [c.model_dump() for c in claims],
                              "tool_event_end": len(middleware.events)})
    except AgentFailure as exc:
        agent_error = str(exc)
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
    final = service.snapshot()
    service.close()
    result = verify(scenario, initial, final, middleware.events, responses, harness_error=error,
                    conversation_assessment=metadata.get("conversation_assessment", "unassessed"))
    if agent_error:
        result = {"status": "agent_failure", "violations": [{"rule": "agent_output_valid",
                  "expected": "valid final customer claims within the configured step budget",
                  "observed": agent_error, "event_indices": [e["index"] for e in middleware.events]}],
                  "conversation_assessment": {"status": "unassessed", "evidence": [],
                                              "uncertainty": "invalid agent response"}}
    scenario_data = scenario.model_dump()
    trace = {"trace_version": TRACE_VERSION, "run_id": run_id, "parent_run": parent_run,
             "created_at": datetime.now(timezone.utc).isoformat(), "package_version": __version__,
             "source_commit": source_version(), "scenario": scenario_data,
             "scenario_sha256": hashlib.sha256(json.dumps(scenario_data, sort_keys=True).encode()).hexdigest(),
             "initial_state": initial, "messages": [t.model_dump() for t in scenario.turns],
             "agent": metadata, "configuration": {"provider": provider, "agent_version": agent_version,
                                                   "model": model, "seed": scenario.seed},
             "fault_schedule": middleware.schedule, "tool_events": middleware.events,
             "backend_events": [b for e in middleware.events for b in e["backend_events"]],
             "responses": responses, "final_state": final, "result": result,
             "latency_ms": (time.perf_counter() - start) * 1000,
             "reproduction_command": f"agent-chaos rerun {directory / 'trace.json'}",
             "trial_summary": {"total_trials": 1, "failure_count": int(result["status"] == "agent_failure")}}
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
    data = json.loads(path.read_text())
    if data.get("trace_version") != TRACE_VERSION:
        raise ValueError("unsupported trace version")
    Scenario.model_validate(data["scenario"])
    return data


def rerun(trace: dict, *, out="runs", agent_version=None, provider=None, model=None) -> dict:
    config = trace["configuration"]
    return run_scenario(Scenario.model_validate(trace["scenario"]),
                        agent_version or config["agent_version"], out=out,
                        initial=trace["initial_state"], provider=provider or config["provider"],
                        model=model or config.get("model"), parent_run=trace["run_id"])


def summarize(traces: list[dict]) -> dict:
    statuses = ("pass", "agent_failure", "harness_error", "inconclusive")
    counts = {s: sum(t["result"]["status"] == s for t in traces) for s in statuses}
    rows = []
    for name in sorted({t["scenario"]["name"] for t in traces}):
        group = [t for t in traces if t["scenario"]["name"] == name]
        rows.append({"scenario": name, "total_trials": len(group),
                     **{s: sum(t["result"]["status"] == s for t in group) for s in statuses}})
    return {"total_trials": len(traces), "failure_count": counts["agent_failure"],
            "counts": counts, "by_scenario": rows,
            "note": "Fault seeds reproduce schedules; live model reruns can vary."}
