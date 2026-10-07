# Simulated payment API v1

Python methods and model tools share these schemas. There is no real payment API,
HTTP server, authentication, pending settlement, cancellation, or FX support.
Every amount is a **positive integer USD cent amount**, with strict validation
that rejects floats, booleans, and numeric strings. Identifiers are 1–200 characters.

| Tool | Arguments | Success result |
| --- | --- | --- |
| `get_payment` | `payment_id`, `customer_id` | Payment, `refunded_cents`, `remaining_cents` |
| `create_refund` | `request_id`, `payment_id`, `customer_id`, `amount_cents`, `idempotency_key` | Immutable refund with `refund_id`, parameters, `status: succeeded` |
| `get_refund_status` | `idempotency_key` | Refund, or `status: not_found` with the key |
| `list_refunds` | `payment_id`, `customer_id` | `{refunds: [...]}` for that payment |

Keys are globally unique across payments. Identical retries return the original
refund before checking the current remaining balance. Different request ID, payment, customer,
or amount with the same key raises `idempotency_conflict`. Creation validates
ownership and remaining balance inside `BEGIN IMMEDIATE`; concurrent writers
cannot overdraw. `customer_mismatch`, `payment_not_found`, and
`insufficient_balance` reject creation without an economic effect. Refunds cannot
be updated or deleted through the tool interface. Snapshot restoration is a
harness-only operation, used to isolate trials and restore recorded initial state.

The middleware returns errors as tool observations. `executed: false` applies to
known rejection or pre-execution failure; `executed: unknown` applies to timeout
or malformed data. The agent never receives the authoritative `backend_result`
or `backend_events` fields recorded for verification.

## Fault semantics

Each YAML fault selects one tool invocation by 1-based `occurrence`. Probability
is sampled once per fault with a local seeded RNG, in YAML order, before execution.
Schedules include exact draws and enabled flags; an enabled fault may still be
unreached if the agent never calls that invocation. Only one fault may occupy a
(tool, occurrence) pair.

| Fault | Timing and observation | Ledger consequence |
| --- | --- | --- |
| `before_failure` | Before service execution: `unavailable` | No execution |
| `rate_limit` | Before execution: `rate_limited`, `retry_after_ms: 100` | No execution |
| `after_timeout` | Run service, then return `timeout` | Successful writes remain committed |
| `malformed` | Run service, then return broken raw JSON and `malformed_response` | Successful writes remain committed |
| `visibility_delay` | Only on creation; return `pending`; hide this refund from the next `hidden_reads` matching status/list reads | Refund is committed immediately |

Visibility delay uses a logical observation clock, not elapsed seconds. A list
read decrements each hidden matching refund once. Payment balance reads remain
strongly consistent. An idempotent creation replay can still return the committed
refund, so reconciliation has an alternative to delayed read paths. A service
rejection takes precedence over an after-execution fault: there is no successful
result to corrupt. Bounded retry counts are agent policy, not a reliability proof.

## Authorization and verification

Messages in one turn arrive before execution. The latest amount for each request
ID in that batch is authoritative. Repetition across turns retains that identity;
changing its payment/customer or its amount after an execution turn is rejected
as an unsupported scenario. A new request requires a new ID. The reference
verifier allocates valid intents in message/turn order against initial balances.
An unknown payment, wrong customer, or excess amount is expected to have no effect.
This is a declared, narrow policy: simultaneous distinct intents must be served
in this order; the scenario editor should not imply a different policy in prose.

Refund rows carry an explicit request ID independently of their idempotency key.
The service does not make request IDs unique: a buggy retry with a new key must
remain observable. Financial checks use snapshots and refund multiset/counts per
request ID, independently of the
agent's structured claims. Completion claims require a matching refund and a
matching succeeded observation **before the response**. `not_found` is not proof
of a missing refund. An otherwise correct ledger with uncertainty is inconclusive.
An unexecuted or broken test is a harness error. Incorrect or missing customer
claims and target step-budget exhaustion are agent failures. Financial failures
retain priority over uncertainty or unassessed conversational quality.

The scripted agents use deterministic sentence templates. Real model runs expose
structured claims for these checks, but their accompanying prose is recorded as
**unassessed**: no model judge is included, and otherwise correct live runs are
inconclusive. Any future model judge must remain a separate assessment with its
own evidence and uncertainty; it must not override financial checks.
