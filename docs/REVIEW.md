# Project review — 2026-10-12

The offline refund MVP works in the checked local environment. This review is
source inspection and regression evidence, not proof that every possible input
or live model interaction works.

## Changes

1. Removed the unused `FaultMiddleware.faults` field. Runtime injection and
   recording use the precomputed seeded schedule; retaining raw faults served no
   purpose. Fault tests passed before committing this cleanup (`7a879e9`).
2. Fixed comparison exit codes (`8e1ff64`). Previously, a harness error on the
   flawed-agent side could be hidden by passing corrected-agent trials. Errors
   on either side now exit 2. An inconclusive flawed trial with a passing
   corrected group exits 3. Intentional flawed-agent failures still allow a
   successful comparison when the corrected group passes. Added seven regression
   cases covering both sides and error precedence, and updated the README.

The flawed agent, optional model adapter, generator, minimizer, saved examples,
and reporting code have active uses and tests; they were retained.

## Verification

- Python 3.12: **69 tests passed**, including real OpenAI SDK calls against an
  offline HTTP mock. Ruff lint and formatting passed. JavaScript syntax passed.
- Development fixtures, five trials each: flawed 30 failures / 40; corrected
  0 / 40. Held-out fixtures, five trials each: flawed 10 / 10; corrected 0 / 10.
  Neither group had harness errors or inconclusive results. These public fixtures
  are scripted regression cases, not an independent live-model benchmark.
- Recorded timeout rerun: 600 cents committed against a 300-cent intent. Corrected
  rerun from the same saved initial state: 300 cents, pass.
- Scripted scenario generation, playback, JSON/HTML export and minimization all
  completed with expected exit codes. Minimization reproduced the failure in all
  three baseline trials and used six target executions in total.
- Equal-budget study, eight executions per group: fixed 6 failures / 8,
  scripted-generated 8 / 8, random 0 / 8; no execution errors or uncertainty.
  Input distributions differ; this small sample supports no general ranking.
- Browser verified the walkthrough's final flawed state (600 cents / failure),
  corrected state (300 cents / pass), and navigation to the corrected evidence
  report. Local links, example JSON, and the Vercel static output directory were
  checked. The previous preview process had stopped; restarted it on port 8765.

Full new evidence is local under `runs/review-2026-10-12/` and ignored by Git.
Previously committed example reports retain their original measurement dates.

Reproduce the main checks from the repository root after the README setup:

```bash
pytest -q
ruff check src tests
ruff format --check src tests
node --check examples/workflow.js
agent-chaos compare scenarios --trials 5 --seed 17 --out runs/review-development
agent-chaos compare scenarios/heldout --trials 5 --seed 17 --out runs/review-heldout
agent-chaos rerun examples/timeout-flawed.json --out runs/review-reproduce
# Expected exit 1 above: the deliberately flawed policy duplicates the refund.
agent-chaos rerun examples/timeout-flawed.json --agent corrected --out runs/review-fixed
agent-chaos study scenarios --agent flawed --budget 8 --seed 17 --out runs/review-study
agent-chaos minimize examples/timeout-flawed.json --trials 3 --budget 12 --out runs/review-minimize
```

## Unverified and pending

No live model calls were made. The user has no model API key. Natural-language
model claims remain unassessed separately from deterministic financial checks.
The website is educational playback and saved reports; it does not run Python
or SQLite in the browser. No mobile-device verification was performed.

Vercel CLI currently reports **logged out**. Static configuration is committed,
but account login and production deployment are pending. No public URL is claimed.
The remote GitHub Actions matrix was not checked during this local review.

## Suggested next work, one task at a time

1. Validate the complete trace contract before playback/rerun: state, tool events,
   claims, references, required metadata, and scenario hash. `read_trace` currently
   validates only the format version and embedded scenario. Use the existing
   Pydantic dependency for typed nested trace models; see the official
   [model validation documentation](https://docs.pydantic.dev/latest/concepts/models/).
   A hash detects accidental changes; it does not authenticate evidence.
2. Expand refund boundary tests: existing partial refunds, exact remaining balance,
   and simultaneous creation attempts through separate SQLite connections.
3. Add a small browser trace viewer that opens a local JSON file and shows its
   recorded fault, tool timeline and ledger. Keep it offline and label imported
   data as recorded evidence, without executing agents from the page.

Finish the already prepared Vercel deployment after account sign-in. Broader
framework support, billing, monitoring and automatic fixes remain outside scope.
