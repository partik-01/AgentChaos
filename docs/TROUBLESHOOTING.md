# Troubleshooting

An expected agent failure is not a broken harness. Start with the exit code and
stderr; [CLI result meanings](CLI.md) explain `0`, `1`, `2` and `3`.

| Symptom | Check / action |
| --- | --- |
| `agent-chaos` not found | Activate the install environment; run `python -m pip install -e .`, or try `python -m agent_chaos.cli --help`. |
| Unsupported Python | Check `python --version`; use Python 3.11+. |
| Scenario/example not found | Run from the repository root. Clone the repo for assets; they are not included in the wheel. |
| No YAML found | Supply a YAML file or a directory with immediate YAML files. Discovery is not recursive. |
| Exit `1` from flawed example | Expected. Inspect the violated rule, expected/observed outcome and ledger evidence. |
| Exit `2` | Read stderr for invalid configuration/trace, provider/import/constructor or I/O errors. |
| Exit `3` | Completion is unverified or prose is unassessed. Financial evidence remains available; do not count it as a pass. |
| Refund exists but agent sees timeout/not-found | This may be an intentional fault. Reconcile by stable key; observations and backend state differ. |
| Lookup policy fails despite a lookup | Check matching payment/customer arguments and whether the lookup preceded creation. |
| Factory import fails | Use `module:callable` in the current directory or installed environment. Factory must take no arguments. |
| Factory target rejected | Check custom kind, nonempty version, JSON metadata, conversation assessment and callable `run_turn`. |
| Custom rerun refuses | Explicitly supply `--agent-factory` again; trace metadata is never auto-imported. |
| Custom agent hangs | CLI factories default to 60 seconds / 100 calls. Set `--timeout-seconds` / `--max-tool-calls`. Direct Python runs need explicit limits or a factory; see [execution limits](EXECUTION_LIMITS.md). |
| Spawn/pickle error | Prefer an importable zero-argument factory. Use a main guard in Python entrypoints; local classes/lambdas and parent monkeypatches do not transfer reliably. |
| Initialization deadline | Inspect `execution_stop.phase`; startup/import/construction counts against the deadline. Increase it to test agent behavior rather than startup. |
| OpenAI unavailable | Install `.[openai]`, set `OPENAI_API_KEY` in the environment and pass your available `--model`. `.env` is not automatically loaded. |
| Viewer rejects JSON | Choose a single-run trace, not a suite summary; maximum 10 MiB. Use CLI inspect for full validation. |
| Suite stopped early | Open `--out/suite.html` or `suite.json`; check `progress.state` and remaining trials. Factory failures are recorded and later trials continue. See [partial suites](PARTIAL_SUITES.md). |
| Report missing | Look under `--out/RUN_ID/report.html`. Output-write failures return errors, never a pass. |
| Website port occupied | Use another port, e.g. `python -m http.server 8766 --bind 127.0.0.1 --directory examples`. |

## Invalid traces

Inspection checks structure, hash, faults, backend effects, observations, response
timing and verdict. Editing financial evidence or rules can invalidate a trace.
Rerun validates before execution; it does not repair edited evidence. Return to
the original or execute the original scenario again. Internal consistency is
not proof of authenticity.

## Otherwise-correct live runs are inconclusive

Financial and structured-claim checks still run, but arbitrary prose is
unassessed. No model judge is included. `deterministic_templates` applies only
to the exact sentences from `agent_chaos.agents.claim`, not arbitrary text.
See [custom-agent requirements](CUSTOM_AGENTS.md).

## Reporting problems

Include reproduction command, package/Python version, exit code, expected and
observed result, and a minimal simulated YAML case. State whether the target is
scripted, custom or live. Sanitized event indices or JSON/HTML evidence help.
Review customer text, metadata and provider output before sharing; omit keys and
real customer/payment details. A valid trace can still contain private text.

Use [GitHub issues](https://github.com/partik-01/ChaoticAgent/issues) and
[contribution guidance](../CONTRIBUTING.md). No response-time guarantee is claimed.

[Documentation index](README.md).
