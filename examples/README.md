# Measured offline evidence

These files were produced by actual scripted executions on 2026-10-07. No model
API key or live model call was used. HTML reports open directly in a browser.

| Evidence | JSON | HTML |
| --- | --- | --- |
| Normal baseline, flawed script passes | [trace](normal-flawed.json) | [report](normal-flawed.html) |
| Ambiguous timeout exposes duplicate refund | [trace](timeout-flawed.json) | [report](timeout-flawed.html) |
| Same saved initial state, corrected agent rerun | [trace](timeout-corrected.json) | [report](timeout-corrected.html) |
| Per-scenario repeated-trial counts | [summary](benchmark-summary.json) | [report](benchmark-summary.html) |

The expected refund is 300 cents. The flawed agent commits 600 cents; the corrected
rerun commits 300. The flawed replay was also reexecuted and produced the same
final ledger and fault schedule. Latency and run IDs vary. Reproduction commands
in these exported traces were normalized to portable paths relative to the
repository root; financial evidence and recorded versions were not changed.

From the repository root, after installing Agent Chaos:

```bash
agent-chaos playback examples/timeout-flawed.json
agent-chaos rerun examples/timeout-flawed.json  # Exits 1: duplicate reproduced
agent-chaos rerun examples/timeout-flawed.json --agent corrected  # Exits 0
agent-chaos export examples/timeout-flawed.json --output runs/export.json
agent-chaos compare scenarios --trials 3 --seed 17 --out runs/recheck-fixed
agent-chaos compare scenarios/heldout --trials 5 --seed 17 --out runs/recheck-heldout
agent-chaos study scenarios --agent flawed --budget 24 --seed 17 --out runs/recheck-study
```

Development results: flawed **18 failures / 24 trials**, corrected **0 / 24**.
Reserved-case results: flawed **10 / 10**, corrected **0 / 10**.
The discovery demonstration measured fixed **18 / 24**, scripted-generated
**24 / 24**, random **3 / 24**, without harness errors or inconclusive runs.
Generation is a scripted proposal policy in this measurement. Strategies differ
in their input distributions; these counts are not a general ranking. Equal
target-execution budgets do not imply equal model cost or token use.

Full aggregate traces are created locally by the commands above. Only selected
portable traces and aggregate counts are checked into Git. Source commits and
dependency versions are recorded in the summary. These are public, small scripted
regression demonstrations, not independent holdout or live-model benchmarks.

## API-free follow-up validation

A later requested offline run completed **82 target executions without any model
API call**: five trials of each development scenario for both policies (80),
followed by failure reproduction and corrected rerun (2). Flawed: 30 failures /
40 trials. Corrected: 0 / 40. No harness errors or inconclusive runs occurred.
View the [JSON evidence](no-api-validation.json) or [HTML report](no-api-validation.html).
These remain deterministic scripted demonstrations, not live model benchmarks.

## Workflow explainer website

`custom_agent.py` is an independent Python target and runner for the refund
sandbox. Follow [the custom-agent guide](../docs/CUSTOM_AGENTS.md) to reproduce
its timeout failure and rerun the corrected policy. It needs no API key.

Serve this folder with `python3 -m http.server 8765 --bind 127.0.0.1 --directory examples`
from the repository root, then open `http://127.0.0.1:8765/`.
`index.html` and `workflow.js` provide a six-step explanation, a flawed/corrected
policy switch, a project component map, links to these reports, and copyable CLI
commands. The walkthrough explains recorded evidence; it does not execute tests.
An always-visible six-step flow explains OpenAI reasoning, local simulated tool
execution, the timeout, agent recovery and independent verification. It also
states the refund-only scope, no-real-money boundary and scripted no-key option.

`viewer.html` opens your own single-run `trace.json` using a local file picker.
It displays rules, before/after balances, tools, faults, claims and version
metadata. Selected files are not uploaded or saved to browser storage. The
browser checks display structure only; use the CLI for full trace consistency
validation. Neither the viewer nor the walkthrough runs agents. See
[the usability assessment](../docs/USABILITY.md) for adoption limits and measured
fresh-install evidence. Node tests: `node --test tests/viewer.test.cjs`.
