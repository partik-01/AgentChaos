"""Post-MVP experiments with explicit trial budgets and no automatic fixes."""

import copy
from pathlib import Path

from .generation import generate_scenario, random_scenario, write_scenario
from .runner import run_scenario, summarize, write_json
from .schema import Scenario, load_scenario


def has_rule(trace, rule):
    return trace["result"]["status"] == "agent_failure" and any(
        v["rule"] == rule for v in trace["result"]["violations"]
    )


def candidates(scenario: Scenario):
    """Greedy single-deletion candidates, each independently schema validated."""
    data = scenario.model_dump()
    for index in range(len(data["faults"])):
        candidate = copy.deepcopy(data)
        del candidate["faults"][index]
        yield f"remove fault {index}", candidate
    if len(data["turns"]) > 1:
        for index in range(len(data["turns"])):
            candidate = copy.deepcopy(data)
            del candidate["turns"][index]
            yield f"remove turn {index}", candidate
    for ti, turn in enumerate(data["turns"]):
        if len(turn["messages"]) > 1:
            for mi in range(len(turn["messages"])):
                candidate = copy.deepcopy(data)
                del candidate["turns"][ti]["messages"][mi]
                yield f"remove message {ti}:{mi}", candidate


def minimize(trace: dict, *, out="runs/minimize", trials=3, budget=60, rule=None):
    if trials < 2 or budget < trials:
        raise ValueError("minimization requires at least 2 trials and budget >= trials")
    if trace["result"]["status"] != "agent_failure":
        raise ValueError("only recorded agent failures can be minimized")
    rule = rule or trace["result"]["violations"][0]["rule"]
    config = trace["configuration"]
    scenario = Scenario.model_validate(trace["scenario"])
    used = 0
    attempts = []

    def evaluate(candidate, label):
        nonlocal used
        results = []
        for trial in range(trials):
            results.append(
                run_scenario(
                    candidate.model_copy(update={"seed": scenario.seed + trial}),
                    config["agent_version"],
                    provider=config["provider"],
                    model=config.get("model"),
                    initial=trace["initial_state"],
                    parent_run=trace["run_id"],
                    out=out,
                )
            )
            used += 1
        preserved = all(has_rule(t, rule) for t in results)
        attempts.append(
            {
                "change": label,
                "preserved_in_all_trials": preserved,
                "summary": summarize(results),
                "runs": results,
            }
        )
        return preserved

    baseline = evaluate(scenario, "baseline reproduction")
    if baseline:
        changed = True
        while changed and used + trials <= budget:
            changed = False
            for label, proposal in candidates(scenario):
                if used + trials > budget:
                    break
                try:
                    candidate = Scenario.model_validate(proposal)
                except ValueError:
                    continue
                if evaluate(candidate, label):
                    scenario = candidate
                    changed = True
                    break
    result = {
        "minimization_version": 1,
        "source_run": trace["run_id"],
        "rule": rule,
        "baseline_reproduced": baseline,
        "trials_per_candidate": trials,
        "execution_budget": budget,
        "executions_used": used,
        "stop_reason": "baseline_not_reproduced"
        if not baseline
        else "budget_exhausted"
        if used + trials > budget
        else "no_preserving_single_deletion",
        "scenario": scenario.model_dump(),
        "attempts": attempts,
        "note": "Greedy local reduction, not a globally minimal proof. Live model reruns can vary.",
    }
    write_scenario(Path(out) / "minimized.yaml", scenario)
    write_json(Path(out) / "minimization.json", result)
    from .reports import write_html

    write_html(Path(out) / "minimization.html", result)
    return result


def study(
    paths: list[Path],
    *,
    budget=24,
    seed=17,
    out="runs/study",
    agent_version="flawed",
    provider="scripted",
    model=None,
    generator_provider="scripted",
    generator_model=None,
):
    if budget < 1:
        raise ValueError("execution budget must be positive")
    fixed = [load_scenario(p) for p in paths]
    if not fixed:
        raise ValueError("fixed scenario set is empty")
    base = next(
        (s for s in fixed if not s.faults and len(s.turns) == 1 and len(s.turns[0].messages) == 1),
        None,
    )
    if base is None:
        raise ValueError("study requires a fault-free one-request baseline scenario")
    groups = {}
    proposals = []
    # Groups execute sequentially; exactly budget target executions per group.
    for kind in ("fixed", "generated", "random"):
        traces = []
        for trial in range(budget):
            trial_seed = seed + trial
            if kind == "fixed":
                scenario = fixed[trial % len(fixed)].model_copy(update={"seed": trial_seed})
            elif kind == "generated":
                scenario, metadata = generate_scenario(
                    base, trial_seed, provider=generator_provider, model=generator_model
                )
                proposals.append(metadata)
                write_scenario(Path(out) / "proposals" / f"{trial:04d}.yaml", scenario)
                write_json(Path(out) / "proposals" / f"{trial:04d}.json", metadata)
            else:
                scenario = random_scenario(base, trial_seed)
            traces.append(
                run_scenario(scenario, agent_version, provider=provider, model=model, out=out)
            )
        groups[kind] = {"summary": summarize(traces), "runs": traces}
    result = {
        "study_version": 1,
        "budget_per_group": budget,
        "total_target_executions": 3 * budget,
        "seed": seed,
        "agent_version": agent_version,
        "provider": provider,
        "summary": {kind: group["summary"] for kind, group in groups.items()},
        "groups": groups,
        "generation_metadata": proposals,
        "generation_model_calls": sum(m["kind"] == "llm_proposal" for m in proposals),
        "note": "Equal target-execution budgets, not equal tokens or dollar costs. Generation overhead"
        " is additional and recorded. Generated/random use the normal baseline fixture;"
        " fixed cases cycle in filename order. No ranking or statistical claim is implied.",
    }
    write_json(Path(out) / "study.json", result)
    from .reports import write_html

    write_html(Path(out) / "study.html", result)
    return result
