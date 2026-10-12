# Agent Chaos documentation

Start with a local scripted run. Then connect your own refund agent, write a
scenario, and inspect its evidence. No model API key is needed for that path.

| You want to… | Read |
| --- | --- |
| Install and get a first result | [Getting started](GETTING_STARTED.md) |
| Find command options, exit codes and output files | [CLI reference](CLI.md) |
| Create a refund/fault test case | [Scenario authoring](SCENARIOS.md) |
| Connect an existing Python agent | [Custom agents](CUSTOM_AGENTS.md) |
| Require tool order, bounded calls or stable retry arguments | [Tool rules](TOOL_RULES.md) |
| Understand payment/idempotency/fault semantics | [API contract](API.md) |
| Understand offline evidence validation | [Trace validation](TRACE_VALIDATION.md) |
| Fix a setup, integration or result problem | [Troubleshooting](TROUBLESHOOTING.md) |
| Run optional scenario discovery/minimization | [Experiments](EXPERIMENTS.md) |
| See measured results and saved traces | [Example evidence](../examples/README.md) |
| Understand what is and is not proven | [Usability and limitations](USABILITY.md) |
| Develop or contribute | [Contributing](../CONTRIBUTING.md) |

All commands assume the repository root and an active Python environment unless
stated otherwise. Sample YAML, custom example and website files are in the Git
repository; the wheel contains the Python package, not those assets.

## Code map

| File under `src/agent_chaos/` | Responsibility |
| --- | --- |
| `schema.py` | Scenario, tool argument, claim and tool-rule contracts |
| `payments.py` | Transactional authoritative SQLite ledger |
| `faults.py` | Seeded faults and separate backend/observed events |
| `agents.py`, `openai_agent.py` | Scripted targets and optional OpenAI target |
| `adapters.py` | Python target/tool boundary and explicit factory loading |
| `tool_rules.py`, `verifier.py` | Independent policy, financial and claim checks |
| `runner.py`, `traces.py` | Isolated executions, restoration and trace validation |
| `cli.py`, `reports.py` | Commands, trial summaries and JSON/static HTML output |
| `generation.py`, `experiments.py` | Optional discovery and minimization |

## Maintainer records

[Progress](PROGRESS.md), [original implementation plan](PLAN.md) and
[earlier review](REVIEW.md) retain the history of implementation and validation.
Their dated test counts describe those checkpoints; they are not the getting
started guide or a claim that remote CI passed.

[Back to the project README](../README.md).
