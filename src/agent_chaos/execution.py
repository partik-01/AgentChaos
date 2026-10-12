"""Spawned targets; authoritative tools and evidence remain in the parent."""

import json
import math
import multiprocessing
import time

from .adapters import create_custom_agent, load_agent_factory
from .agents import AgentFailure, ScriptedAgent
from .schema import Turn

DEFAULT_TIMEOUT = 60.0
DEFAULT_TOOL_CALLS = 100


def execution_limits(timeout_seconds=None, max_tool_calls=None):
    seconds = DEFAULT_TIMEOUT if timeout_seconds is None else timeout_seconds
    calls = DEFAULT_TOOL_CALLS if max_tool_calls is None else max_tool_calls
    if type(seconds) not in (int, float) or not math.isfinite(seconds) or seconds <= 0:
        raise ValueError("timeout_seconds must be finite and positive")
    if type(calls) is not int or calls < 1:
        raise ValueError("max_tool_calls must be a positive integer")
    return {"timeout_seconds": float(seconds), "max_tool_calls": calls}


def send(connection, message):
    # JSON only: no target-produced pickle is deserialized in the parent.
    connection.send_bytes(json.dumps(message, allow_nan=False).encode())


def receive(connection):
    return json.loads(connection.recv_bytes())


class RemoteTools:
    def __init__(self, connection, agent):
        self.connection = connection
        self.agent = agent

    def call(self, tool, arguments):
        send(
            self.connection,
            {"type": "tool", "tool": tool, "arguments": arguments, "metadata": self.agent.metadata},
        )
        return receive(self.connection)


def worker(connection, turns, provider, version, model, agent, factory):
    try:
        if factory:
            agent = create_custom_agent(load_agent_factory(factory))
            agent.metadata = dict(agent.metadata, factory_reference=factory)
        elif agent is None:
            if provider == "scripted":
                agent = ScriptedAgent(version)
            elif provider == "openai":
                from .openai_agent import OpenAIAgent

                agent = OpenAIAgent(version, model)
            else:
                raise ValueError(f"unknown provider: {provider}")
        send(connection, {"type": "ready", "metadata": agent.metadata})
        tools = RemoteTools(connection, agent)
        for index, data in enumerate(turns):
            claims = agent.run_turn(Turn.model_validate(data), tools)
            send(
                connection,
                {
                    "type": "response",
                    "turn": index,
                    "claims": [claim.model_dump() for claim in claims],
                    "metadata": agent.metadata,
                },
            )
        send(connection, {"type": "done", "metadata": agent.metadata})
    except (EOFError, BrokenPipeError):
        # The parent closes its endpoint when enforcing a stop. No error can
        # be delivered then; avoid a misleading worker traceback on stderr.
        pass
    except Exception as exc:
        try:
            send(
                connection,
                {
                    "type": "agent_error" if isinstance(exc, AgentFailure) else "error",
                    "message": f"{type(exc).__name__}: {exc}",
                    "metadata": getattr(agent, "metadata", None),
                },
            )
        except (EOFError, BrokenPipeError):
            pass
    finally:
        connection.close()


def execute_bounded(
    scenario,
    middleware,
    metadata,
    limits,
    *,
    provider,
    version,
    model=None,
    agent=None,
    factory=None,
):
    context = multiprocessing.get_context("spawn")
    parent, child = context.Pipe()
    process = context.Process(
        target=worker,
        args=(
            child,
            [turn.model_dump() for turn in scenario.turns],
            provider,
            version,
            model,
            agent,
            factory,
        ),
        daemon=True,
    )
    outcome = {
        "metadata": metadata,
        "responses": [],
        "error": None,
        "agent_error": None,
        "stop": None,
    }
    started = time.monotonic()
    ready = False

    def stop(kind, blocked=None):
        outcome["stop"] = {
            "kind": kind,
            "phase": "agent" if ready else "initialization",
            "elapsed_ms": (time.monotonic() - started) * 1000,
            "completed_tool_calls": len(middleware.events),
            "blocked_call": blocked,
        }

    try:
        process.start()
        child.close()
        while True:
            remaining = limits["timeout_seconds"] - (time.monotonic() - started)
            if remaining <= 0:
                stop("deadline")
                break
            if not parent.poll(min(remaining, 0.05)):
                if not process.is_alive():
                    raise RuntimeError(
                        f"target worker exited without completion (exit {process.exitcode})"
                    )
                continue
            message = receive(parent)
            if message.get("metadata") is not None:
                outcome["metadata"] = message["metadata"]
            kind = message["type"]
            if kind == "ready":
                ready = True
            elif kind == "tool":
                if len(middleware.events) >= limits["max_tool_calls"]:
                    stop(
                        "tool_budget", {"tool": message["tool"], "arguments": message["arguments"]}
                    )
                    break
                send(parent, middleware.call(message["tool"], message["arguments"]))
            elif kind == "response":
                outcome["responses"].append(
                    {
                        "turn": message["turn"],
                        "claims": message["claims"],
                        "tool_event_end": len(middleware.events),
                    }
                )
            elif kind == "done":
                break
            elif kind in ("error", "agent_error"):
                outcome[kind if ready else "error"] = message["message"]
                break
            else:
                raise ValueError("invalid target worker protocol")
    except Exception as exc:
        outcome["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        child.close()
        parent.close()
        if process.pid is not None:
            process.join(0.2)
            if process.is_alive():
                process.terminate()
                process.join(0.2)
            if process.is_alive():
                process.kill()
                process.join(1)
            process.close()
    return outcome


def apply_execution_stop(result, stop, limits, events):
    if stop is None:
        return
    if stop["phase"] == "initialization":
        result["status"] = "harness_error"
        result["error"] = "execution deadline exceeded during target initialization"
    else:
        result["status"] = "agent_failure"
        result.pop("error", None)
        rule = "execution_deadline" if stop["kind"] == "deadline" else "execution_tool_budget"
        result["violations"].append(
            {
                "rule": rule,
                "expected": limits,
                "observed": stop,
                "event_indices": [event["index"] for event in events],
            }
        )
    result["conversation_assessment"] = {
        "status": "unassessed",
        "evidence": [],
        "uncertainty": "execution limit reached",
    }
