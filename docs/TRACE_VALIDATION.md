# Trace validation implementation plan

Scope: validate version-1 single-run traces before inspection, playback, export,
minimization, or rerun, including direct Python calls to `rerun`. Validation must
finish before creating a run directory, opening SQLite, or constructing an agent.
Work stays sequential, with a commit for each reviewable improvement.

1. Define typed contracts for every required trace section: ledger snapshots,
   faults, tool/backend events, response claims, configuration, metadata, results,
   and trial counts. Reject missing fields, wrong types and non-finite numbers.
2. Check relationships: scenario hash and copied messages; seed and fault schedule;
   tool indices/occurrences and fault references; turn boundaries and violation
   references; unique ledger identifiers and backend effect reconstruction;
   recorded outcomes against deterministic verification.
3. Enforce validation at file and direct rerun entrypoints. Reject duplicate JSON
   keys. Keep valid pass, failure, inconclusive and partial harness-error evidence
   readable. Test malformed input produces a CLI harness error without execution
   or exported output, while existing examples remain compatible.
4. Run regression tests and offline playback/rerun checks, record evidence and
   limitations, and push the completed commits to GitHub.

Financial failures are valid evidence, not malformed traces: duplicate economic
effects and incorrect claims must remain inspectable. Tool argument errors and
unknown tool names are also valid recorded agent behavior when marked as rejected
validation attempts. Model metadata is extensible for raw provider responses and
custom test agents. The validator does not authenticate evidence or run a model;
a scenario hash and internal consistency checks cannot prove external provenance.
