import json

import httpx
import pytest
from pydantic import SecretStr

from src.api.main import create_app
from src.settings import Settings
from tests.conftest import ORIGIN


def cloud_config(config):
    return Settings(
        _env_file=None,
        database_path=config.database_path,
        engine="cloudflare",
        cloudflare_account_id="a" * 32,
        cloudflare_api_token=SecretStr("unit-test-token"),
        cloudflare_free_plan_confirmed=True,
    )


async def test_five_agents_cloud_protocol_no_local_service_and_image_validation(config, image):
    config = cloud_config(config)
    calls = []

    def handler(request):
        assert request.url.host == "api.cloudflare.com"
        assert request.headers["Authorization"] == "Bearer unit-test-token"
        data = json.loads(request.content) if request.content else {}
        calls.append(request)
        if request.url.path.endswith("/models/search"):
            return httpx.Response(
                200, json={"success": True, "result": [{"name": config.cloudflare_model}]}
            )
        if "/ai/run/" in request.url.path:
            assert data["steps"] == 4 and data["prompt"]
            return httpx.Response(
                200, json={"success": True, "result": {"image": image.split(",")[1]}}
            )
        properties = data["response_format"]["json_schema"]["schema"]["properties"]
        assert data["max_completion_tokens"] == 512 and data["stream"] is False
        if "description" in properties:
            content = data["messages"][-1]["content"]
            assert content[1]["image_url"]["url"].startswith("data:image/jpeg;base64,")
            result = {"description": "blue shirt"}
        elif "product_ids" in properties:
            text = data["messages"][0]["content"]
            assert "blue shirt" in text
            candidates = json.loads(text[text.index("{") :])["candidates"]
            result = {"product_ids": [candidates[0]["id"]]}
        else:
            result = {"advice": "check_fit", "follow_up": "colour"}
        return httpx.Response(
            200,
            json={
                "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(result)}}],
                "usage": {"prompt_tokens": 50, "completion_tokens": 20},
            },
        )

    app = create_app(config, httpx.MockTransport(handler))
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://localhost:8000", headers=ORIGIN
        ) as client,
    ):
        assert (await client.get("/api/health")).json()["status"] == "ready"
        await client.get("/api/session")
        result = (
            await client.post(
                "/api/chat", json={"message": "visualize a casual outfit", "image": image}
            )
        ).json()
        assert result["engine"] == "cloudflare" and result["warnings"] == []
        assert result["image_kind"] == "generated" and result["image"].startswith(
            "data:image/jpeg;base64,"
        )
        assert [event["agent"] for event in result["agent_trace"]] == [
            "intent",
            "vision",
            "retrieval",
            "recommendation",
            "conversation",
            "image",
        ]
        assert result["token_budget"]["reserved_output_tokens"] == 1536
        assert [row["usage"]["eval_count"] for row in result["token_budget"]["calls"]] == [
            20,
            20,
            20,
        ]
        stored = await app.state.store.read(client.cookies.get("retail_session"))
        assert "base64" not in stored.model_dump_json()
        assert "unit-test-token" not in json.dumps(result)


async def test_cloud_quota_failure_never_retries_or_switches_to_billable_provider(config):
    config = cloud_config(config)
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(429, json={"detail": "private upstream body"})

    app = create_app(config, httpx.MockTransport(handler))
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://localhost:8000", headers=ORIGIN
        ) as client,
    ):
        await client.get("/api/session")
        result = (await client.post("/api/chat", json={"message": "casual outfit"})).json()
        assert len(calls) == 1 and result["engine"] == "catalogue"
        assert result["products"] and result["warnings"]
        assert "private upstream body" not in json.dumps(result)
        assert result["token_budget"]["calls"][0]["status"] == "unavailable"


def test_cloud_mode_requires_explicit_free_plan_configuration(config):
    with pytest.raises(ValueError, match="confirmation"):
        Settings(
            _env_file=None,
            engine="cloudflare",
            cloudflare_account_id="a" * 32,
            cloudflare_api_token=SecretStr("unit-test-token"),
        )
    assert "unit-test-token" not in repr(cloud_config(config))


async def test_cloud_missing_generated_bytes_not_success(config):
    from src.cloud_provider import CloudflareImageProvider
    from src.providers import ProviderUnavailable

    config = cloud_config(config)
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"success": True, "result": {}})
        )
    ) as client:
        with pytest.raises(ProviderUnavailable, match="no image"):
            await CloudflareImageProvider(config, client).generate("sample outfit")
