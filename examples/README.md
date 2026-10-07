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
