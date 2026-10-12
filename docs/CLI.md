# CLI reference

Commands assume the repository root and an active environment. Use
`agent-chaos --help` or `agent-chaos run --help` for flags. The Python alternative
is `python -m agent_chaos.cli`.

## Common tasks

| Task | Command |
| --- | --- |
| Normal test | `agent-chaos run scenarios/01_normal.yaml` |
| Expose timeout failure | `agent-chaos run scenarios/03_after_timeout.yaml --agent flawed` |
| Repeat eight core cases | `agent-chaos suite scenarios --trials 5 --out runs/suite` |
| Compare built-in policies | `agent-chaos compare scenarios --trials 3 --seed 17 --out runs/comparison` |
| Public reserved cases | `agent-chaos suite scenarios/heldout --trials 5 --out runs/reserved` |
| Configured tool policies | `agent-chaos suite scenarios/tool_rules --trials 5 --out runs/policies` |
| Read saved evidence | `agent-chaos inspect examples/timeout-flawed.json` |
| Offline playback (same as inspect) | `agent-chaos playback examples/timeout-flawed.json` |
| Reproduce failure | `agent-chaos rerun examples/timeout-flawed.json` |
| Check correction | `agent-chaos rerun examples/timeout-flawed.json --agent corrected` |
| Export JSON and HTML | `agent-chaos export examples/timeout-flawed.json --output runs/export/failure.json` |

Inspect/playback validate recorded evidence without executing tools or an agent.
They return `0` for valid evidence even if the recorded result was a failure.
Rerun executes again and returns the **new** outcome's exit code. Trace inputs
may be a file or run directory. Inspection/export accept single-run traces,
not suite/comparison bundles.

## Execution options

| Flag | Meaning |
| --- | --- |
| `--agent corrected` / `--agent flawed` | Built-in policy, or prompt variant for the OpenAI target |
| `--provider scripted` | Default; no model API calls |
| `--provider openai --model YOUR_MODEL_ID` | Optional live integration; needs extra/key |
| `--agent-factory module:callable` | Explicit custom target for run, suite and rerun |
| `--out DIRECTORY` | Evidence root, default `runs` |
| `--seed INTEGER` | Override fault seed for run, suite, compare and study |
| `--trials INTEGER` | Trials per scenario for suite/compare, default 3 |

Suite seeds are the scenario/override seed plus trial index, starting at zero.
Comparisons use matching seeds for both built-in versions. Discovery selects
immediate `*.yaml` files, not nested folders. Each trial has fresh state.

Rerun defaults to the recorded provider/version/model and restores the initial
database and scenario seed. It has no `--seed` override. Custom targets require
an explicit factory again. Replace `RUN_ID` below with the printed identifier:

```bash
agent-chaos rerun runs/RUN_ID/trace.json --agent-factory examples.custom_agent:make_corrected_agent
agent-chaos rerun runs/RUN_ID/trace.json --provider scripted --agent corrected
```

With a factory, leave built-in agent/provider/model options at defaults;
metadata supplies identity/model. Compare custom versions with two suites using
the same YAML, seeds and trial count. Generic `compare` does not load factories.
See [custom integration](CUSTOM_AGENTS.md).

## Output paths

| Operation | Files under `--out` |
| --- | --- |
| Run/rerun | `RUN_ID/trace.json`, `RUN_ID/report.html`, `RUN_ID/payments.sqlite` |
| Suite | Run directories plus `suite.json`, `suite.html` |
| Compare | Run directories plus `comparison.json`, `comparison.html` |
| Export to `runs/failure.json` | `runs/failure.json`, `runs/failure.html` |

Suite JSON has `summary.counts` and `summary.by_scenario`, plus individual
`runs`. Comparison has `flawed`/`corrected` bundles and a summary. Reports show
expected/observed values, faults and tool/backend evidence. The recorded
reproduction command needs an explicit factory added for custom targets.

## Exit codes and CI

| Code | Meaning |
| --- | --- |
| `0` | Successful run/read/export, or completed comparison/study as below |
| `1` | Agent financial, claim, output/budget or configured tool-policy failure |
| `2` | Harness/configuration/provider/I/O/trace error; never a pass |
| `3` | Inconclusive; never a pass |

For corrected/custom regression suites, let a nonzero exit fail CI:

```bash
agent-chaos suite scenarios --agent corrected --trials 3 --seed 17 --out runs/ci
```

Upload `runs/ci` as an artifact. Intentional flawed examples return `1`; run
them separately when your shell stops on failures. Comparison ignores intended
flawed failures, but errors on either side return `2`, corrected failures `1`,
and otherwise-hidden uncertainty `3`. Study returns `0` for completed discovery
even when it found agent failures; errors/uncertainty still surface. These
convenience exits do not mean every recorded target passed.

## Optional experiments

```bash
agent-chaos generate scenarios/01_normal.yaml --seed 17 --output runs/generated.yaml
agent-chaos minimize examples/timeout-flawed.json --rule no_duplicate_economic_effect --trials 3 --budget 60 --out runs/minimal
agent-chaos study scenarios --agent flawed --budget 24 --seed 17 --out runs/study
```

Minimize requires at least two trials and may return `3` if the original failure
does not reproduce. These commands use built-in targets, not custom factories.
Read [experiment semantics and budgets](EXPERIMENTS.md) before comparing results.

[Documentation index](README.md) · [Troubleshooting](TROUBLESHOOTING.md).
