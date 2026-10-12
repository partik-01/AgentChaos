"""Exercise the real optional SDK through an offline HTTP transport, without an API key."""

import json

import pytest

openai = pytest.importorskip("openai", reason="Install the OpenAI extra for SDK transport tests")
httpx = pytest.importorskip("httpx")

from agent_chaos.openai_agent import OpenAIAgent  # noqa: E402
from agent_chaos.runner import run_scenario  # noqa: E402
from agent_chaos.schema import load_scenario  # noqa: E402
from agent_chaos.traces import validate_trace  # noqa: E402


def test_actual_sdk_serializes_tools_reconciles_timeout_and_records_usage(tmp_path):
    scenario = load_scenario("scenarios/03_after_timeout.yaml")
    message = scenario.turns[0].messages[0]
    refund_args = {
        k: getattr(message, k) for k in ("request_id", "payment_id", "customer_id", "amount_cents")
    } | {"idempotency_key": "request:refund-001"}
    requests = []

    def response_for(request):
        assert str(request.url) == "https://api.openai.com/v1/responses"
        assert request.method == "POST"
        body = json.loads(request.content)
        requests.append(body)
        index = len(requests)
        if index < 3:
            output = [
                {
                    "type": "function_call",
                    "id": f"fc_{index}",
                    "call_id": f"call_{index}",
                    "name": "create_refund" if index == 1 else "get_refund_status",
                    "arguments": json.dumps(
                        refund_args if index == 1 else {"idempotency_key": "request:refund-001"}
                    ),
                    "status": "completed",
                }
            ]
        else:
            claims = {
                k: getattr(message, k)
                for k in ("request_id", "payment_id", "customer_id", "amount_cents")
            }
            claims |= {"status": "completed", "text": "Your 300-cent refund completed."}
            output = [
                {
                    "type": "message",
                    "id": "msg_final",
                    "role": "assistant",
                    "status": "completed",
                    "content": [
                        {
                            "type": "output_text",
                            "text": json.dumps({"claims": [claims]}),
                            "annotations": [],
                        }
                    ],
                }
            ]
        return httpx.Response(
            200,
            json={
                "id": f"resp_{index}",
                "object": "response",
                "created_at": 0,
                "status": "completed",
                "model": "offline-sdk-model",
                "output": output,
                "parallel_tool_calls": False,
                "tool_choice": "auto",
                "tools": [],
                "usage": {
                    "input_tokens": 11,
                    "output_tokens": 7,
                    "total_tokens": 18,
                    "input_tokens_details": {"cached_tokens": 0},
                    "output_tokens_details": {"reasoning_tokens": 0},
                },
            },
        )

    transport = httpx.MockTransport(response_for)
    with openai.OpenAI(
        api_key="offline-placeholder", max_retries=0, http_client=httpx.Client(transport=transport)
    ) as client:
        agent = OpenAIAgent("corrected", "offline-sdk-model", client=client)
        trace = run_scenario(
            scenario, provider="openai", model="offline-sdk-model", agent=agent, out=tmp_path
        )
    assert len(requests) == 3
    assert all(r["store"] is False and r["parallel_tool_calls"] is False for r in requests)
    assert len(requests[0]["tools"]) == 4
    assert all(t["strict"] is True for t in requests[0]["tools"])
    assert requests[0]["text"]["format"]["type"] == "json_schema"
    assert json.loads(requests[1]["input"][-1]["output"])["error"] == "timeout"
    assert json.loads(requests[2]["input"][-1]["output"])["status"] == "succeeded"
    assert len(trace["final_state"]["refunds"]) == 1
    assert trace["agent"]["usage"] == {"input_tokens": 33, "output_tokens": 21}
    assert len(trace["agent"]["model_calls"]) == 3
    assert trace["result"]["violations"] == []
    assert trace["result"]["status"] == "inconclusive"  # Model prose remains unassessed.
    assert trace["agent"]["cost_usd"] is None
    assert "offline-placeholder" not in json.dumps(trace)
    validate_trace(trace)
    trace["agent"]["usage"]["input_tokens"] += 1
    with pytest.raises(ValueError, match="sum recorded model calls"):
        validate_trace(trace)
