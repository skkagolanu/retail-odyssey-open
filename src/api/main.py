"""Retail Odyssey Open API, browser-session isolation and same-origin frontend hosting."""

import asyncio
import logging
import time
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from starlette.middleware.trustedhost import TrustedHostMiddleware

from src.agents.group_chat_orchestrator import GroupChatOrchestrator
from src.catalogue import Catalogue
from src.cloud_provider import CloudflareImageProvider, CloudflareProvider
from src.providers import ComfyProvider, OllamaProvider
from src.schemas import ChatRequest
from src.sessions import (
    SessionBusy,
    SessionCapacity,
    SessionExpired,
    SessionRateLimited,
    SessionStore,
)
from src.settings import ROOT, Settings
from src.utils.prometheus_metrics import Metrics

logger = logging.getLogger("retail")
COOKIE = "retail_session"


class BodyLimitMiddleware:
    def __init__(self, app, limit):
        self.app, self.limit = app, limit

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = dict(scope["headers"])
        try:
            declared = int(headers.get(b"content-length", b"0"))
        except ValueError:
            declared = -1
        if declared < 0 or declared > self.limit:
            return await JSONResponse(
                {"detail": "Request body exceeds the upload limit"}, status_code=413
            )(scope, receive, send)
        if scope["method"] in {"POST", "PUT", "PATCH"}:
            body = bytearray()
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    return
                body.extend(message.get("body", b""))
                if len(body) > self.limit:
                    return await JSONResponse(
                        {"detail": "Request body exceeds the upload limit"}, status_code=413
                    )(scope, receive, send)
                if not message.get("more_body", False):
                    break
            first = True

            async def buffered_receive():
                nonlocal first
                if first:
                    first = False
                    return {"type": "http.request", "body": bytes(body), "more_body": False}
                return await receive()

            return await self.app(scope, buffered_receive, send)
        return await self.app(scope, receive, send)


class RequestMetricsMiddleware:
    """Measure through the final ASGI response body, with bounded label cardinality."""

    def __init__(self, app, metrics):
        self.app, self.metrics = app, metrics

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        began, status = time.perf_counter(), 500

        async def tracked_send(message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, tracked_send)
        finally:
            route = getattr(scope.get("route"), "path", "unmatched")
            if route not in {
                "/api/session",
                "/api/history",
                "/api/chat",
                "/api/clear",
                "/api/health",
                "/metrics",
                "/",
            }:
                route = "static_or_unmatched"
            method = (
                scope["method"]
                if scope["method"] in {"GET", "POST", "HEAD", "OPTIONS"}
                else "other"
            )
            self.metrics.http.labels(method=method, route=route, status=str(status)).inc()
            self.metrics.http_latency.labels(route=route).observe(time.perf_counter() - began)


def create_app(
    config: Settings | None = None, transport: httpx.AsyncBaseTransport | None = None
) -> FastAPI:
    config = config or Settings()
    metrics = Metrics()
    store = SessionStore(config)

    @asynccontextmanager
    async def lifespan(application):
        await store.initialize()
        async with httpx.AsyncClient(
            timeout=config.provider_timeout_seconds,
            follow_redirects=False,
            trust_env=False,
            transport=transport,
        ) as client:
            catalogue = await asyncio.to_thread(
                Catalogue, config.catalogue_path, config.allowed_retailers
            )
            model = (
                CloudflareProvider(config, client)
                if config.engine == "cloudflare"
                else OllamaProvider(config, client)
            )
            images = (
                CloudflareImageProvider(config, client)
                if config.engine == "cloudflare"
                else ComfyProvider(config, client)
            )
            application.state.orchestrator = GroupChatOrchestrator(
                config, catalogue, model, images, metrics
            )
            application.state.catalogue, application.state.model, application.state.images = (
                catalogue,
                model,
                images,
            )
            application.state.capacity = asyncio.Semaphore(config.max_inflight)
            yield

    app = FastAPI(title="Retail Odyssey Open", version="2.0.0", lifespan=lifespan)
    app.state.store, app.state.metrics, app.state.config = store, metrics, config
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(config.allowed_origins),
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
        max_age=600,
    )
    app.add_middleware(BodyLimitMiddleware, limit=config.max_body_bytes)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(config.trusted_hosts))

    @app.middleware("http")
    async def request_boundary(request: Request, call_next):
        if (
            request.method == "POST"
            and request.headers.get("origin", "") not in config.allowed_origins
        ):
            response = JSONResponse(
                {"detail": "A configured same-origin request is required"}, status_code=403
            )
        else:
            response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'"
        )
        return response

    @app.exception_handler(SessionCapacity)
    async def capacity_error(request, error):
        return JSONResponse(
            {"detail": "Session capacity reached; try again later"},
            status_code=503,
            headers={"Retry-After": "60"},
        )

    @app.exception_handler(SessionExpired)
    async def expired_error(request, error):
        return JSONResponse(
            {"detail": "Session expired; reload to start a new one"}, status_code=401
        )

    @app.exception_handler(SessionBusy)
    async def busy_error(request, error):
        return JSONResponse(
            {"detail": "A reply is already running for this conversation"}, status_code=409
        )

    @app.exception_handler(SessionRateLimited)
    async def rate_error(request, error):
        return JSONResponse(
            {"detail": "Conversation rate limit reached; try again shortly"},
            status_code=429,
            headers={"Retry-After": "60"},
        )

    async def session(request: Request, response: Response) -> str:
        token, created = await store.resolve(request.cookies.get(COOKIE))
        if created:
            metrics.sessions_created.inc()
        response.set_cookie(
            COOKIE,
            token,
            max_age=config.session_ttl_seconds,
            httponly=True,
            secure=config.secure_cookies,
            samesite="strict",
            path="/api",
        )
        return token

    def existing(request: Request) -> str:
        token = request.cookies.get(COOKIE)
        if not token or len(token) != 43:
            raise SessionExpired
        return token

    @app.get("/api/session")
    async def get_session(request: Request, response: Response):
        token = await session(request, response)
        state = await store.read(token)
        return dict(
            history=[turn.model_dump() for turn in state.history],
            preferences=state.preferences.model_dump(),
            history_limit=config.max_history_messages,
            ttl_seconds=config.session_ttl_seconds,
            catalogue=app.state.catalogue.info(),
        )

    @app.get("/api/history")
    async def get_history(request: Request):
        state = await store.read(existing(request))
        return dict(
            history=[turn.model_dump() for turn in state.history],
            preferences=state.preferences.model_dump(),
        )

    @app.post("/api/clear")
    async def clear_history(request: Request):
        await store.clear(existing(request))
        metrics.cleared.inc()
        return dict(history=[], preferences={}, status="cleared")

    @app.post("/api/chat")
    async def chat(payload: ChatRequest, request: Request):
        if app.state.capacity.locked():
            raise HTTPException(
                503, "The assistant is busy; try again shortly", headers={"Retry-After": "5"}
            )
        async with app.state.capacity:
            lease = await store.acquire(existing(request))
            try:
                async with asyncio.timeout(config.request_timeout_seconds):
                    result = await app.state.orchestrator.process_message(
                        payload.message, lease.state, payload.image
                    )
                if not await store.commit(lease):
                    raise HTTPException(
                        409, "Conversation was reset while this reply was running; reply discarded"
                    )
                metrics.products.inc(len(result["products"]))
                return result
            except ValueError as error:
                raise HTTPException(422, str(error)) from error
            except TimeoutError as error:
                raise HTTPException(
                    504,
                    "The inference time budget expired; try again later or use catalogue mode",
                ) from error
            finally:
                await store.release(lease)

    @app.get("/api/health")
    async def health():
        model_available = (
            await app.state.model.available() if config.engine != "catalogue" else None
        )
        return dict(
            status="ready" if config.engine == "catalogue" or model_available else "degraded",
            release="open-v2",
            engine=config.engine,
            catalogue=app.state.catalogue.info(),
            model_available=model_available,
            model_name=(
                config.cloudflare_model if config.engine == "cloudflare" else config.ollama_model
            )
            if config.engine != "catalogue"
            else None,
            image_generation_configured=app.state.images.configured,
        )

    @app.get("/metrics")
    async def prometheus():
        metrics.active.set(await store.count())
        return Response(generate_latest(metrics.registry), media_type=CONTENT_TYPE_LATEST)

    frontend = ROOT / "frontend/dist"

    @app.get("/{path:path}", include_in_schema=False)
    async def frontend_file(path: str):
        if path.startswith(("api/", "metrics")):
            raise HTTPException(404, "Not found")
        file = (frontend / path).resolve()
        if frontend.resolve() not in file.parents and file != frontend.resolve():
            raise HTTPException(404, "Not found")
        if file.is_file():
            return FileResponse(file)
        if not path or path == "index.html":
            index = frontend / "index.html"
            if index.is_file():
                return FileResponse(index)
        raise HTTPException(404, "Build the frontend or use the Vite development server")

    app.add_middleware(RequestMetricsMiddleware, metrics=metrics)
    return app


app = create_app()
