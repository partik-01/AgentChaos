"""Standalone custom-agent integration. No OpenAI key or payment network needed."""

import argparse
import json
import shlex
from pathlib import Path

from agent_chaos.adapters import RefundTools
from agent_chaos.agents import claim, confirmed
from agent_chaos.cli import positive, suite_paths
from agent_chaos.reports import write_html
from agent_chaos.runner import read_trace, rerun, run_scenario, summarize, write_json
from agent_chaos.schema import Claim, Message, Turn, load_scenario


class MySupportAgent:
    """Example application policy, independent of the built-in ScriptedAgent."""

    def __init__(self, policy="corrected"):
        self.policy = policy
        self.metadata = {
            "kind": "custom",
            "name": "my-support-agent",
            "version": f"example-v1-{policy}",
            "implementation": "examples/custom_agent.py:MySupportAgent",
            "usage": {"input_tokens": 0, "output_tokens": 0},
            "cost_usd": 0.0,
            # Only use this for the exact fixed sentences produced by claim().
            "conversation_assessment": "deterministic_templates",
        }
        self.answers: dict[str, Claim] = {}
        self.attempts = 0

    def run_turn(self, turn: Turn, tools: RefundTools) -> list[Claim]:
        # Pre-execution changes replace earlier amounts for the same request.
        latest = {message.request_id: message for message in turn.messages}
        return [self.refund(message, tools) for message in latest.values()]

    def refund(self, message: Message, tools: RefundTools) -> Claim:
        if self.policy == "corrected" and message.request_id in self.answers:
            return self.answers[message.request_id]
        args = {
            k: getattr(message, k)
            for k in ("request_id", "payment_id", "customer_id", "amount_cents")
        }
        # Your application's tool dispatcher belongs here. Every payment call
        # must go through tools.call so faults and evidence cover the operation.
        for _ in range(3):
            self.attempts += 1
            key = f"custom:{message.request_id}"
            if self.policy == "flawed":
                key += f":attempt:{self.attempts}"
            result = tools.call("create_refund", args | {"idempotency_key": key})
            if confirmed(result, message):
                answer = claim(message, "completed")
                self.answers[message.request_id] = answer
                return answer
            if result.get("error") in (
                "insufficient_balance",
                "customer_mismatch",
                "payment_not_found",
                "idempotency_conflict",
            ):
                return claim(message, "not_completed")
            if self.policy == "corrected":
                result = tools.call("get_refund_status", {"idempotency_key": key})
                if confirmed(result, message):
                    answer = claim(message, "completed")
                    self.answers[message.request_id] = answer
                    return answer
        return claim(message, "uncertain")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["run", "rerun", "suite"])
    parser.add_argument("input", help="Scenario YAML/directory for run/suite; trace for rerun")
    parser.add_argument("--policy", choices=["flawed", "corrected"], default="corrected")
    parser.add_argument("--out", default="runs/custom")
    parser.add_argument("--trials", type=positive, default=1, help="Trials per scenario for suite")
    args = parser.parse_args(argv)
    if args.mode != "suite" and args.trials != 1:
        parser.error("--trials applies only to suite")
    if args.mode == "suite":
        scenarios = [load_scenario(path) for path in suite_paths(args.input)]
        traces = []
        for scenario in scenarios:
            for trial in range(args.trials):
                target = MySupportAgent(args.policy)
                traces.append(
                    run_scenario(
                        scenario.model_copy(update={"seed": scenario.seed + trial}),
                        target.metadata["version"],
                        agent=target,
                        provider="custom",
                        out=args.out,
                    )
                )
        bundle = {"summary": summarize(traces), "runs": traces}
        write_json(Path(args.out) / "suite.json", bundle)
        write_html(Path(args.out) / "suite.html", bundle)
        print(json.dumps(bundle["summary"], indent=2))
        counts = bundle["summary"]["counts"]
        return (
            2
            if counts["harness_error"]
            else 1
            if counts["agent_failure"]
            else 3
            if counts["inconclusive"]
            else 0
        )
    agent = MySupportAgent(args.policy)  # Fresh memory for every execution.
    options = {
        "agent": agent,
        "agent_version": agent.metadata["version"],
        "provider": "custom",
        "out": args.out,
    }
    if args.mode == "run":
        trace = run_scenario(load_scenario(args.input), **options)
    else:
        trace = rerun(read_trace(args.input), **options)
    path = Path(args.out).resolve() / trace["run_id"] / "trace.json"
    print(
        json.dumps(
            {
                "trace": str(path),
                "result": trace["result"],
                "adapter_reproduction_command": (
                    f"python examples/custom_agent.py rerun {shlex.quote(str(path))} "
                    f"--policy {args.policy}"
                ),
            },
            indent=2,
        )
    )
    return {"pass": 0, "agent_failure": 1, "harness_error": 2, "inconclusive": 3}[
        trace["result"]["status"]
    ]


if __name__ == "__main__":
    raise SystemExit(main())
