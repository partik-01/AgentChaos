# Configurable tool-call rules

Implementation plan: deterministic, optional rules on the recorded calls of the
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
  all calls globally. No `after` calls means no violation.
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
