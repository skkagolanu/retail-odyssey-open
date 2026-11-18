import asyncio

import httpx

from src.api.main import create_app


async def test_csrf_host_and_body_limits(config):
    config.max_body_bytes = 1024
    app = create_app(config)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://localhost:8000"
        ) as client,
    ):
        await client.get("/api/session")
        for origin in ["", "https://evil.test", "http://localhost:8000.evil.test"]:
            result = await client.post(
                "/api/chat", json={"message": "hi"}, headers={"Origin": origin}
            )
            assert result.status_code == 403
        assert (await client.get("/api/health", headers={"Host": "evil.test"})).status_code == 400
        assert (
            await client.post(
                "/api/chat", content="x" * 2000, headers={"Origin": "http://localhost:8000"}
            )
        ).status_code == 413

        async def chunks():
            yield b"x" * 600
            yield b"x" * 600

        assert (
            await client.post(
                "/api/chat", content=chunks(), headers={"Origin": "http://localhost:8000"}
            )
        ).status_code == 413
        result = await client.options(
            "/api/chat",
            headers={"Origin": "https://evil.test", "Access-Control-Request-Method": "POST"},
        )
        assert "access-control-allow-origin" not in result.headers


async def test_metrics_literal_products_sessions_and_inclusive_timing(app, client):
    original = app.state.orchestrator.process_message

    async def delayed(*args):
        await asyncio.sleep(0.03)
        return await original(*args)

    app.state.orchestrator.process_message = delayed
    response = await client.post(
        "/api/chat", json={"message": "classic business outfit under £100"}
    )
    count = len(response.json()["products"])
    assert count > 0
    await client.post("/api/clear")
    metrics = (await client.get("/metrics")).text
    assert "retail_sessions_created_total 1.0" in metrics
    assert "retail_conversations_cleared_total 1.0" in metrics
    assert f"retail_products_returned_total {float(count)}" in metrics
    assert app.state.metrics.http_latency.labels(route="/api/chat")._sum.get() >= 0.03
    assert "classic business" not in metrics and client.cookies.get("retail_session") not in metrics


async def test_default_readiness_and_headers(client):
    result = await client.get("/api/health")
    assert result.json()["status"] == "ready"
    assert result.json()["model_available"] is None
    assert result.headers["cache-control"] == "no-store"
    assert "script-src 'self'" in result.headers["content-security-policy"]
    assert (await client.get("/api/unknown")).status_code == 404


async def test_global_backpressure_does_not_block_other_routes(app, client):
    for _ in range(app.state.config.max_inflight):
        await app.state.capacity.acquire()
    try:
        assert (await client.post("/api/chat", json={"message": "hi"})).status_code == 503
        assert (await client.get("/api/health")).status_code == 200
    finally:
        for _ in range(app.state.config.max_inflight):
            app.state.capacity.release()
