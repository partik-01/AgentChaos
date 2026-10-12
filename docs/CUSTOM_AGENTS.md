# Test your own refund agent

Agent Chaos exposes a Python adapter boundary for **the simulated refund
workflow**. You can use your own agent logic or model client. It does not accept
an arbitrary API URL, discover your tools, or verify other business workflows.
The adapter is local code you explicitly run; recorded traces never import it.

## Run the independent example without an API key

Install the project using the README quick start, then run from the repository:

```bash
python examples/custom_agent.py run scenarios/03_after_timeout.yaml --policy flawed
# Exits 1: the first refund succeeds but times out; a new-key retry commits a second refund.
```

Copy the printed `trace` path into these commands:

```bash
agent-chaos inspect runs/custom/<run-id>/trace.json
python examples/custom_agent.py rerun runs/custom/<run-id>/trace.json --policy flawed
# Exits 1: 600 cents refunded again from the restored initial state.
python examples/custom_agent.py rerun runs/custom/<run-id>/trace.json --policy corrected
# Exits 0: one 300-cent refund, confirmed through the tools.
agent-chaos export runs/custom/<run-id>/trace.json --output runs/custom-failure.json
```

The example prints an `adapter_reproduction_command` with the actual trace path.
Its `MySupportAgent` implements its own policy, rather than wrapping the built-in
`ScriptedAgent`. Both policies are deterministic Python logic, not LLMs. The
corrected example selects the latest pre-execution amount, remembers confirmed
requests, keeps the same idempotency key across bounded retries, and reports
uncertainty when it cannot confirm completion.

## Adapter contract

Implement the `RefundAgent` protocol in `agent_chaos.adapters`:

```python
from agent_chaos.adapters import RefundTools
from agent_chaos.schema import Claim, Turn


class MyAgentAdapter:
    def __init__(self):
        self.metadata = {
            "kind": "custom",
            "name": "my-agent",
            "version": "my-agent-v1",
            "conversation_assessment": "unassessed",
            # Add model/prompt/configuration versions and usage when available.
            # Do not include API keys or other secrets.
        }

    def run_turn(self, turn: Turn, tools: RefundTools) -> list[Claim]:
        # Feed the messages to your application. Replace its payment-tool
        # dispatcher with tools.call(name, arguments). Translate its final
        # response into validated Claim objects. See the runnable example.
        ...
```

A turn contains a batch of customer messages before execution. The newest
amount for a request supersedes earlier amounts in that batch. The same
`request_id` in later turns still represents one business intent.

Route **every** payment operation through `tools.call`. The four supported names
are `get_payment`, `create_refund`, `get_refund_status`, and `list_refunds`; see
[API semantics](API.md) for arguments and observed results. Never connect this
test adapter to a real payment API or read the authoritative database from the
target. If your application bypasses this boundary, Agent Chaos cannot inject
or verify those calls. The Python protocol is an integration contract, not a
security sandbox that prevents arbitrary adapter code from accessing files or
the network.

Return a list of Pydantic `Claim` objects with request, payment, customer, amount,
status and actual customer-facing text. Use `AgentFailure` for invalid agent
output or an exhausted application step budget. Unexpected adapter exceptions
are harness errors; they never count as passes. Bound your own retries, model
steps and timeouts; the synchronous Python runner does not forcibly terminate a
hung custom adapter.

For arbitrary model prose, keep `conversation_assessment: unassessed`. Financial
and structured claim checks still execute, but otherwise-correct runs remain
inconclusive. `deterministic_templates` is only for the exact fixed sentences
from `agent_chaos.agents.claim`, not a way to certify arbitrary text. Record model,
prompt, implementation and dependency versions needed to reconstruct your agent;
usage/cost may be null when unknown. Secrets must stay outside trace metadata.

## Run and rerun from Python

```python
from agent_chaos.runner import read_trace, rerun, run_scenario
from agent_chaos.schema import load_scenario

target = MyAgentAdapter()
trace = run_scenario(
    load_scenario("scenarios/03_after_timeout.yaml"),
    agent=target,
    provider="custom",
    agent_version=target.metadata["version"],
    out="runs/my-agent",
)

# Create another instance: no memory or external state carried from the failed trial.
fixed_target = MyAgentAdapter()
recorded = read_trace("runs/my-agent/<run-id>/trace.json")
fixed = rerun(
    recorded,
    agent=fixed_target,
    provider="custom",
    agent_version=fixed_target.metadata["version"],
    out="runs/my-agent-rerun",
)
```

`read_trace` and `rerun` fully validate recorded evidence. Rerun restores the
initial simulated database and scenario fault seed, then executes the explicitly
supplied instance. It does not restore external agent state or guarantee live
model determinism. For repeated trials, instantiate your adapter separately for
each `run_scenario`, then use `summarize(traces)` to report counts.

The generic trace reproduction command remains `agent-chaos rerun <trace>`.
For a custom target, that command refuses execution with instructions to supply
its adapter; use your adapter runner or the Python call above. It never silently
substitutes a built-in policy. To deliberately compare with the built-in target:

```bash
agent-chaos rerun runs/custom/<run-id>/trace.json --provider scripted --agent corrected
```

Custom targets currently use the Python API or their own runner. The generic
CLI `suite`, `compare`, `minimize`, and `study` do not load custom adapters. The
website can display their recorded traces but cannot execute them. The example
and scenario files are repository assets, not bundled wheel contents.

## Repeated offline regression commands

The example runner also implements a small suite loop with a fresh target for
every trial. These commands save JSON and HTML trial evidence and per-scenario
counts. The flawed suite intentionally exits 1.

```bash
python examples/custom_agent.py suite scenarios --policy flawed --trials 5 --out runs/custom-flawed
python examples/custom_agent.py suite scenarios --policy corrected --trials 5 --out runs/custom-corrected
```

Measured locally on 2026-10-12: this independent example produced **25 failures /
40 flawed trials**, and **0 failures / 40 corrected trials**, with no harness
errors or inconclusive runs. Normal baseline and pre-execution failure both
passed 5/5 per policy; timeout, ambiguous retry, delayed visibility, repeat
requests and malformed responses each failed 5/5 for the flawed policy. Both
policies handled the changed amount. These are public development scenarios and
deterministic scripted tests, not independent holdouts or live-model results.
