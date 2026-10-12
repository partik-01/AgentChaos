# Getting started

Goal: install Agent Chaos, produce one passing run, reproduce a duplicate refund,
and verify a corrected rerun. This uses simulated payments and no API key.

## Requirements

- Python 3.11 or newer, with `venv` and pip.
- Git, to get the sample scenarios, website and custom example.
- A terminal and a browser for opening static reports.

SQLite is included with Python; no database server is needed. Node 18+ is only
needed to run the website tests. Runtime dependencies are Pydantic and PyYAML.
Python 3.11–3.13 are configured in CI; local checks were performed on macOS with
Python 3.12. These instructions do not claim Windows was tested.

## Install on macOS or Linux

```bash
git clone https://github.com/partik-01/ChaoticAgent.git
cd ChaoticAgent
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
agent-chaos --help
```

If you already cloned the repository, start with `cd ChaoticAgent`. Editable
installation makes the checked-out package available in this environment; you
do not need to reinstall for ordinary Python source edits.

## Install on Windows (PowerShell)

```powershell
git clone https://github.com/partik-01/ChaoticAgent.git
cd ChaoticAgent
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
agent-chaos --help
```

Check that `py -3 --version` selects Python 3.11+. If activation is blocked by
your existing policy, you can use the environment directly without changing it:

```powershell
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m agent_chaos.cli run scenarios/01_normal.yaml
```

## Produce your first result

```bash
agent-chaos run scenarios/01_normal.yaml --out runs/first-run
```

Expected output has `status: pass`, an empty `violations` list, a `run_id`, and a
reproduction command. Each execution writes:

```text
runs/first-run/RUN_ID/
  trace.json        # Complete messages, tools, faults, state and verdict
  report.html       # Readable evidence; open directly in a browser
  payments.sqlite   # Authoritative simulated database for this execution
```

Replace `RUN_ID` with the identifier printed by the command. IDs and latency
change across executions. For this normal scenario, the expected refund is
300 USD cents. Bob's unrelated payment must stay unchanged.

## See a real simulated failure and correction

The checked-in trace supplies a known initial state, scenario and flawed policy:

```bash
agent-chaos inspect examples/timeout-flawed.json
agent-chaos rerun examples/timeout-flawed.json --out runs/reproduced
# Expected exit 1: two refunds totaling 600 cents, expected 300.
agent-chaos rerun examples/timeout-flawed.json --agent corrected --out runs/corrected
# Expected exit 0: one refund totaling 300 cents.
```

Inspection validates and reads recorded evidence. Rerun executes against a fresh
database restored from that evidence. The deliberate failure is an expected test
result. Run the commands separately if your shell/CI stops on nonzero exits.

For newly generated evidence, inspect the `trace.json` path under the printed
run ID. Paths containing spaces should be quoted. The CLI's reproduction command
already quotes the generated path.

## Optional live OpenAI target

The built-in live adapter supports OpenAI. It uses the same simulated tools;
OpenAI does not process a payment. Install its extra:

```bash
python -m pip install -e '.[openai]'
```

Set your own key in the process environment, then replace `YOUR_MODEL_ID` with a
model available to your account that supports tools and structured outputs:

```bash
export OPENAI_API_KEY=YOUR_KEY
agent-chaos run scenarios/03_after_timeout.yaml --provider openai --model YOUR_MODEL_ID
```

In PowerShell, use `$env:OPENAI_API_KEY = "YOUR_KEY"` instead of `export`.
The package does not automatically load a `.env` file. Keep keys outside scenario
files, adapter metadata, shared terminal logs and Git. These calls can incur
provider charges; the no-key scripted path remains available.

The adapter has mocked integration tests; no live-model benchmark is claimed.
Financial and structured-claim checks are deterministic, but model prose is
unassessed. An otherwise correct live run is therefore **inconclusive**, not a
pass. Seeded faults do not make model output deterministic.

## Continue

- [Use your own agent factory](CUSTOM_AGENTS.md).
- [Write a scenario](SCENARIOS.md) or [add tool policies](TOOL_RULES.md).
- [Find CLI options and report paths](CLI.md).
- [Troubleshoot a result or setup problem](TROUBLESHOOTING.md).
- [Install development tools and contribute](../CONTRIBUTING.md).

[Documentation index](README.md).
