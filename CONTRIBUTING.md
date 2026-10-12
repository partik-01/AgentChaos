# Contributing to Agent Chaos

Small, focused contributions are welcome: clearer docs, reproducible scenarios,
verifier/service tests and improvements within the simulated refund workflow.
For a new workflow/provider or major integration, open an issue explaining the
use case and proposed contract before investing in a broad implementation.

## Development setup

Fork and clone the repository, then create an environment using Python 3.11+.
See [platform-specific setup](docs/GETTING_STARTED.md) if needed.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev,openai]'
git switch -c codex/my-improvement
```

The OpenAI extra enables SDK/mock tests; **no API key is needed** for the checks
below. Node 18+ is needed for the viewer tests, not for Python execution. CI is
configured for Python 3.11, 3.12 and 3.13 on Linux; configured coverage is not a
claim that a particular remote run passed.

## Make and verify one change

Keep money as integer cents. Preserve backend/observation separation, stable
idempotency semantics and independent financial verification. Every call that
the harness evaluates must pass through its tool boundary. Broken execution and
unassessed/uncertain results must never become passes.

For behavior changes, add a meaningful regression test and a small simulated
case when useful. For documentation, verify commands, links and their expected
exit codes rather than adding tests that simply assert prose is present.

```bash
python -m pytest -q
ruff check .
ruff format --check .
node --test tests/viewer.test.cjs
agent-chaos compare scenarios --trials 3 --seed 17 --out runs/contribution-fixed
agent-chaos compare scenarios/heldout --trials 5 --seed 17 --out runs/contribution-reserved
```

These comparisons intentionally contain flawed-agent failures. Do not hide
harness errors or inconclusive runs. Run focused tests while editing, then the
checks above for a completed behavior change. Inspect a report if your change
affects evidence or rendering. Use `ruff format` on changed files when needed.

## Documentation and evidence

- Update the relevant [guide](docs/README.md), not only the main README.
- Document API/rule semantics before changing them. Explain trace compatibility.
- Keep historical counts dated and attached to their actual commands/policies.
  New scripts or input distributions are separate results.
- Do not claim live-model reliability, external adoption or deployment without
  evidence. Scripted trials are regression demonstrations.
- Keep keys, real customer text, payment details and large run directories out
  of Git. Review anything you attach to an issue or PR.
- Do not edit saved financial evidence to make a test pass. Preserve the failing
  original and create a new run for the correction.

## Submit a pull request

Use small commits with descriptive messages. Explain the problem, resulting
behavior, validation performed and material limits. Include reproduction steps
for a bug fix and indicate whether tests use scripted logic, mocks or live calls.
Mention skipped checks honestly. Follow the repository's MIT license for your
contribution. Maintainer response times and acceptance are not guaranteed.

For a bug, use the [issue template](https://github.com/partik-01/ChaoticAgent/issues/new/choose)
and [troubleshooting guide](docs/TROUBLESHOOTING.md). For a private-data issue,
sanitize a simulated reproduction before posting publicly; no private reporting
channel is currently documented.

[Project README](README.md) · [Documentation index](docs/README.md) · [License](LICENSE).
