# Execution limits

Custom factory executions default to **60 seconds and 100 tool calls per run**,
covering startup, import/construction and all turns. Budgets reset per trial.
The target runs in a fresh spawned worker. The parent owns SQLite, fault
middleware, tool execution and recorded evidence, so stopping a hung agent
retains completed refunds and tool events.

## Commands

The flags are available on `run`, `suite` and `rerun`:

```bash
agent-chaos run scenarios/01_normal.yaml --agent-factory examples.custom_agent:make_corrected_agent
agent-chaos suite scenarios --trials 3 --timeout-seconds 10 --max-tool-calls 20 --out runs/bounded-suite
```

Custom factories always use both limits. Built-in targets and direct Python
`agent=...` instances keep their previous inline behavior unless either limit
is provided; the other then uses its default. `compare`, `generate`, `minimize`
and `study` retain their existing execution paths without these flags.

Seconds must be finite and positive; calls must be a positive integer. Every
attempt counts, including invalid calls, faults and idempotent replays. At the
budget, the next call is blocked **before middleware execution**, with no backend
effect or fabricated tool event. Its name/arguments appear in stop evidence.
Finishing at exactly the budget can still pass. YAML `max_calls` tool rules are
separate post-execution policy checks; this budget actively prevents calls.

## Offline demonstrations

From the repository root with the package installed, no model key required:

```bash
# Exit 1: three reads execute; the fourth is blocked.
agent-chaos run scenarios/01_normal.yaml --agent-factory examples.limited_agents:make_endless_reads --max-tool-calls 3 --out runs/limits

# Exit 1: refund commits, then the target hangs. The ledger retains the refund.
agent-chaos run scenarios/01_normal.yaml --agent-factory examples.limited_agents:make_refund_then_hang --timeout-seconds 2 --out runs/limits
```

Replace `RUN_ID` below with the second command's printed identifier:

```bash
agent-chaos inspect runs/limits/RUN_ID/trace.json
# Exit 1; the recorded two-second deadline is reused.
agent-chaos rerun runs/limits/RUN_ID/trace.json --agent-factory examples.limited_agents:make_refund_then_hang
# Exit 0; corrected target finishes and confirms one refund.
agent-chaos rerun runs/limits/RUN_ID/trace.json --agent-factory examples.custom_agent:make_corrected_agent --timeout-seconds 10
agent-chaos export runs/limits/RUN_ID/trace.json --output runs/limits/export.json
```

These are scripted demonstrations, not live-model benchmarks. A very short
limit or overloaded machine can stop initialization instead of the intended
hang. Inspect `execution_stop.phase` and increase the deadline if needed.

## Evidence and classification

| Condition | Result / CLI exit |
| --- | --- |
| Import or constructor exceeds deadline | Harness error / 2 |
| Import, constructor, serialization or worker crashes | Harness error / 2 |
| Initialized target exceeds deadline | Agent failure / 1 |
| Next call exceeds tool budget | Agent failure / 1 |
| Finishes within limits | Independent verifier decides; completion alone is not a pass |

Setup failures produce per-trial traces and suites continue. New bounded traces
record `configuration.execution_limits` and `execution_stop` (null on
completion). Stops include kind, phase, elapsed milliseconds, completed call
count and any blocked call. A blocked call is not an executed/observed tool
event. HTML reports show the limits and stop alongside the final ledger.
Previously completed responses, events and received metadata are retained.

Inspection and rerun validate stop counts, budget/deadline evidence and the
derived verdict. Older version-1 traces without these optional fields still
work. Reruns retain recorded limits; either flag overrides only that value.
Custom reruns still require an explicitly supplied factory; traces cannot select
Python code to import. Fault seeds do not make live model reruns deterministic.

`agent.execution_metadata_complete` is false after stops/errors. Interrupted
model usage/cost may be missing from the last received metadata; it is not
invented. Zero usage in a script does not imply interrupted live calls are free.
Timing uses a monotonic clock, including process startup.

## Python integration

Prefer `run_scenario(scenario, agent_factory="my_agent:create_agent",
timeout_seconds=30, max_tool_calls=50)` to construct the target inside the worker.
`rerun` accepts the same options. Protect Python script entrypoints with an
`if __name__ == '__main__'` guard; never start runs at module import time.

A supplied `agent=...` instance must be importable and picklable. Local classes
and lambdas generally fail serialization, producing harness errors. Worker
mutations are not copied back to the caller; read the returned trace instead.
Parent monkeypatches do not automatically transfer into a fresh worker.
Parent-side serialization can execute custom Python methods and cannot itself
be forcibly interrupted; use a factory to bound imports/construction and target
code. The older standalone `examples/custom_agent.py` runner stays inline.

## Enforcement boundaries

The parent finishes a simulated tool operation before stopping the worker;
completed commits survive. Parent tool execution, process startup/cleanup and
report finalization can add time beyond the target deadline. Cleanup closes the
per-worker channel, then joins, terminates and, if needed, kills the worker.
Channels are discarded, never reused. See official
[Python multiprocessing guidance](https://docs.python.org/3/library/multiprocessing.html)
for spawn/pickling requirements and termination caveats.

This is process isolation for termination, **not a security sandbox**. It does
not enforce memory/dollar limits, guarantee hard real-time deadlines, interrupt
parent-side code, undo bypassed real API calls, or promise termination of programs
independently spawned by a target. It cannot revoke an external request already
accepted by a provider. Keep network timeouts and bounded retries in your target.
Local verification is on macOS/Python 3.12; Linux/Windows behavior and actual
provider cancellation were not verified here.

[Documentation index](README.md).
