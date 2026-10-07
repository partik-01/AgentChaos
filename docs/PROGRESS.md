# Agent Chaos progress

Updated: 2026-10-07. Work is sequential, with a commit for each reviewable
improvement. The user now requests a checkpoint and approval of the next task
before starting it.

## Completed implementation

- Defined the implementation plan, API semantics, and correctness rules before coding.
- Added a Python package, strict Pydantic schemas, SQLite payment service, and tests.
- Implemented seeded fault injection with separate backend and observation evidence.
- Built flawed and corrected scripted refund agents and an independent verifier.
- Added isolated trace recording, JSON/static HTML reports, and the CLI.
- Implemented run, suite, inspect/playback, rerun, compare, and export.
- Added all eight requested development scenarios and two reserved holdout cases.
- Added an optional OpenAI Responses adapter with mocked tests; no live API run.
- Verified the offline MVP before implementing optional extensions.
- Added validated scripted/model scenario proposals, repeated-trial minimization,
  and fixed/generated/random studies with equal target-execution budgets.
- Added request-level financial verification, readable report tables, bounded
  identifiers, and reconciliation of repeated uncertain requests.
- Wrote README, API documentation, experiment documentation, MIT license, and CI.

## Latest completed task

Release recheck completed on 2026-10-07, against source commit `5a237a2`.

- Reviewed payment, fault, agent, verifier, recorder, CLI, generation, minimization,
  report, documentation, and CI implementation sequentially.
- Fixed temporal verification: a truthful earlier noncompletion claim stays valid
  when a later retry commits; a partial/wrong refund still disproves noncompletion.
- Quoted reproduction commands so paths containing spaces can be executed.
- `ruff check src tests`: passed. `ruff format --check src tests`: passed.
- `pytest -q`: **61 passed** on local Python 3.12.
- Built the wheel, installed it into a fresh temporary virtual environment, ran
  `pip check`, and executed a passing normal scenario outside the repository.
- Fresh development and reserved-case comparisons reproduced the counts below.
- Completed a 24-target-run-per-strategy offline discovery study: fixed 18 failures,
  scripted-generated 24, random 3; no harness errors or inconclusive trials.
  These strategies differ in input distribution and generation overhead; this is
  measured demonstration output, not a general ranking or live model benchmark.
- No live model calls were performed. Official OpenAI documentation was rechecked
  for stateless Responses history; the adapter preserves every returned output item.

The prior financial-evidence fix (`0c84ca4`) also remains covered: financial
violations survive invalid target output and provider failure without counting a
broken execution as a pass.

## Recorded offline demonstrations

- Development: flawed script 18 failures / 24 trials; corrected script 0 / 24.
- Reserved cases, evaluated after development checks: flawed 10 / 10; corrected 0 / 10.
- These are scripted demonstration counts, not live-model benchmark claims.
- Reports from these executions exist in ignored local `runs/` directories.

## Release evidence completed

- Added portable measured traces and static HTML under `examples/`:
  normal flawed baseline, timeout failure, corrected rerun, and benchmark summary.
- Verified playback/export of the checked-in failure trace and reran both policies
  from its recorded initial snapshot: flawed commits 600 cents; corrected commits
  the expected 300 cents.
- Visually inspected the HTML report in a browser and refined the tool timeline
  so tool names and fault labels remain readable. Temporary preview was stopped.
- Final post-review checks: **61 tests passed**, lint and format checks passed.

## GitHub status

Remote: https://github.com/partik-01/ChaoticAgent.git

All release implementation and example commits were pushed to `main`, through
`c6664b4`. Local and remote commit hashes were verified identical. This progress
checkpoint is committed and pushed as the final documentation update.

GitHub Actions status could not be verified: the public runs API returned HTTP
404, and the GitHub CLI is unavailable locally. The workflow is committed for
Python 3.11, 3.12, and 3.13, but only local Python 3.12 execution is claimed.
No live OpenAI API calls or live-model benchmark claims were made.

## Next task — awaiting user direction

The offline MVP, optional experiments, release recheck, portable evidence, and
GitHub push are complete. A possible next task is a live OpenAI adapter smoke test
with an account-available model, if the user requests it. It has not been started.
Continue the user's process: one task at a time, record verification and progress,
commit each small improvement, and ask before beginning another task.

## Local preview launch

On 2026-10-07, the user requested launching the project for inspection.
Started the static example-report server at `http://127.0.0.1:8765` and opened
`timeout-flawed.html` in the visible Codex browser. Verified that the report shows
300 cents expected, 600 cents observed, and the exact timeout/commit timeline.
The browser tab and server were intentionally left available for the user.
The MVP application remains a CLI with static HTML reporting; this preview serves
recorded demonstration evidence and does not execute scenarios from a web UI.

## OpenAI adapter validation checkpoint

The user authorized moving to the next task after the preview launch.
Installed the optional OpenAI extra locally (SDK 2.54.0) and verified adapter
initialization and all four tool definitions. Added `tests/test_openai_sdk.py`,
which exercises the actual SDK using an offline HTTP mock transport: creation
commits behind a timeout, the model requests status reconciliation, and exactly
one refund is recorded. The test checks serialized requests, tool outputs, token
usage, raw response recording, and absence of the placeholder credential in traces.
It intentionally retains an inconclusive result for unassessed model prose.

Verification: dependency check passed; lint and formatting passed; **62 tests
passed** with the OpenAI extra installed. The SDK transport test is skipped when
that optional extra is absent; CI installs it. No external model API call was made.

A live smoke test is still awaiting a locally configured `OPENAI_API_KEY` and an
account-available model ID. Neither was configured in the current session. The
user was asked for the model ID and instructed to keep API credentials out of chat.
No different task has been started while that input is pending.

## Completed API-free validation

The user does not have a model API key and requested testing without one.
Ran five fresh trials of all eight development scenarios for each scripted agent,
then reproduced the ambiguous-timeout failure and executed its corrected rerun:
**82 target executions, zero model API calls**.

- Flawed script: **30 failures / 40 trials**, 10 passes.
- Corrected script: **0 failures / 40 trials**, 40 passes.
- Both groups: zero harness errors and zero inconclusive runs.
- Failure rerun retained the identical final ledger and fault schedule: 600 cents
  refunded for a 300-cent request. Corrected rerun from the same initial snapshot:
  one 300-cent refund, pass.
- Saved measured counts and selected full evidence to
  `examples/no-api-validation.json` and `examples/no-api-validation.html`.

These are real executions of the offline SQLite/fault/verifier pipeline using
scripted policies, not mocked payment state or live LLM reliability results.
The live API smoke test is deferred because the user has no API credentials.
No other implementation task was begun during this validation.
