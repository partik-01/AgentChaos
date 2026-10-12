import json
from pathlib import Path

import pytest

from agent_chaos.agents import AgentFailure
from agent_chaos.cli import main
from agent_chaos.reports import render_html
from agent_chaos.runner import read_trace, rerun, run_scenario, summarize
from agent_chaos.schema import load_scenario


@pytest.mark.parametrize("path", sorted(Path("scenarios").glob("*.yaml")), ids=lambda p: p.stem)
def test_corrected_handles_fixed_scenarios(path, tmp_path):
    trace = run_scenario(load_scenario(path), out=tmp_path)
    assert trace["result"]["status"] == "pass"
    assert Path(trace["reproduction_command"].split(" ", 2)[-1]).is_file()


@pytest.mark.parametrize("number", [3, 4, 5, 6, 7, 8])
def test_flawed_exposes_known_failures(number, tmp_path):
    path = next(Path("scenarios").glob(f"{number:02d}_*.yaml"))
    trace = run_scenario(load_scenario(path), "flawed", out=tmp_path)
    assert trace["result"]["status"] == "agent_failure"
    if number in (3, 4, 7, 8):
        assert len(trace["final_state"]["refunds"]) == 2
        assert sum(r["amount_cents"] for r in trace["final_state"]["refunds"]) == 600


def test_offline_playback_rerun_with_fix_and_export(tmp_path, capsys):
    scenario = load_scenario("scenarios/03_after_timeout.yaml")
    failed = run_scenario(scenario, "flawed", out=tmp_path)
    path = tmp_path / failed["run_id"] / "trace.json"
    before = path.read_bytes()
    assert main(["playback", str(path)]) == 0
    assert path.read_bytes() == before
    recorded = read_trace(path)
    reproduced = rerun(recorded, out=tmp_path)
    assert reproduced["final_state"] == failed["final_state"]
    assert reproduced["fault_schedule"] == failed["fault_schedule"]
    fixed = rerun(recorded, out=tmp_path, agent_version="corrected")
    assert fixed["result"]["status"] == "pass"
    assert fixed["initial_state"] == failed["initial_state"]
    assert fixed["parent_run"] == failed["run_id"]
    output = tmp_path / "export.json"
    assert main(["export", str(path), "--output", str(output)]) == 0
    assert json.loads(output.read_text())["run_id"] == failed["run_id"]
    assert output.with_suffix(".html").exists()


def test_provider_or_target_errors_never_pass(tmp_path):
    scenario = load_scenario("scenarios/01_normal.yaml")

    class Broken:
        metadata = {"conversation_assessment": "unassessed"}

        def run_turn(self, *args):
            raise RuntimeError("provider unavailable")

    trace = run_scenario(scenario, out=tmp_path, agent=Broken())
    assert trace["result"]["status"] == "harness_error"
    assert summarize([trace])["counts"]["pass"] == 0

    class Invalid(Broken):
        def run_turn(self, *args):
            raise AgentFailure("bad output")

    assert (
        run_scenario(scenario, out=tmp_path, agent=Invalid())["result"]["status"] == "agent_failure"
    )


def test_suite_counts_and_holdout_exclusion(tmp_path, capsys):
    assert main(["suite", "scenarios", "--trials", "2", "--out", str(tmp_path)]) == 0
    data = json.loads((tmp_path / "suite.json").read_text())
    assert data["summary"]["total_trials"] == 16
    assert not any(r["scenario"]["split"] == "heldout" for r in data["runs"])
    assert main(["suite", str(tmp_path / "empty")]) == 2


def test_html_escapes_customer_content(tmp_path):
    trace = run_scenario(load_scenario("scenarios/01_normal.yaml"), out=tmp_path)
    trace["messages"][0]["messages"][0]["text"] = '<script>alert("x")</script>'
    page = render_html(trace)
    assert "<script>" not in page
    assert "&lt;script&gt;" in page


def test_cli_agent_failure_exit_and_invalid_input(tmp_path, capsys):
    assert (
        main(
            ["run", "scenarios/03_after_timeout.yaml", "--agent", "flawed", "--out", str(tmp_path)]
        )
        == 1
    )
    assert main(["run", "missing.yaml"]) == 2


def test_versioned_trace_rejects_unknown_format(tmp_path):
    path = tmp_path / "trace.json"
    path.write_text('{"trace_version": 900}')
    with pytest.raises(ValueError, match="unsupported"):
        read_trace(path)


def test_repeated_request_after_uncertainty_reconciles_even_when_balance_is_lower(tmp_path):
    from agent_chaos.schema import Scenario

    data = load_scenario("scenarios/05_delayed_visibility.yaml").model_dump()
    data["turns"][0]["messages"][0]["amount_cents"] = 600
    data["turns"].append(data["turns"][0])
    data["faults"] = [
        {"kind": "visibility_delay", "hidden_reads": 100},
        {"kind": "after_timeout", "occurrence": 2},
        {"kind": "malformed", "occurrence": 3},
    ]
    trace = run_scenario(Scenario.model_validate(data), out=tmp_path)
    assert trace["responses"][0]["claims"][0]["status"] == "uncertain"
    assert trace["responses"][1]["claims"][0]["status"] == "completed"
    assert trace["result"]["status"] == "inconclusive"  # Earlier uncertainty stays visible.
    assert len(trace["final_state"]["refunds"]) == 1
    calls = [e for e in trace["tool_events"] if e["tool"] == "create_refund"]
    assert len(calls) == 4
    assert len({e["arguments"]["idempotency_key"] for e in calls}) == 1


def test_maximum_length_request_id_can_form_a_valid_idempotency_key(tmp_path):
    from agent_chaos.schema import Scenario

    data = load_scenario("scenarios/01_normal.yaml").model_dump()
    data["turns"][0]["messages"][0]["request_id"] = "r" * 200
    assert run_scenario(Scenario.model_validate(data), out=tmp_path)["result"]["status"] == "pass"


def test_invalid_agent_output_retains_financial_consequences(tmp_path):
    class DuplicateThenInvalid:
        metadata = {"conversation_assessment": "unassessed"}

        def run_turn(self, turn, tools):
            m = turn.messages[0]
            args = {
                k: getattr(m, k)
                for k in ("request_id", "payment_id", "customer_id", "amount_cents")
            }
            tools.call("create_refund", args | {"idempotency_key": "one"})
            tools.call("create_refund", args | {"idempotency_key": "two"})
            raise AgentFailure("invalid response after duplicate commit")

    trace = run_scenario(
        load_scenario("scenarios/01_normal.yaml"), out=tmp_path, agent=DuplicateThenInvalid()
    )
    assert trace["result"]["status"] == "agent_failure"
    assert {"agent_output_valid", "exact_total_refunded", "no_duplicate_economic_effect"} <= {
        v["rule"] for v in trace["result"]["violations"]
    }


def test_provider_error_preserves_ledger_evidence_without_counting_pass(tmp_path):
    class ProviderFailure:
        metadata = {"conversation_assessment": "unassessed"}

        def run_turn(self, turn, tools):
            m = turn.messages[0]
            args = {
                k: getattr(m, k)
                for k in ("request_id", "payment_id", "customer_id", "amount_cents")
            }
            tools.call("create_refund", args | {"idempotency_key": "one"})
            tools.call("create_refund", args | {"idempotency_key": "two"})
            raise RuntimeError("provider connection failed")

    trace = run_scenario(
        load_scenario("scenarios/01_normal.yaml"), out=tmp_path, agent=ProviderFailure()
    )
    assert trace["result"]["status"] == "harness_error"
    assert "exact_total_refunded" in {v["rule"] for v in trace["result"]["violations"]}
    assert len(trace["final_state"]["refunds"]) == 2


def test_reproduction_command_quotes_paths_with_spaces(tmp_path):
    import shlex

    folder = tmp_path / "evidence with spaces"
    trace = run_scenario(load_scenario("scenarios/01_normal.yaml"), out=folder)
    tokens = shlex.split(trace["reproduction_command"])
    assert tokens[:2] == ["agent-chaos", "rerun"]
    assert Path(tokens[2]).is_file()
    assert main(tokens[1:] + ["--out", str(tmp_path / "rerun")]) == 0


@pytest.mark.parametrize(
    "flawed_status,corrected_status,expected_exit",
    [
        ("agent_failure", "pass", 0),
        ("harness_error", "pass", 2),
        ("harness_error", "agent_failure", 2),
        ("inconclusive", "pass", 3),
        ("pass", "harness_error", 2),
        ("pass", "inconclusive", 3),
        ("pass", "agent_failure", 1),
    ],
)
def test_comparison_does_not_hide_execution_errors(
    tmp_path, monkeypatch, capsys, flawed_status, corrected_status, expected_exit
):
    def suite(args, agent):
        status = flawed_status if agent == "flawed" else corrected_status
        return {
            "summary": summarize(
                [{"scenario": {"name": "comparison"}, "result": {"status": status}}]
            ),
            "runs": [],
        }

    monkeypatch.setattr("agent_chaos.cli.execute_suite", suite)
    assert main(["compare", "scenarios", "--out", str(tmp_path)]) == expected_exit
    saved = json.loads((tmp_path / "comparison.json").read_text())
    assert saved["summary"]["flawed"]["counts"][flawed_status] == 1
    assert saved["summary"]["corrected"]["counts"][corrected_status] == 1
