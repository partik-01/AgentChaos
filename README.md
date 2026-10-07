# Agent Chaos

**Find out what an agent actually did when its tools failed.** Agent Chaos tests a
customer-support refund workflow against a simulated SQLite payment ledger. It
injects precisely timed faults, independently verifies the business outcome, and
saves enough evidence to inspect a failure and rerun it against another agent.

MIT licensed. Python 3.11+. **Simulated payments only.** No real payment credentials
or payment network access. The default agents are deterministic Python scripts;
the optional OpenAI adapter runs a real tool-calling model.

## Quick start (no API key)

```bash
git clone https://github.com/partik-01/ChaoticAgent.git
cd ChaoticAgent
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
pytest -q
agent-chaos run scenarios/01_normal.yaml
agent-chaos run scenarios/03_after_timeout.yaml --agent flawed
# The previous command intentionally exits 1: it exposes a duplicate refund.
agent-chaos compare scenarios --trials 5 --out runs/comparison
```

Every run saves `trace.json`, `report.html`, and `payments.sqlite` in an isolated
`runs/<run-id>/` directory. The CLI prints the exact reproduction command. Open
the HTML file directly in a browser. Suite and comparison commands also export
JSON and HTML containing all trial evidence and counts per scenario.

```bash
agent-chaos inspect runs/<run-id>/trace.json
agent-chaos playback runs/<run-id>/trace.json   # Read-only, offline inspection
agent-chaos rerun runs/<run-id>/trace.json      # Executes again from saved initial state
agent-chaos rerun runs/<run-id>/trace.json --agent corrected
agent-chaos export runs/<run-id>/trace.json --output failure.json
agent-chaos suite scenarios --agent corrected --trials 10 --out runs/suite
agent-chaos compare scenarios/heldout --trials 5 --out runs/holdout
```

Exit codes: `0` pass (or successful inspection/export); `1` agent failure;
`2` harness error; `3` inconclusive. Comparison's exit code reflects the corrected
agent, since flawed failures are intentional. CLI usage errors exit `2`. A broken
provider or invalid scenario can never count as a pass.

## Example failure

Browse [checked-in JSON/HTML evidence and measured counts](examples/README.md),
including a failed timeout trace and its corrected-agent rerun.

In `03_after_timeout`, the first `create_refund` commits **300 cents** but the
middleware returns a timeout. The flawed agent retries with a new key, committing
another **300 cents**. It tells the customer only 300 cents were refunded.

The verifier reports `exact_total_refunded` (expected 300, observed 600) and
`no_duplicate_economic_effect`. The report shows both committed refund rows,
the original arguments and idempotency keys, the injected `after_timeout` fault,
and the distinction between the successful backend result and the timeout the
agent saw. The corrected agent reconciles the original refund or retries with
the same key, producing one economic effect. This example can be reproduced
without a model API key.

## Architecture

| Component | Responsibility |
| --- | --- |
| `schema.py` | Pydantic contracts; version 1 YAML scenarios; strict integer cents |
| `payments.py` | Authoritative SQLite ledger; transactional balance limits and global idempotency |
| `faults.py` | Seeded fault schedule; backend results kept separate from agent observations |
| `agents.py` | Intentionally flawed and corrected scripted refund policies |
| `openai_agent.py` | One optional OpenAI Responses API adapter using the same tools |
| `verifier.py` | Independent deterministic financial and structured-claim checks |
| `runner.py` | Isolated state, recording, snapshot restoration, trial summaries |
| `reports.py`, `cli.py` | Static escaped HTML, JSON, CLI inspection and comparisons |

The agent gets only tool observations. The verifier reads authoritative snapshots
and events, not the agent's success label. It checks the right payment/customer,
exact amount, balance safety, duplicate economic effects, unrelated state, and
claims supported by observations available before the response.

Read [API semantics and correctness rules](docs/API.md) and the
[sequential implementation plan](docs/PLAN.md). One request ID means one business
intent. Messages in a turn arrive before tool execution; the latest amount wins.
Repeating that request across turns must not issue another refund. Changing an
amount after an execution turn is outside this MVP and rejected by validation.

## Fixed scenarios

| Scenario | Expected behavior |
| --- | --- |
| 01 Normal | One confirmed 300-cent refund |
| 02 Failure before creation | Safe retry; one refund |
| 03 Success followed by timeout | Reconcile the committed refund |
| 04 Retry after ambiguous timeout | Preserve the original key even when reconciliation tools fail |
| 05 Temporarily invisible refund | Absence is not failure; confirm or report uncertainty |
| 06 Customer changes amount | Latest pre-execution amount, 200 cents |
| 07 Customer repeats request | Reuse the existing outcome; one refund |
| 08 Malformed creation response | Reconcile a possible commit; no duplicate |

Each YAML includes `expected_behavior`. Additional reserved cases combine an
ambiguous commit near the balance limit with a new request, and rate limiting
with malformed data. Normal suite discovery excludes the `heldout` subdirectory.
They were evaluated only after the development suite and adapter tests passed.
This small author-designed holdout is useful regression evidence, not an
independent scientific benchmark; after publication these cases are public.

## Workflow website

For a simple explanation of the project, launch the included static walkthrough:

```bash
python3 -m http.server 8765 --bind 127.0.0.1 --directory examples
```

Open [the local workflow website](http://127.0.0.1:8765/). Step through a refund,
compare the flawed and corrected policies, see actual ledger state versus agent
observations, and open the measured reports. The page also explains the five
components and provides offline CLI commands. It is educational playback of
recorded examples; fresh test execution happens through the CLI.

## Optional live model

```bash
pip install -e '.[openai]'
export OPENAI_API_KEY=your_key
agent-chaos run scenarios/03_after_timeout.yaml --provider openai --model YOUR_MODEL_ID
agent-chaos compare scenarios --provider openai --model YOUR_MODEL_ID --trials 5
```

Choose a model available to your account that supports tools and structured
outputs. The adapter follows the official
[OpenAI function-calling documentation](https://developers.openai.com/api/docs/guides/function-calling).
It uses bounded tool loops, records the exact prompts and raw model outputs,
records token usage, disables hidden SDK retries, and leaves cost null when the
provider supplies no dollar cost. API calls may incur charges. Model unavailability
is a harness error. Invalid target responses or exhausted target steps are agent
failures. Live integration has mocked tests; no live-model benchmark is claimed.

Financial checks remain deterministic. Model-generated customer prose is
**unassessed**, recorded separately from structured claims, and makes otherwise
correct live runs inconclusive. No model judge silently overrides financial rules.
Scripted template sentences are checked deterministically. Uncertainty is also
inconclusive when finances are otherwise correct, never a pass.

## Reproducible validation

```bash
pytest -q
ruff check src tests
ruff format --check src tests
agent-chaos compare scenarios --trials 3 --seed 17 --out runs/fixed
agent-chaos compare scenarios/heldout --trials 5 --seed 17 --out runs/heldout
```

The first verified offline development run measured **18 failures / 24 trials**
for the flawed script and **0 / 24** for the corrected script. The reserved cases
measured **10 / 10** and **0 / 10**, respectively. Results are counted by scenario,
including harness errors and inconclusive trials separately. Normal execution
passes for both scripts; failures expose specific fault or interaction handling.
These counts are deterministic demonstration results, not LLM reliability rates
or confidence estimates. Repeated identical scripts offer regression evidence;
they do not provide independent statistical samples.

## Optional experiments after the MVP

```bash
agent-chaos generate scenarios/01_normal.yaml --output runs/generated.yaml
agent-chaos minimize runs/<failed-run-id>/trace.json --trials 3 --budget 60
agent-chaos study scenarios --agent flawed --budget 24 --seed 17 --out runs/study
```

Generation is scripted offline by default; `--provider openai --model ...` uses
an optional proposal agent. The minimizer removes faults/messages/turns only when
the same violated rule survives every trial. The study compares fixed cases,
generated proposals, and seeded random faults with equal target-execution counts.
Generation overhead is additional and recorded. See [experiment semantics,
budgets, and limitations](docs/EXPERIMENTS.md).

## Evidence and limitations

Traces record initial/final database snapshots, all user messages and responses,
tool arguments/results, exact fault decisions, backend events, scenario hash,
package/source versions, prompt/configuration/model metadata, latency, tokens,
and available cost. Local reports may contain customer text or model outputs;
use simulated input and review traces before sharing them. API keys are not
intentionally recorded. Traces are evidence files, not signed tamper-proof audits.

Offline playback inspects saved events; a scenario rerun restores initial state
and executes the agent again. Fault seeds reproduce scheduling decisions, **not
live model output**. A changed source version can change behavior; pin the recorded
commit for strict code reproduction. Timing and run IDs vary even for scripts.

This MVP has one workflow, one provider, immediate successful refund settlement,
logical-read visibility delays, and bounded retries. It does not cover asynchronous
payment settlement, genuine concurrent customer conversations, fraud policy,
production tools, authentication, billing, distributed execution, monitoring,
automatic fixes, or arbitrary agent frameworks. A corrected demo passing a small
suite is not a proof of reliability outside the declared contract.

Contributions: use small focused commits, add a scenario/test for behavioral
changes, and run the checks above. See [LICENSE](LICENSE).
