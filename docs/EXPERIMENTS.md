# Optional post-MVP experiments

These commands are optional and run sequentially. They propose tests and shrink
failures; they never fix agents, modify source code, or monitor production.

## Propose scenarios

```bash
agent-chaos generate scenarios/01_normal.yaml --seed 17 --output runs/generated.yaml
agent-chaos run runs/generated.yaml --agent flawed
# Optional real generation agent (requires the OpenAI extra and API key):
agent-chaos generate scenarios/01_normal.yaml --provider openai --model YOUR_MODEL_ID \
  --seed 17 --output runs/model-proposal.yaml
```

The default is an explicitly labeled deterministic **scripted proposal policy**,
not a model. It proposes ambiguous creation faults and occasional repeated
requests. The OpenAI generation agent uses a recorded prompt and JSON output to
propose turns and faults; Pydantic validates every proposal before execution.
The fixture is copied from the base scenario, never from the generator output.
Limits: 8 turns, 16 messages, 12 faults; unique tool/occurrence slots and declared
execution-turn rules. Invalid model proposals produce a harness error; there is
no unrecorded repair loop or silent filtering of successful trials.

Generation metadata is saved beside the YAML with a `.generation.json` suffix.
For models it records prompt, input, raw response and reported usage. Costs are
null unless available, and seeds label proposals rather than control model output.
A proposed fault may be unreachable under a particular target's behavior; the
fault schedule and observed events make that visible.

## Minimize failures

```bash
agent-chaos minimize runs/<failed-run-id>/trace.json \
  --rule no_duplicate_economic_effect --trials 3 --budget 60 --out runs/minimal
agent-chaos run runs/minimal/minimized.yaml --agent flawed
```

The minimizer first reexecutes the original failure. Each candidate removes one
fault, turn, or message. It restores the recorded initial state and retains a
candidate only when the selected deterministic rule fails in **every** trial,
using seed offsets from the original seed. Harness errors, passes and inconclusive
runs do not preserve a failure. It records all attempts and results, not just the
accepted reductions. Budgets count every target execution, including baseline
trials; no partial candidate batch is started. At least two trials are required.

Output: `minimized.yaml`, `minimization.json`, `minimization.html`, and each
individual run. If the original failure does not reproduce in all baseline trials,
the CLI exits 3 and marks `baseline_reproduced: false`. The resulting YAML is not
claimed to preserve the failure in that case. Reduction is greedy and preserves
a violated rule, not a globally minimal causal explanation. Removing an
interaction changes authorization context; inspect the retained evidence. Small
trial batches cannot establish a live model's true failure probability.

## Compare discovery strategies

```bash
agent-chaos study scenarios --agent flawed --budget 24 --seed 17 --out runs/discovery
# Live targets and generation are separately selectable:
agent-chaos study scenarios --provider openai --model TARGET_MODEL_ID \
  --generator-provider openai --generator-model GENERATOR_MODEL_ID \
  --agent corrected --budget 24 --seed 17 --out runs/live-discovery
```

Every strategy receives exactly `--budget` **target executions**. Fixed cases
cycle in filename order. Generated proposals and random faults use the fault-free
one-request baseline fixture found in that set. Random injection chooses a
creation fault, invocation 1–3, probability 0.5 or 1, and 1–6 hidden reads from a
seeded RNG. Generated inputs are validated and saved, so discovery is reproducible
by rerunning those files. All strategies use the same payment environment.

Reports include per-scenario failure counts, harness errors, inconclusive counts,
full traces, generation metadata and generation model-call count. Additional
generation API calls are explicitly outside the equal target-execution budget.
This is **not equal dollar cost, token use, number of tool calls, or scenario
complexity**. Do not interpret this small convenience experiment as a fair general
ranking of generation methods. Use trace usage data to design a separate token-
or dollar-budget experiment if needed. Study exits 0 for completed discovery even
when targets fail, 2 for harness errors, and 3 for inconclusive target runs.
