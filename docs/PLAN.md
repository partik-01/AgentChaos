# Agent Chaos implementation plan

Work sequentially and commit each reviewable improvement (including documentation
and usability changes). First establish the refund contract, then build and test:

1. Package and validated versioned scenario models.
2. Transactional SQLite payment service and independent service tests.
3. Seeded fault middleware, observation trace, and timing tests.
4. Scripted flawed/corrected agents and deterministic outcome verifier.
5. Recorder, CLI, JSON/HTML reports, reruns, suites, and comparisons.
6. Eight fixed cases, independent verifier tests, reserved holdout cases.
7. One optional OpenAI Responses tool-calling adapter with mocked tests.
8. Verify the complete offline MVP; write quick start and measured demo evidence.
9. Only after MVP verification: bounded optional generation, minimization, and
   equal-trial-budget comparison; test and document their limitations.
10. Run final checks and push commits to the requested GitHub repository.

## Contract before code

All money is positive integer USD cents; no floats. Payments belong to one
customer. Refunds are immediately committed, immutable, successful ledger entries.
SQLite transactions enforce remaining balance. `create_refund(payment_id,
customer_id, amount_cents, idempotency_key)` validates ownership and available
balance. Keys are global: identical parameters return the original refund even
when remaining balance is now lower; different parameters produce a conflict.
Reads (`get_payment`, `get_refund_status` by key, `list_refunds`) are strongly
consistent at the service layer. Only middleware can obscure their observations.

Every user request has an explicit request ID. Repeated messages for that ID are
one business intent. A changed amount before execution replaces that intent;
a changed amount after execution is unsupported and must not create a new refund.
Messages are grouped into execution turns: all messages in a turn arrive before
its tools execute. This makes the change-before-execution case unambiguous.

Faults select a tool and its 1-based invocation number, with a seeded probability.
Before-failure and rate-limit faults prevent execution. After-timeout and malformed
faults run the service first. Visibility faults hide a newly committed refund from
status/list reads for a specified number of reads, without changing the ledger.
No wall-clock sleeps are needed; delayed visibility uses a logical read clock.

Verifier rules compare initial/final authoritative snapshots: correct customer
and payment, exact total per latest authorized intent, one economic effect per
request, balance safety, no unrelated mutations, and structured customer claims
consistent with both ledger and observed confirmation. Explicit uncertainty with
otherwise correct finances is inconclusive, never a pass. Missing execution,
provider failures, and recorder failures are harness errors, never passes.
Deterministic structured claims do not prove arbitrary natural-language accuracy;
LLM prose is recorded and conversational assessment is reported separately as
unassessed, making otherwise correct live runs inconclusive.

Traces include full snapshots, ordered tool/observation/backend events, messages,
responses, exact scenario and prompts/configuration, package/source versions,
model metadata, latency, token usage, and cost when supplied. Playback is read-only;
rerun restores the snapshot and executes again. Seeds reproduce fault decisions,
not live model output. Scripted runs are deterministic except IDs and timing.
