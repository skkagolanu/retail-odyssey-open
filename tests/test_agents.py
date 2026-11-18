import asyncio
import json

import httpx
import pytest

from src.api.main import create_app
from src.budget import CURRENT_BUDGET, TokenBudget
from src.providers import OllamaProvider, ProviderUnavailable
from tests.conftest import ORIGIN


async def test_real_agent_contracts_sequential_handoffs_shared_budget_and_logs(
    config, image, capsys
):
    config.engine = "ollama"
    calls = []

    def handler(request):
        payload = json.loads(request.content)
        calls.append(payload)
        schema = payload["format"]["properties"]
        if "description" in schema:
            result = {"description": "A blue shirt"}
        elif "product_ids" in schema:
            assert "A blue shirt" in payload["messages"][0]["content"]
            content = payload["messages"][0]["content"]
            candidates = json.loads(content[content.index("{") :])["candidates"]
            result = {"product_ids": [candidates[0]["id"]]}
        else:
            content = payload["messages"][0]["content"]
            selected = json.loads(content[content.index("{") :])["selected_products"]
            assert len(selected) == 1
            result = {"advice": "check_fit", "follow_up": "colour"}
        return httpx.Response(
            200,
            json={
                "done": True,
                "message": {"content": json.dumps(result)},
                "prompt_eval_count": 50,
                "eval_count": 20,
            },
        )

    app = create_app(config, httpx.MockTransport(handler))
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://localhost:8000", headers=ORIGIN
        ) as client,
    ):
        await client.get("/api/session")
        result = (
            await client.post(
                "/api/chat", json={"message": "casual outfit under £100", "image": image}
            )
        ).json()
        assert result["engine"] == "ollama" and len(calls) == 3
        assert [event["agent"] for event in result["agent_trace"]] == [
            "intent",
            "vision",
            "retrieval",
            "recommendation",
            "conversation",
        ]
        assert all(event["trace_id"] == result["trace_id"] for event in result["agent_trace"])
        assert result["token_budget"]["reserved_output_tokens"] == 384
        assert result["token_budget"]["reserved_input_tokens"] <= 10000
        assert [call["agent"] for call in result["token_budget"]["calls"]] == [
            "vision",
            "recommendation",
            "conversation",
        ]
        assert all(call["options"]["num_predict"] == 128 for call in calls)
        assert "Which colours" in result["answer"]
        event = app.state.metrics.recent_events[-1]
        assert event["agent"] == "conversation" and "message" not in event
        metrics = (await client.get("/metrics")).text
        assert "retail_agent_runs_total" in metrics and "retail_model_tokens_total" in metrics
        assert "A blue shirt" not in metrics


def test_budget_trims_oldest_complete_pairs_and_refuses_excess_calls():
    budget = TokenBudget(context_limit=1000, input_limit=3000, output_limit=256)
    messages = (
        [{"role": "system", "content": "rules"}]
        + [{"role": role, "content": "x" * 300} for _ in range(4) for role in ["user", "assistant"]]
        + [{"role": "user", "content": "latest"}]
    )
    trimmed, limit, record = budget.prepare(messages, {})
    assert trimmed[0] == messages[0] and trimmed[-1] == messages[-1]
    assert record["dropped_history_messages"] > 0 and record["dropped_history_messages"] % 2 == 0
    assert limit == 128
    budget.prepare([messages[0], messages[-1]], {})
    with pytest.raises(ProviderUnavailable, match="budget"):
        budget.prepare([messages[0], messages[-1]], {})


async def test_context_budgets_are_isolated_between_async_turns(config):
    async def run():
        budget = TokenBudget()
        token = CURRENT_BUDGET.set(budget)
        try:
            await asyncio.sleep(0)
            async with httpx.AsyncClient(
                transport=httpx.MockTransport(
                    lambda request: httpx.Response(
                        200, json={"done": True, "message": {"content": '{"product_ids":[]}'}}
                    )
                )
            ) as client:
                await OllamaProvider(config, client).answer([{"role": "user", "content": "outfit"}])
            return budget
        finally:
            CURRENT_BUDGET.reset(token)

    first, second = await asyncio.gather(run(), run())
    assert first is not second and len(first.calls) == len(second.calls) == 1
    assert CURRENT_BUDGET.get() is None


async def test_conversation_out_of_schema_plan_never_reaches_public_answer(config):
    config.engine = "ollama"

    def handler(request):
        payload = json.loads(request.content)
        if "product_ids" in payload["format"]["properties"]:
            content = payload["messages"][0]["content"]
            candidates = json.loads(content[content.index("{") :])["candidates"]
            result = {"product_ids": [candidates[0]["id"]]}
        else:
            result = {"advice": "buy my fake product", "follow_up": "none"}
        return httpx.Response(200, json={"done": True, "message": {"content": json.dumps(result)}})

    app = create_app(config, httpx.MockTransport(handler))
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://localhost:8000", headers=ORIGIN
        ) as client,
    ):
        await client.get("/api/session")
        result = (
            await client.post("/api/chat", json={"message": "classic business outfit"})
        ).json()
        assert result["products"] and "fake product" not in result["answer"]
        assert any("conversation agent" in warning for warning in result["warnings"])
