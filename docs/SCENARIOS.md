# Write a refund scenario

A version-1 YAML file declares payments, customer requests, faults and optional
tool policies. It is validated before agent execution. Change one behavior at
a time and choose a distinct name for a new case.

## Complete example

Save this as `my_refund.yaml` in the repository root:

```yaml
version: 1
name: my_timeout_case
description: Refund commits but the first response times out.
expected_behavior: Confirm the original refund or retry with its original key.
seed: 17
split: development
payments:
  - payment_id: payment_demo
    customer_id: customer_demo
    amount_cents: 1000
turns:
  - messages:
      - request_id: refund_demo
        payment_id: payment_demo
        customer_id: customer_demo
        amount_cents: 300
        text: Please refund 300 USD cents.
faults:
  - tool: create_refund
    occurrence: 1
    kind: after_timeout
```

```bash
agent-chaos run my_refund.yaml --agent flawed
# Expected exit 1: duplicate refund.
agent-chaos run my_refund.yaml --agent corrected
# Expected exit 0: one confirmed refund.
```

`expected_behavior` is human-readable documentation, not executable logic or a
model judge. The verifier derives authorization from structured messages and
payment state; [tool rules](TOOL_RULES.md) add explicit extra requirements.

## Fields and request identity

| Field | Meaning |
| --- | --- |
| `version` | Currently `1` |
| `name`, `description`, `expected_behavior` | Identity and human-readable context |
| `seed` | Fault scheduling seed, default `0` |
| `split` | `development`, `heldout` or `generated`; label, not a discovery filter |
| `payments` | Unique payment IDs, customer owners and positive integer cents |
| `turns` | Message batches before each agent execution turn |
| `faults` | Optional list; empty means no faults |
| `tool_rules` | Optional call-order/count/argument policies |

Unknown fields are rejected. Identifiers are 1–200 characters; idempotency keys
are 1–256. `300` means $3.00; amount strings, floats and booleans are rejected.
An unknown payment, wrong owner or excessive amount is a valid negative test
whose expected economic effect is zero.

Every message includes request/payment/customer IDs, amount and text. Structured
fields determine authorization; the harness does not parse arbitrary prose to
infer a different amount. Same request ID means one business intent. The latest
amount for that request within a pre-execution batch wins. After the turn, its
amount/payment/customer cannot change; a distinct request needs a new ID.
Different intents consume available balance in declared message/turn order.

YAML fixtures start with payments and no refunds. Advanced Python runs and
trace reruns can restore initial refund rows; YAML has no `refunds` fixture field.
Read [API/authorization semantics](API.md) for the exact contract.

## Fault timing

Tools are `get_payment`, `create_refund`, `get_refund_status`, `list_refunds`.
`occurrence` is the 1-based invocation number for that tool across the whole
run. Only one fault can occupy a tool/occurrence slot.

| Kind | Effect |
| --- | --- |
| `before_failure` | Unavailable before execution; no backend effect |
| `rate_limit` | Rate-limited before execution; no backend effect |
| `after_timeout` | Operation executes, then the agent receives timeout |
| `malformed` | Operation executes, then response data is malformed |
| `visibility_delay` | Creation commits but appears pending/absent to matching reads |

`probability` defaults to `1`, ranges from `0` to `1`, and is sampled once per
fault before execution using the seed. Scheduled faults can be unreached if the
agent does not make that call; compare `fault_schedule` with `tool_events`.
Visibility delay attaches only to creation. `hidden_reads` defaults to `3` and
counts logical matching status/list reads, not seconds. An idempotent creation
replay can still confirm the original refund. See [fault precedence](API.md).

## Sample inventory

| Case | Expected behavior |
| --- | --- |
| 01 Normal | One confirmed 300-cent refund |
| 02 Before failure | Safely retry after no execution |
| 03 Timeout | Reconcile the committed refund |
| 04 Ambiguous retry | Preserve the key when reconciliation also fails |
| 05 Delayed visibility | Confirm or report uncertainty; absence is not failure |
| 06 Changed amount | Latest pre-execution amount, 200 cents |
| 07 Repeated request | One economic effect |
| 08 Malformed response | Reconcile possible commit without duplication |
| `scenarios/heldout/` (2 cases) | Balance-edge ambiguity and combined faults |
| `scenarios/tool_rules/` (1 case) | Lookup order, attempt limit and stable retries |

`suite scenarios` selects only the eight immediate YAML files. Directory, not
`split`, determines discovery. Published reserved cases are public regression
examples, not independent scientific holdouts.

[CLI](CLI.md) · [Tool policies](TOOL_RULES.md) · [Documentation index](README.md).
