# Execution limits

Implementation contract: bounded targets execute in a fresh spawned process.
The parent owns SQLite, fault middleware, tool execution and recorded evidence.
The worker receives observed tool results only. A deadline can stop sleeping,
looping or blocked target code without terminating a ledger write mid-operation.

Custom factory executions default to 60 seconds and 100 tool calls per run,
including import/construction and all turns. Explicit limits enable the same
execution path for built-in targets or a supplied Python agent instance.
Unbounded direct Python calls remain compatible when no limits/factory are given.

`--timeout-seconds` must be finite and positive; `--max-tool-calls` is a positive
integer. Limits count all tool attempts, including invalid calls, faults and
idempotent replays. The next call beyond the budget is blocked before middleware
execution: no backend effect or fabricated tool event. Its name/arguments are
recorded separately in the stop evidence. Normal execution at exactly the call
budget can still pass.

Deadline expiry during import/construction is a harness error. After the target
initializes, deadline or tool-budget exhaustion is an agent failure, never a
pass. Previously completed calls, responses, authoritative state and available
model metadata are retained. Missing in-flight provider usage is not invented.
Worker crashes are harness errors; suites should continue and include their
counts. Reruns restore the recorded limits unless explicitly overridden.

This is process isolation for termination, not a security sandbox. It does not
undo bypassed real API calls, enforce memory/dollar limits, guarantee hard
real-time timing, or promise termination of programs independently spawned by a
target. Parent simulated tool execution and report finalization can add time.
Direct Python instances must be spawn-picklable; an importable zero-argument
factory is preferred. Python entrypoints need an `if __name__ == '__main__'`
guard for spawned execution. No thread or signal-only deadline fallback.
