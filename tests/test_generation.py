import pytest

from agent_chaos.generation import generate_scenario, random_scenario, validate_proposal
from agent_chaos.schema import load_scenario


def test_scripted_generation_and_random_baseline_are_valid_and_seeded():
    base = load_scenario("scenarios/01_normal.yaml")
    for seed in range(20):
        a, metadata = generate_scenario(base, seed)
        b, _ = generate_scenario(base, seed)
        assert a == b
        assert a.payments == base.payments
        assert a.split == "generated"
        assert metadata["kind"] == "scripted_proposal"
        assert random_scenario(base, seed) == random_scenario(base, seed)


def test_rejects_invalid_sequences_and_out_of_scope_fixture_edits():
    base = load_scenario("scenarios/01_normal.yaml")
    proposal = {
        "turns": [t.model_dump() for t in base.turns],
        "faults": [{"kind": "visibility_delay", "tool": "get_payment"}],
    }
    with pytest.raises(ValueError, match="visibility_delay"):
        validate_proposal(base, proposal, name="bad", seed=1)
    proposal["faults"] = []
    proposal["payments"] = []
    with pytest.raises(ValueError, match="Extra inputs"):
        validate_proposal(base, proposal, name="bad", seed=1)


def test_mocked_generation_agent_validates_its_output():
    import json
    from types import SimpleNamespace

    base = load_scenario("scenarios/01_normal.yaml")
    proposal = {
        "turns": [t.model_dump() for t in base.turns],
        "faults": [{"kind": "after_timeout"}],
    }
    response = SimpleNamespace(
        output_text=json.dumps(proposal), model_dump=lambda **kw: {"usage": {"input_tokens": 4}}
    )
    client = SimpleNamespace(responses=SimpleNamespace(create=lambda **kw: response))
    candidate, metadata = generate_scenario(base, 5, provider="openai", model="mock", client=client)
    assert candidate.faults[0].kind == "after_timeout"
    assert metadata["kind"] == "llm_proposal"
