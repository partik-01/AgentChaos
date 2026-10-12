# Who can use Agent Chaos today?

Agent Chaos is a working, narrow refund-agent testing sandbox. A developer can
install it, edit YAML cases, execute real simulated-payment operations, inspect
financial consequences, and rerun a failure against a different agent policy.
The website walkthrough is an educational demonstration. The trace viewer is a
working file-inspection utility. Neither website page executes tests.

It is useful for learning and regression-testing refund retry/idempotency logic,
or developing an agent adapter for this environment. It is not yet a general
testing platform into which any existing agent can be dropped unchanged.

## What another developer needs

Use the README clone/setup instructions with Python 3.11+. No model API key is
needed for scripted runs. Change a scenario's payments, structured user messages,
request amounts, turns, or supported faults, then run:

```bash
agent-chaos run path/to/customer-case.yaml --agent flawed
agent-chaos run path/to/customer-case.yaml --agent corrected
agent-chaos compare scenarios --trials 5 --out runs/comparison
agent-chaos inspect runs/<run-id>/trace.json
agent-chaos rerun runs/<run-id>/trace.json --agent corrected
```

The deliberately flawed run may exit 1. It creates an actual erroneous refund
ledger in SQLite, not a hard-coded result page. The independent financial checks
inspect that state. Fresh runs create JSON, HTML, and SQLite evidence. Playback
and rerun have different meanings, and recorded traces are consistency-validated
before importing them in the CLI.

The wheel contains the Python package; sample YAML and website files are in the
Git repository. Clone the repository for the complete examples and viewer. The
viewer needs only its HTML, CSS and JavaScript files, not Python or Node to use.
Node 18+ is needed only to run its JavaScript test command.

## Inspect your own run in the website

```bash
python3 -m http.server 8765 --bind 127.0.0.1 --directory examples
```

Open `http://127.0.0.1:8765/viewer.html`, select your `trace.json`, and inspect:

- Recorded verdict, violated rules, expected/observed values and event references.
- Payment balances before/after, new refund totals, complete refund snapshots.
- Tool arguments, exact recorded faults, backend effects and agent observations.
- Customer messages/claims, separate conversational assessment, model and prompt
  metadata, versions and reproduction command.

Selected files are read through the browser File API. The page does not upload
them, save them to browser storage, send analytics, or execute imported commands.
Imported content is rendered as text. Example buttons fetch bundled example JSON
from the same static server. You can also open `viewer.html` directly from disk
and choose a JSON file; example buttons need the server. Files over 10 MiB and
amounts/totals outside JavaScript's safe integer range are rejected. Comparison,
suite and study summaries are not supported imports.

**The browser does display checks, not full trace validation.** Its recorded
verdict can be wrong if someone edited the file. Use `agent-chaos inspect` for
the full Python contract, hash, fault/effect reconstruction and verdict checks.
Even full consistency checks cannot prove authenticity or external provenance.

## Testing an actual agent

The CLI initially supports one live provider: `--provider openai --model ...`,
with the user's API key. That adapter has offline tests against the real SDK's
mock HTTP transport, but no live model benchmark was performed. Otherwise-correct
live traces remain inconclusive because conversational prose is unassessed.

The CLI's `--agent` selects the built-in flawed/corrected policies; it does not
load arbitrary agent code. Other agents need a Python adapter passed through
`run_scenario(scenario, agent=adapter, ...)`. It must expose JSON-compatible
`metadata` and `run_turn(turn, tools)`, returning a list of `Claim` objects. Route
the simulated payment calls through `tools.call(name, arguments)` so faults and
evidence are captured. Declare conversational text as `unassessed` unless it
uses the exact supported deterministic templates. This is a small Python
extension point, not broad framework interoperability or a stable plugin ABI.

There is no real payment integration, hosted execution backend, production
monitoring, or automatic fix generation. Connecting a production agent's existing
tools requires deliberate adapter work and replacing payment operations with
the simulation. Recorded customer interaction is a structured scenario, not an
unrestricted natural-language support conversation. No external user adoption
or production-readiness claim has been established.

## Evidence for this assessment — 2026-10-12

Built a wheel using pip's normal isolated build, installed it and its runtime
dependencies in a new virtual environment outside the repository, and verified
imports came from that environment's `site-packages`. Created a new YAML case
requesting **250 cents**, rather than using the displayed 300-cent examples.

- Flawed policy: 500 cents committed, agent failure.
- Corrected policy: 250 cents committed, pass.
- Full inspection, corrected rerun, JSON and HTML export succeeded outside the
  checkout. No model calls were made.
- The browser imported that new failed run and showed its 500-cent ledger.
- Browser checks also covered both bundled examples, file selection, clearing,
  keyboard Enter, invalid JSON and oversize rejection. Imported `<img ...>` text
  remained literal JSON text; no image or script element was created.
- 191 Python tests and 17 JavaScript tests passed; Python lint/format passed.

The first build attempt disabled build isolation and failed because setuptools
was absent from the existing development environment. The normal isolated build
succeeded without changing project dependencies. The fresh install used that
wheel plus the new scenario file; it did not prove a package-only installation
includes example fixtures. Testing was local macOS/Python 3.12 and the in-app
desktop browser. No mobile-device, Windows, live model or remote CI result is
claimed. Vercel production deployment still awaits account authentication.
Local evidence is in `runs/viewer-usability/` and is ignored by Git.

The honest conclusion: usable now for this simulated refund workflow and local
evidence inspection; early-stage and adapter-dependent for other people's real
agents. The attractive walkthrough alone would be a demonstration. The CLI's
new executions, authoritative ledger, verifier, and rerun evidence are the useful
testing system behind it.
