# Trace validation — version 1

Scope: validate version-1 single-run traces before inspection, playback, export,
minimization, or rerun, including direct Python calls to `rerun`. Validation must
finish before creating a run directory, opening SQLite, or constructing an agent.
Work stays sequential, with a commit for each reviewable improvement.

1. Define typed contracts for every required trace section: ledger snapshots,
   faults, tool/backend events, response claims, configuration, metadata, results,
   and trial counts. Reject missing fields, wrong types and non-finite numbers.
2. Check relationships: scenario hash and copied messages; seed and fault schedule;
   tool indices/occurrences and fault references; turn boundaries and violation
   references; unique ledger identifiers and backend effect reconstruction;
   recorded outcomes against deterministic verification.
3. Enforce validation at file and direct rerun entrypoints. Reject duplicate JSON
   keys. Keep valid pass, failure, inconclusive and partial harness-error evidence
   readable. Test malformed input produces a CLI harness error without execution
   or exported output, while existing examples remain compatible.
4. Run regression tests and offline playback/rerun checks, record evidence and
   limitations, and push the completed commits to GitHub.

Financial failures are valid evidence, not malformed traces: duplicate economic
effects and incorrect claims must remain inspectable. Tool argument errors and
unknown tool names are also valid recorded agent behavior when marked as rejected
validation attempts. Model metadata is extensible for raw provider responses and
custom test agents. The validator does not authenticate evidence or run a model;
a scenario hash and internal consistency checks cannot prove external provenance.

## Implemented contract

`src/agent_chaos/traces.py` defines the required sections and nested records with
Pydantic. Input is parsed strictly without silently coercing cents, counters,
seeds, or identifiers. New recorded scenarios include every scenario field,
including their explicit version and optional `tool_rules`. Older version-1
traces may omit `tool_rules`, meaning no extra tool policies. Timestamps require
an ISO format and timezone. Latencies,
costs, token counts and fault draws are bounded; all JSON values must be finite.
Unknown record fields are rejected except extensible agent metadata. The existing
portable examples' optional `export_note` remains supported.

The validator checks the hash against the original scenario JSON representation,
without rewriting numbers or metadata. It reproduces fault scheduling from the
seed, checks contiguous tool indices and per-tool occurrences, and verifies the
selected fault, execution phase and agent observation for each invocation.

It interprets the four simulated API operations **in memory** over recorded state,
without invoking payment tools, SQLite, model clients or network services. Each
authoritative result, commit and idempotent replay must agree with the prior
ledger. The flattened backend timeline and final ledger must agree with those
effects. Unique payment/refund IDs, unique idempotency keys and payment references
are checked separately. A new key that causes a duplicate economic effect is
valid trace data; the independent verifier records its business-rule violation.

Responses must form a contiguous prefix of scenario turns and reference
nondecreasing event boundaries within the timeline. Successful or inconclusive
execution must cover all turns and the final tool event. Violation references
must point to existing events. Deterministic customer text must match its scripted
claim template. Provider text remains separately unassessed. Recorded model usage
must sum the per-call usage, which must agree with the raw provider response.

The recorded verdict, expected intents, violations and conversational assessment
must agree with a fresh deterministic verification of the evidence. Configured
tool-policy failures are also recomputed from the recorded scenario and attempted
calls; changing/removing a violation cannot produce a valid pass. Partial
provider failures and recorded invalid-output exceptions keep their existing
harness/agent classifications and financial consequences. Single-run trial counts
must agree with the verdict. Reproduction commands must have the expected
`agent-chaos rerun <trace-path>` shape; validation never executes that command.

`read_trace` also rejects duplicate JSON keys at any nesting depth, unsupported
versions, non-object roots and malformed JSON. Validation happens before CLI
inspection/export/minimization or rerun execution. `rerun` validates direct dict
inputs too, before creating output directories or constructing an agent.

## Verification and limits

Completed on 2026-10-12: **169 tests passed**, Ruff lint and formatting passed.
Trace-specific tests cover all ten scenarios under both policies, existing
examples, damaged sections and relationships, uncertain visibility, probabilistic
read faults, prior refunds, invalid tool calls, agent setup/provider failures,
and the real optional SDK against an offline HTTP transport. CLI regressions
confirm invalid imports exit 2 without execution or output creation.

Offline end-to-end checks exercised playback, failure reproduction (600 cents),
corrected rerun (300 cents), export, repeated-trial minimization, and a three-trial
development comparison. Flawed: 18 failures / 24 trials; corrected: 0 / 24;
no harness errors or inconclusive trials. All produced single-run traces validated,
and the original example's file hash remained unchanged. A modified ledger was
rejected before a rerun directory was created. Local evidence is under
`runs/trace-validation-2026-10-12/`.

This contract applies to single-run traces, not comparison/study summary imports.
Raw provider metadata is JSON data, not a validation of every provider-specific
field. The validator cannot prove that a reported provider/agent exception actually
happened, that a source commit produced a recording, or that a consistent recording
is authentic. There is no signature or trusted external ledger. Changing all
related fields coherently can evade consistency checks. No live model calls were
made. Future changes to API or fault semantics must preserve the version-1 import
contract or introduce an explicit new trace version.

## Optional execution-stop evidence

Bounded version-1 traces add `configuration.execution_limits` and
`execution_stop`. Validation checks completed-call counts, budgets, deadline
elapsed time, blocked-call presence, initialization evidence and the recomputed
stop verdict. A blocked call was never executed, so it is separate from tool
events. Older traces without these fields remain compatible. See
[execution limits](EXECUTION_LIMITS.md) for semantics and enforcement boundaries.
