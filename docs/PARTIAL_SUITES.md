# Access partial suite results

`agent-chaos suite` saves `suite.json` and `suite.html` in `--out` before and
after each trial. You can open or refresh the HTML report while the suite runs.
Each recorded trial links to its own HTML report and trace JSON. The CLI prints
both summary paths with the final or interrupted result.

```bash
agent-chaos suite scenarios --agent-factory examples.custom_agent:make_corrected_agent --trials 3 --out runs/my-suite
```

Open `runs/my-suite/suite.html` in a browser. The JSON file contains the same
recorded trials, financial verdicts and progress. For full validation of one
trial, take its run ID from the report and execute:

```bash
agent-chaos inspect runs/my-suite/RUN_ID/trace.json
```

`inspect` accepts single-run traces, not suite summaries. The browser report
presents saved evidence; use the CLI to validate a selected trace.

## What happens when a factory fails?

Import errors, rejected metadata, constructor failures and worker crashes are
recorded as individual harness-error trials. The suite continues to later
trials, including fresh factory instances. It saves the resulting summaries
and exits 2 if any trial had a harness error. Successful trials and failed trials
remain accessible in the same report.

A failure outside the target boundary, such as an unexpected runner exception,
stops execution. The summary retains previously recorded trials, marks the suite
`harness_error`, records the exception and active trial, and exits 2. It does not
invent a complete trace for a trial that failed to record.

## Understand progress before using the totals

The bundle retains `summary` and `runs`, and adds `progress`:

| Field | Meaning |
| --- | --- |
| `state` | `running`, `completed`, `interrupted`, or `harness_error` |
| `planned_trials` | Number of scenarios multiplied by trials per scenario |
| `completed_trials` | Trials with a returned trace, including recorded harness errors |
| `remaining_trials` | Planned minus completed, including any unfinished active trial |
| `active_trial` | Scenario name, one-based trial number within that scenario, and seed; null between trials or after completion |
| `error` | Suite interruption/exception message, or null |
| `updated_at` | UTC timestamp of the saved checkpoint |

`summary.total_trials` and all result counts cover **recorded trials only**.
For example, one pass followed by an unrecorded runner error yields one pass
in the trial counts, a suite state of `harness_error`, and exit 2. Never interpret
an incomplete subset of passing trials as a passing suite.

`completed` means every planned trial returned a trace; it does not mean the
trials passed. Check the normal result counts and exit code too. A handled Ctrl+C
during a trial saves `interrupted` and exits **130**. The report marks every
non-completed state as incomplete.

## Try an interrupted suite without a model key

```bash
agent-chaos suite scenarios/01_normal.yaml --agent-factory examples.limited_agents:make_refund_then_hang --timeout-seconds 5 --trials 3 --out runs/partial-demo
```

After the first trial finishes (about five seconds), open
`runs/partial-demo/suite.html`. Press Ctrl+C in the running terminal during a
later trial. The report retains the first trial's refund, deadline failure and
trace link, plus the remaining count. This is a deliberately broken script.

## Storage and interruption boundaries

JSON and HTML are each replaced atomically. They are separate files, not one
transaction: during a refresh or write error, HTML can be one checkpoint behind
JSON. Prefer the JSON timestamp and progress when comparing them. If storage
fails, the CLI returns an error and the most recent successfully saved files
remain available; it cannot promise another checkpoint on unwritable storage.

A hard kill, machine shutdown, or interruption during checkpoint writing can
leave the last snapshot marked `running`. That is incomplete evidence, not proof
that a process is still alive. Files from an in-flight trial may exist without a
finished trace and are not silently counted. Completed trace directories remain
available independently of the summary.

All scenario files validate before execution. Invalid configuration does not
replace a prior suite report. Starting a valid new suite in the same `--out`
replaces the summary from its first checkpoint; use separate output directories
to keep suite histories. Concurrent suites must use different directories.
This feature does not resume interrupted suites automatically. Checkpointing
currently applies to the standard `suite` command, not `compare`, `study` or the
older standalone example runner. Rewriting full bundles favors small MVP suites;
very large suites need a more scalable recording format.

[CLI reference](CLI.md) · [Documentation index](README.md).
