# Configurable tool-call rules

Deterministic, optional rules on the recorded calls of the
four refund tools. Rules inspect attempted calls, including calls that failed
before execution. They complement financial verification; they do not certify
successful authorization or a correct business outcome.

Add `tool_rules` to version-1 YAML scenarios (omitted means no extra rules):

```yaml
tool_rules:
  - id: check-payment-first
    kind: call_order
    before: get_payment
    after: create_refund
    match_fields: [payment_id, customer_id]
  - id: bounded-refund-attempts
    kind: max_calls
    tool: create_refund
    max: 3
    group_by: [request_id]
  - id: stable-refund-retries
    kind: consistent_args
    tool: create_refund
    group_by: [request_id]
    fields: [payment_id, customer_id, amount_cents, idempotency_key]
```

- `call_order`: every `after` attempt must have a strictly earlier `before`
  attempt with identical `match_fields`. An earlier failed call still counts:
  this checks order, not successful observation. Empty `match_fields` compares
  all calls globally. No `after` calls creates no ordering requirement; invalid
  `before` comparison arguments still produce a missing-argument violation.
- `max_calls`: the number of attempts for `tool` must be at most `max`, including
  faulted and idempotent replay attempts. `max: 0` forbids a tool. `group_by`
  partitions calls by exact argument values; empty means one whole-run group.
- `consistent_args`: all calls for `tool` in each `group_by` group must retain
  identical `fields` values, compared with the first call. Zero or one call
  cannot disagree. Retry identity is specified by `group_by`; calls with a
  different request ID are separate groups, not automatically recognized retries.

All checks span the entire run, including later turns. Grouping/matching fields
must be argument names supported by the specified tool(s). Missing required
comparison/grouping arguments in recorded invalid calls violate the rule rather
than silently skipping it. IDs are unique; unknown rule kinds/tools/fields,
duplicate fields, overlapping consistency/group fields, negative/noninteger
limits and extra options are configuration errors before execution. Rules do
not require a tool to be called, except indirectly when an `after` call needs an
earlier `before`. Financial checks still detect a missing required refund.

Violations are named `tool_rule:<id>` and include expected/observed values plus
event indices. They count as agent failures; harness errors retain precedence.
JSON/HTML reports include them, and trace playback/rerun recomputes them from
recorded rules and calls. Older traces without `tool_rules` remain readable.

## Try the sample without an API key

```bash
agent-chaos run scenarios/tool_rules/refund_policy.yaml --agent flawed
# Exits 1: duplicate refund and changed retry key.
agent-chaos run scenarios/tool_rules/refund_policy.yaml --agent corrected
# Exits 0: financial checks and all three tool policies pass.
agent-chaos run scenarios/tool_rules/refund_policy.yaml --agent-factory examples.custom_agent:make_corrected_agent
# Exits 1: financially correct refund, but this custom example skips get_payment.
agent-chaos suite scenarios/tool_rules --agent corrected --trials 5 --out runs/tool-rules
```

This custom example demonstrates why a developer's chosen tool policy can
matter even when the financial outcome is correct. These are opt-in requirements,
not a claim that every refund workflow must use the same order. The historical
eight scenarios and their benchmark counts are unchanged; the new sample
directory must be selected explicitly.

Inspect/export and rerun a recorded failure with the ordinary commands:

```bash
agent-chaos inspect runs/<run-id>/trace.json
agent-chaos export runs/<run-id>/trace.json --output runs/tool-policy-failure.json
agent-chaos rerun runs/<run-id>/trace.json --provider scripted --agent corrected
```

To reproduce a custom target, explicitly supply its `--agent-factory` again.
Policies are restored with the recorded scenario and rechecked in every rerun.

Local verification on 2026-10-12: five trials each of the built-in flawed,
built-in corrected and independent custom corrected policies. Flawed: 5/5
failures (retry-key policy plus financial consequences); built-in corrected:
5/5 passes; custom corrected: 5/5 call-order failures with exactly 300 cents
refunded. No harness errors or inconclusive runs. A corrected restored-state
rerun passed. These are scripted regression results, not live-model benchmarks.
