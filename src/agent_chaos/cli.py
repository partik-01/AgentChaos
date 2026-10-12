"""CLI for one refund workflow. Playback never calls tools or a model."""

import argparse
import json
import sys
from pathlib import Path

from .adapters import create_custom_agent, load_agent_factory
from .reports import write_html
from .runner import read_trace, rerun, run_scenario, summarize, write_json
from .schema import load_scenario


def positive(value):
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return number


def execution_options(parser, *, custom=False):
    parser.add_argument("--agent", choices=["flawed", "corrected"], default="corrected")
    parser.add_argument("--provider", choices=["scripted", "openai"], default="scripted")
    parser.add_argument("--model", help="Required for live OpenAI runs")
    parser.add_argument("--out", default="runs", help="Evidence directory")
    parser.add_argument("--seed", type=int, help="Override the scenario fault seed")
    if custom:
        parser.add_argument(
            "--agent-factory", help="Explicit local module:callable returning a custom target"
        )


def custom_options(factory):
    target = create_custom_agent(factory)
    return {
        "agent": target,
        "agent_version": target.metadata["version"],
        "provider": "custom",
        "model": target.metadata.get("model"),
    }


def suite_paths(path):
    path = Path(path)
    paths = sorted(path.glob("*.yaml")) if path.is_dir() else [path]
    if not paths:
        raise ValueError("no YAML scenarios found (holdouts require their explicit directory)")
    return paths


def execute_suite(args, agent):
    # Validate all fixtures before any model spending.
    scenarios = [load_scenario(p) for p in suite_paths(args.path)]
    factory = (
        load_agent_factory(args.agent_factory) if getattr(args, "agent_factory", None) else None
    )
    traces = []
    for scenario in scenarios:
        for trial in range(args.trials):
            seed = (args.seed if args.seed is not None else scenario.seed) + trial
            options = (
                custom_options(factory)
                if factory
                else {"agent_version": agent, "provider": args.provider, "model": args.model}
            )
            trace = run_scenario(
                scenario.model_copy(update={"seed": seed}), out=args.out, **options
            )
            traces.append(trace)
    return {"summary": summarize(traces), "runs": traces}


def exit_code(summary):
    counts = summary["counts"]
    return (
        2
        if counts["harness_error"]
        else 1
        if counts["agent_failure"]
        else 3
        if counts["inconclusive"]
        else 0
    )


def save_bundle(path, data):
    write_json(path, data)
    write_html(Path(path).with_suffix(".html"), data)


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="agent-chaos", description="Test refund agents with simulated payments."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    one = commands.add_parser("run", help="Execute one YAML scenario")
    one.add_argument("scenario")
    execution_options(one, custom=True)
    suite = commands.add_parser("suite", help="Run multiple isolated trials per scenario")
    suite.add_argument("path")
    suite.add_argument("--trials", type=positive, default=3)
    execution_options(suite, custom=True)
    inspect = commands.add_parser(
        "inspect", aliases=["playback"], help="Offline read-only trace playback"
    )
    inspect.add_argument("trace")
    repeat = commands.add_parser("rerun", help="Restore recorded initial state and execute again")
    repeat.add_argument("trace")
    repeat.add_argument("--agent", choices=["flawed", "corrected"])
    repeat.add_argument("--provider", choices=["scripted", "openai"])
    repeat.add_argument("--model")
    repeat.add_argument("--out", default="runs")
    repeat.add_argument(
        "--agent-factory", help="Explicit local module:callable for a fresh custom target"
    )
    compare = commands.add_parser(
        "compare", help="Matched fault-seed trials for both agent versions"
    )
    compare.add_argument("path")
    compare.add_argument("--trials", type=positive, default=3)
    execution_options(compare)
    export = commands.add_parser("export", help="Export recorded JSON and static HTML")
    export.add_argument("trace")
    export.add_argument("--output", default="export.json")
    generate = commands.add_parser("generate", help="Propose and validate a bounded scenario")
    generate.add_argument("base")
    generate.add_argument("--provider", choices=["scripted", "openai"], default="scripted")
    generate.add_argument("--model")
    generate.add_argument("--seed", type=int, default=17)
    generate.add_argument("--output", default="runs/generated.yaml")
    minimum = commands.add_parser(
        "minimize", help="Greedily remove events while repeating a failure rule"
    )
    minimum.add_argument("trace")
    minimum.add_argument("--trials", type=positive, default=3)
    minimum.add_argument("--budget", type=positive, default=60)
    minimum.add_argument("--rule")
    minimum.add_argument("--out", default="runs/minimize")
    research = commands.add_parser(
        "study", help="Compare fixed/generated/random with equal target-run budgets"
    )
    research.add_argument("path")
    research.add_argument("--budget", type=positive, default=24)
    research.add_argument(
        "--generator-provider", choices=["scripted", "openai"], default="scripted"
    )
    research.add_argument("--generator-model")
    execution_options(research)
    args = parser.parse_args(argv)
    try:
        if getattr(args, "agent_factory", None) and (
            args.provider not in (None, "scripted")
            or args.model is not None
            or args.agent not in (None, "corrected")
        ):
            raise ValueError(
                "--agent-factory supplies identity/model; omit --provider, --model and --agent"
            )
        if args.command == "generate":
            from .generation import generate_scenario, write_scenario

            candidate, metadata = generate_scenario(
                load_scenario(args.base), args.seed, provider=args.provider, model=args.model
            )
            write_scenario(args.output, candidate)
            write_json(Path(args.output).with_suffix(".generation.json"), metadata)
            print(json.dumps({"scenario": args.output, "generation": metadata}, indent=2))
            return 0
        if args.command == "minimize":
            from .experiments import minimize

            data = minimize(
                read_trace(args.trace),
                out=args.out,
                trials=args.trials,
                budget=args.budget,
                rule=args.rule,
            )
            print(
                json.dumps(
                    {
                        k: data[k]
                        for k in (
                            "rule",
                            "baseline_reproduced",
                            "executions_used",
                            "stop_reason",
                            "note",
                        )
                    },
                    indent=2,
                )
            )
            return 0 if data["baseline_reproduced"] else 3
        if args.command == "study":
            from .experiments import study

            data = study(
                suite_paths(args.path),
                budget=args.budget,
                seed=args.seed if args.seed is not None else 17,
                out=args.out,
                agent_version=args.agent,
                provider=args.provider,
                model=args.model,
                generator_provider=args.generator_provider,
                generator_model=args.generator_model,
            )
            print(json.dumps({"summary": data["summary"], "note": data["note"]}, indent=2))
            combined = summarize([t for g in data["groups"].values() for t in g["runs"]])
            # Discovery of failures is study output. Harness errors and uncertainty still surface.
            return (
                2
                if combined["counts"]["harness_error"]
                else 3
                if combined["counts"]["inconclusive"]
                else 0
            )
        if args.command == "run":
            scenario = load_scenario(args.scenario)
            if args.seed is not None:
                scenario = scenario.model_copy(update={"seed": args.seed})
            options = (
                custom_options(load_agent_factory(args.agent_factory))
                if args.agent_factory
                else {"agent_version": args.agent, "provider": args.provider, "model": args.model}
            )
            trace = run_scenario(scenario, out=args.out, **options)
            print(
                json.dumps(
                    {
                        "run_id": trace["run_id"],
                        "status": trace["result"]["status"],
                        "violations": trace["result"]["violations"],
                        "reproduction_command": trace["reproduction_command"],
                    },
                    indent=2,
                )
            )
            return exit_code(summarize([trace]))
        if args.command == "suite":
            data = execute_suite(args, args.agent)
            save_bundle(Path(args.out) / "suite.json", data)
            print(json.dumps(data["summary"], indent=2))
            return exit_code(data["summary"])
        if args.command == "compare":
            left = execute_suite(args, "flawed")
            right = execute_suite(args, "corrected")
            data = {
                "comparison_version": 1,
                "flawed": left,
                "corrected": right,
                "summary": {
                    "flawed": left["summary"],
                    "corrected": right["summary"],
                    "execution_budget_per_agent": left["summary"]["total_trials"],
                    "note": "Identical seeds and initial fixtures; live model output may vary.",
                },
            }
            save_bundle(Path(args.out) / "comparison.json", data)
            print(json.dumps(data["summary"], indent=2))
            # Intentional flawed failures are expected; execution errors on either side are not.
            if left["summary"]["counts"]["harness_error"]:
                return 2
            if left["summary"]["counts"]["inconclusive"] and exit_code(right["summary"]) == 0:
                return 3
            return exit_code(right["summary"])
        if args.command == "rerun":
            recorded = read_trace(args.trace)  # Validate before importing user-selected code.
            options = (
                custom_options(load_agent_factory(args.agent_factory))
                if args.agent_factory
                else {"agent_version": args.agent, "provider": args.provider, "model": args.model}
            )
            trace = rerun(
                recorded,
                out=args.out,
                **options,
            )
            print(
                json.dumps(
                    {
                        "run_id": trace["run_id"],
                        "result": trace["result"],
                        "reproduction_command": trace["reproduction_command"],
                    },
                    indent=2,
                )
            )
            return exit_code(summarize([trace]))
        trace = read_trace(args.trace)
        if args.command == "export":
            save_bundle(args.output, trace)
            print(f"Exported {args.output} and {Path(args.output).with_suffix('.html')}")
        else:
            print(
                json.dumps(
                    {
                        "mode": "offline_playback",
                        "run_id": trace["run_id"],
                        "result": trace["result"],
                        "trial_summary": trace["trial_summary"],
                        "tool_events": trace["tool_events"],
                        "final_state": trace["final_state"],
                        "reproduction_command": trace["reproduction_command"],
                    },
                    indent=2,
                )
            )
        return 0
    except Exception as exc:  # CLI boundary: provider/IO failures must be labeled harness errors.
        print(f"harness_error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
