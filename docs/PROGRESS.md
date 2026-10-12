# Agent Chaos progress

Updated: 2026-10-12. Work is sequential, with a commit for each reviewable
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

## Completed workflow website task

The user requested a simple website explaining the website and project workflow.
Added `examples/index.html` and `examples/workflow.js` in sequential commits.
The existing local server now opens the explainer at `http://127.0.0.1:8765/`.

The page covers customer request, payment validation, refund commit, hidden timeout,
agent handling, and independent verification. The flawed/corrected switch shows
600 versus 300 cents alongside what the agent knows. Additional sections explain
all five project components, the static website's role, report playback/reruns,
uncertainty, saved evidence, and runnable offline CLI commands.

Browser verification: timeout state is 300 committed cents with unknown agent
outcome; flawed final state is 600 cents; corrected final state is 300 cents and
pass. Verified direct step selection, restart, keyboard Enter navigation, policy
switching, command copying, and report navigation/back. Confirmed all local report
links, section anchors, and script references exist. CSS supplies narrow-screen
layouts and reduced-motion handling; no mobile-device test is claimed.

The page is educational playback, not a new agent-execution web backend. It is
self-contained with no third-party asset dependencies or API key requirement.
The preview was left open at the first step for the user. This task is complete;
ask for the next task before beginning a different implementation.

## Vercel deployment task (in progress)

The user authorized publishing the workflow website to Vercel and adding its
live link to the GitHub repository. Installed the remote Vercel MCP config
globally for Codex. The supplied installer's default selection included Claude
Desktop, which rejected HTTP transport; retried successfully with `--agent codex`.
MCP configuration installation does not itself authenticate an account.

Committed static deployment settings: framework disabled, no dependency install
or build command, `examples/` output, CLI upload allowlist, and ignored local
Vercel metadata. Documented the production deployment command.

Vercel CLI rejected its saved token. Started device authentication and opened the
sign-in page for the user. Production deployment and the live README link are
pending successful account authentication; no deployed URL is claimed yet.

## Completed system review and cleanup — 2026-10-12

Reviewed the source, CLI, offline workflows, website and deployment state.
Removed one unused fault field in its own commit. Then fixed comparison exit
codes so a flawed-side harness error or inconclusive trial cannot be hidden by
corrected-side passes, with seven new regression cases and its own commit.

Final checks: 69 tests passed; lint, format, JavaScript syntax and local website
links passed. Fresh five-trial comparisons across ten scenarios: corrected
50/50 passes; flawed 40/50 failures, with zero harness errors or inconclusive
runs. Timeout rerun reproduced 600 cents; corrected rerun committed 300 cents.
Generation, minimization, study, playback and JSON/HTML export were exercised.
Browser checks confirmed both policies and saved report navigation.

Full scope, commands, measured counts, limits and proposed next tasks are in
[REVIEW.md](REVIEW.md). Local evidence is in `runs/review-2026-10-12/`.
Vercel remains logged out; live model execution and remote CI are unverified.
This review/cleanup task is complete. Ask for the next task before implementing
any of the proposed additions.

## Full trace validation task — completed

The user authorized full trace validation and a final GitHub push. The work plan
and acceptance rules are in [TRACE_VALIDATION.md](TRACE_VALIDATION.md): typed
contracts, cross-section checks, validation before all trace-consuming CLI paths
and direct rerun execution, damaged-trace regressions, and compatibility checks
for recorded failures and partial harness errors. No other feature task is being
started.

Sequential implementation commits:

- `cf6b225`: contract, plan and progress checkpoint before implementation.
- `6963009`: typed nested trace models, required sections and structural tests.
- `15b98e8`: cross-section consistency, in-memory effect reconstruction and verdict
  verification; valid saved failures and mocked SDK evidence accepted.
- `c41f9b0`: strict file imports, duplicate-key rejection and validation before
  direct reruns; CLI regressions prove rejection before execution/output.
- `0fdd63a`: compatibility cases for prior refunds, probabilistic read faults,
  unresolved visibility and agent setup errors.

Final validation: **169 tests passed**, lint/format/diff checks passed. Offline
playback, export, minimization and both rerun policies completed. Timeout failure
reproduced 600 cents; corrected rerun committed 300 cents. Three-trial development
comparison: flawed 18/24 failures, corrected 24/24 passes, no harness errors or
inconclusive trials. Every newly produced trace validated; the source example
was unchanged. Deliberately modified ledger evidence was rejected with exit 2
before its rerun directory was created.

The README and [TRACE_VALIDATION.md](TRACE_VALIDATION.md) document the contract,
recorded-error handling, evidence location, and limits. Validation checks internal
consistency, not provenance or authenticity, and requires no model API key.
This task is complete; no suggested follow-up feature was started.

## Refund boundary and concurrency task — completed

The user authorized the next improvement from the review. Scope: independently
test the simulated payment service with prior partial refunds, exact remaining
balance and one-cent-over-balance requests, and synchronized competing requests
through separate SQLite connections. Check ledger state, idempotent replay,
conflicting key reuse, transaction rollback and backend event counts. Implement
one improvement at a time, commit each, run the full suite, then push to GitHub.
No new website or model-provider feature is included in this task.

Sequential commits:

- `fe5b752`: scope and acceptance plan before implementation.
- `1b66d2d`: restored partial-refund balance boundaries (including one cent
  remaining), one-cent overflow rollback, valid retry after rejection, and all
  four conflicting-key parameter checks.
- `505b8b5`: barrier-synchronized SQLite connections, stronger existing overdraw
  check, and five repetitions each of identical-key, conflicting-key and
  distinct-key partial-balance races.

Final local validation: **31 payment-service tests passed; 191 total tests passed**.
Ruff lint and formatting passed. The race tests executed 62 competing requests
across fresh databases, with expected commit/replay/rejection counts and no
unexpected lock errors. No service behavior change was needed: the existing
transaction and idempotency implementation satisfied the new independent tests.
The API documentation and README include the command, tested outcomes and limits.
These tests require no API key and make no benchmark or exhaustive concurrency
claim. This task is complete; no following feature was started.

## Offline trace viewer and usability assessment — completed

The user authorized the offline JSON viewer and requested an honest assessment
of usefulness for other developers. Scope: a static page that reads a selected
single-run trace locally, shows recorded verdict/violations, tool and backend
evidence, initial/final state, customer claims, metadata and reproduction command.
No agent execution, server upload, or browser claim of full Python validation.
Reject unsupported/missing display data; label the verdict as recorded evidence.
Test parsing, unsafe text rendering, example runs and invalid imports. Verify a
fresh installation outside the working checkout, document real adoption limits,
commit sequentially, then push. No broader frontend or provider expansion.

Sequential work: `9b732a9` recorded the plan; `2bd8c23` added the static viewer
and 17 JavaScript tests; `21f88ef` linked it from the walkthrough and added its
tests to CI. Browser imports displayed both saved examples and a newly generated
250-cent failure (500 cents committed), preserved imported markup as text with
no image/script elements, cleared evidence, handled keyboard Enter, and rejected
invalid/oversized files without leaving an old verdict visible.

Fresh usability check: normal isolated wheel build, runtime installation in a
new virtual environment outside the checkout, verified site-packages imports,
new 250-cent scenario, flawed failure at 500 cents, corrected pass at 250 cents,
inspection, corrected rerun and JSON/HTML export. No API key/model call needed.
An initial build with isolation explicitly disabled lacked setuptools; normal
pip build isolation worked without changing dependencies.

Final verification: **191 Python tests and 17 JavaScript tests passed**; lint and
format passed. Local evidence and screenshot are in `runs/viewer-usability/`.
[USABILITY.md](USABILITY.md) explains the working narrow sandbox, adapter work
needed for other agents, browser display-versus-validation distinction, missing
live-model/adoption evidence and pending Vercel authentication. No following
feature was started.
## Plain-language website workflow — completed

Scope: explain that OpenAI supplies reasoning while Agent Chaos executes local
simulated payment tools. Add an always-visible six-step flow, the $3/$6 timeout
example, the no-key scripted alternative, and current refund-only scope. Keep
the existing interactive demonstration. Verify the rendered page and existing
website tests, commit small changes sequentially, then push to GitHub.

`726e0eb` recorded the scope; `cbc42c9` added the six-step explanation ahead
of the interactive walkthrough. Browser verification displayed the current
page and confirmed the existing final-step switch still shows flawed 600 cents
and corrected 300 cents. All 17 viewer JavaScript tests passed. A cached page
initially showed the earlier content; loading the revision URL confirmed the
updated content. Screenshot: `runs/website-flow/workflow.jpg`. This is a static
explanation, with no live model call or change to testing behavior. Public
Vercel deployment remains pending authentication; this task updates the source
and local website. No following feature was started.
## Custom refund-agent adapter — in progress

One task: formalize the Python target/tool boundary and provide a standalone
offline adapter example that executes its own refund policy. Support explicitly
supplied custom agents for runs and restored-state reruns. Never silently replace
a custom target with a built-in agent. Record custom identity/version, keep full
trace validation and financial verification, and demonstrate flawed failure plus
corrected rerun. No arbitrary URL input, new workflow, or plugin code imported
from traces. Document integration limits and run meaningful regression tests.
Commit each small improvement and push the final work to GitHub.
