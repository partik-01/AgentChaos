from pathlib import Path

import pytest

from agent_chaos.experiments import minimize, study
from agent_chaos.runner import run_scenario
from agent_chaos.schema import Fault, load_scenario


def test_minimization_removes_unneeded_fault_but_preserves_duplicate(tmp_path):
    scenario = load_scenario("scenarios/03_after_timeout.yaml")
    scenario = scenario.model_copy(
        update={
            "faults": scenario.faults
            + [Fault(tool="get_payment", kind="rate_limit", occurrence=99)]
        }
    )
    failed = run_scenario(scenario, "flawed", out=tmp_path)
    reduced = minimize(
        failed, out=tmp_path / "reduced", trials=3, budget=30, rule="no_duplicate_economic_effect"
    )
    assert reduced["baseline_reproduced"]
    assert reduced["executions_used"] <= 30
    assert len(reduced["scenario"]["faults"]) == 1
    assert reduced["scenario"]["faults"][0]["kind"] == "after_timeout"
    accepted = [a for a in reduced["attempts"] if a["preserved_in_all_trials"]]
    assert all(a["summary"]["failure_count"] == 3 for a in accepted)
    assert (tmp_path / "reduced" / "minimized.yaml").exists()


def test_minimizer_refuses_nonfailure_and_one_trial(tmp_path):
    trace = run_scenario(load_scenario("scenarios/01_normal.yaml"), out=tmp_path)
    with pytest.raises(ValueError, match="failures"):
        minimize(trace, out=tmp_path)
    with pytest.raises(ValueError, match="at least 2"):
        minimize(trace, out=tmp_path, trials=1)


def test_equal_execution_budget_and_generation_labels(tmp_path):
    result = study(sorted(Path("scenarios").glob("*.yaml")), budget=4, out=tmp_path)
    assert result["total_target_executions"] == 12
    assert result["generation_model_calls"] == 0
    assert all(g["summary"]["total_trials"] == 4 for g in result["groups"].values())
    assert all(m["kind"] == "scripted_proposal" for m in result["generation_metadata"])
    assert (tmp_path / "study.html").exists()


def test_experiment_cli_commands(tmp_path, capsys):
    from agent_chaos.cli import main

    generated = tmp_path / "generated.yaml"
    assert main(["generate", "scenarios/01_normal.yaml", "--output", str(generated)]) == 0
    assert load_scenario(generated).split == "generated"
    assert generated.with_suffix(".generation.json").exists()
    assert main(["study", "scenarios", "--budget", "2", "--out", str(tmp_path / "study")]) == 0
    failed = run_scenario(load_scenario("scenarios/03_after_timeout.yaml"), "flawed", out=tmp_path)
    assert (
        main(
            [
                "minimize",
                str(tmp_path / failed["run_id"] / "trace.json"),
                "--trials",
                "2",
                "--budget",
                "4",
                "--out",
                str(tmp_path / "minimal"),
            ]
        )
        == 0
    )
