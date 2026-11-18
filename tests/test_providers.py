import base64
import json

import httpx
import pytest

from src.api.main import create_app
from src.providers import (
    ComfyProvider,
    OllamaProvider,
    ProviderUnavailable,
    bounded_json,
    normalize_image,
)
from tests.conftest import ORIGIN


@pytest.mark.parametrize(
    "image",
    [
        "https://example.com/photo.png",
        "data:image/svg+xml;base64,AA==",
        "data:image/png;base64,notbase64",
        "data:image/png;base64," + base64.b64encode(b"not an image").decode(),
    ],
)
def test_reject_untrusted_images(image):
    with pytest.raises(ValueError):
        normalize_image(image)


def test_image_normalized_and_metadata_removed(image):
    result = normalize_image(image)
    assert result and result != image.split(",")[1]
    assert base64.b64decode(result).startswith(b"\xff\xd8")


async def test_ollama_schema_vision_and_usage(config, image):
    requests = []

    def handler(request):
        data = json.loads(request.content)
        requests.append(data)
        if "description" in data["format"]["properties"]:
            content = {"description": "A blue shirt"}
        else:
            content = {"product_ids": ["sample-1"]}
        return httpx.Response(
            200,
            json={
                "done": True,
                "message": {"content": json.dumps(content)},
                "eval_count": 12,
                "prompt_eval_count": 44,
                "total_duration": 10000,
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = OllamaProvider(config, client)
        answer, usage = await provider.answer([{"role": "user", "content": "casual outfit"}])
        assert answer.product_ids == ["sample-1"] and usage["eval_count"] == 12
        description, _ = await provider.vision("describe this shirt", normalize_image(image))
        assert description == "A blue shirt"
        assert requests[1]["messages"][1]["images"] == [normalize_image(image)]
        assert requests[0]["format"]["additionalProperties"] is False
        assert requests[0]["options"]["num_thread"] == 2


@pytest.mark.parametrize(
    "value",
    [
        {"done": False, "message": {"content": "{}"}},
        {"done": True, "message": {}},
        {"done": True, "message": {"content": "not-json"}},
        {"done": True, "message": {"content": '{"answer":"hi","product_ids":[],"url":"evil"}'}},
    ],
)
async def test_ollama_invalid_outputs(config, value):
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=value))
    ) as client:
        with pytest.raises(ProviderUnavailable):
            await OllamaProvider(config, client).answer([])


async def test_bounded_provider_error_no_upstream_body_leak():
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(500, text="private upstream debug")
        )
    ) as client:
        with pytest.raises(ProviderUnavailable, match="configured local service") as error:
            await bounded_json(client, "GET", "http://local/api")
        assert "private upstream" not in str(error.value)
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, content=b"x" * 1_000_001))
    ) as client:
        with pytest.raises(ProviderUnavailable, match="size limit"):
            await bounded_json(client, "GET", "http://local/api")


async def test_ollama_unavailable_health_and_grounded_fallback(config):
    config.engine = "ollama"
    app = create_app(config, httpx.MockTransport(lambda request: httpx.Response(503)))
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://localhost:8000", headers=ORIGIN
        ) as client,
    ):
        assert (await client.get("/api/health")).json()["status"] == "degraded"
        await client.get("/api/session")
        result = (await client.post("/api/chat", json={"message": "casual outfit"})).json()
        assert result["engine"] == "catalogue" and result["products"] and result["warnings"]


async def test_comfy_real_protocol_paths_workflow_and_owned_cleanup(config, tmp_path, image):
    path = tmp_path / "workflow.json"
    path.write_text(
        json.dumps(
            {"1": {"inputs": {"text": "{{prompt}}", "seed": "{{seed}}"}, "class_type": "Example"}}
        )
    )
    config.comfyui_url, config.comfyui_workflow = "http://local", path
    calls = []

    def handler(request):
        calls.append((request.url.path, json.loads(request.content) if request.content else None))
        if request.url.path == "/prompt":
            assert calls[-1][1]["prompt"]["1"]["inputs"]["text"] == "Blue shirt outfit"
            assert isinstance(calls[-1][1]["prompt"]["1"]["inputs"]["seed"], int)
            return httpx.Response(200, json={"prompt_id": "job-1"})
        if request.url.path == "/history/job-1":
            return httpx.Response(
                200,
                json={
                    "job-1": {
                        "outputs": {"2": {"images": [{"filename": "look.png", "subfolder": ""}]}}
                    }
                },
            )
        if request.url.path == "/view":
            return httpx.Response(200, content=base64.b64decode(image.split(",")[1]))
        return httpx.Response(200, json={})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await ComfyProvider(config, client).generate("Blue shirt outfit")
        assert result.startswith("data:image/jpeg;base64,")
        assert calls[-1] == ("/queue", {"delete": ["job-1"]})
        assert not any(path == "/interrupt" for path, _ in calls)


async def test_comfy_invalid_file_and_bad_download_are_not_success(config, tmp_path):
    config.comfyui_url = "http://local"
    config.comfyui_workflow = tmp_path / "missing.json"
    async with httpx.AsyncClient() as client:
        with pytest.raises(ProviderUnavailable):
            await ComfyProvider(config, client).generate("look")
    config.comfyui_workflow.write_text('{"text":"{{prompt}}"}')

    def handler(request):
        if request.url.path == "/prompt":
            return httpx.Response(200, json={"prompt_id": "job-1"})
        if request.url.path.startswith("/history"):
            return httpx.Response(
                200, json={"job-1": {"outputs": {"2": {"images": [{"filename": "../bad.png"}]}}}}
            )
        return httpx.Response(200, json={})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ProviderUnavailable):
            await ComfyProvider(config, client).generate("look")


async def test_token_budget_exhaustion_is_unavailable_not_a_finished_answer(config):
    payload = {"done": True, "done_reason": "length", "message": {"content": '{"product_ids": []}'}}
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload))
    ) as client:
        with pytest.raises(ProviderUnavailable, match="did not finish"):
            await OllamaProvider(config, client).answer([])
