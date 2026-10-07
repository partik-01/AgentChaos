import json
from types import SimpleNamespace

import pytest

from agent_chaos.agents import AgentFailure
from agent_chaos.faults import FaultMiddleware
from agent_chaos.openai_agent import OpenAIAgent
from agent_chaos.payments import PaymentService
from agent_chaos.schema import load_scenario


class Response:
    def __init__(self, output, text=""):
        self.output = output
        self.output_text = text

    def model_dump(self, **kwargs):
        return {"output": self.output, "usage": {"input_tokens": 10, "output_tokens": 5},
                "model": "mock-model", "status": "completed"}


class FakeClient:
    def __init__(self, outputs):
        self.outputs = iter(outputs)
        self.requests = []
        self.responses = SimpleNamespace(create=self.create)

    def create(self, **kwargs):
        # Copy because the adapter appends to its history later.
        self.requests.append(json.loads(json.dumps(kwargs)))
        return next(self.outputs)


def test_real_adapter_tool_loop_with_mocked_provider():
    scenario = load_scenario("scenarios/03_after_timeout.yaml")
    refund_args = dict(payment_id="pay_alice", customer_id="alice", amount_cents=300,
                       idempotency_key="request:refund-001")
    def call(name, args, call_id):
        return Response([{"type": "function_call", "name": name,
                          "arguments": json.dumps(args), "call_id": call_id}])
    answer = dict(request_id="refund-001", payment_id="pay_alice", customer_id="alice",
                  amount_cents=300, status="completed", text="Refunded 300 cents.")
    client = FakeClient([call("create_refund", refund_args, "1"),
                         call("get_refund_status", {"idempotency_key": "request:refund-001"}, "2"),
                         Response([], json.dumps({"claims": [answer]}))])
    service = PaymentService()
    service.restore({"payments": [p.model_dump() for p in scenario.payments], "refunds": []})
    middleware = FaultMiddleware(service, scenario.faults, 17)
    agent = OpenAIAgent("corrected", "mock-model", client=client)
    assert agent.run_turn(scenario.turns[0], middleware)[0].status == "completed"
    assert json.loads(client.requests[1]["input"][-1]["output"])["error"] == "timeout"
    assert agent.metadata["usage"] == {"input_tokens": 30, "output_tokens": 15}
    assert len(service.snapshot()["refunds"]) == 1
    assert client.requests[0]["store"] is False
    service.close()


def test_invalid_model_output_is_agent_failure():
    agent = OpenAIAgent("corrected", "mock", client=FakeClient([Response([], "nonsense")]))
    with pytest.raises(AgentFailure, match="invalid customer response"):
        agent.run_turn(load_scenario("scenarios/01_normal.yaml").turns[0], None)


def test_missing_model_does_not_make_a_live_call():
    with pytest.raises(ValueError, match="model"):
        OpenAIAgent("corrected", None)
