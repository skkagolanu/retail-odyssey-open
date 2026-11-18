import asyncio
import sqlite3
import time

import httpx
import pytest

from src.schemas import Preferences, SessionState, Turn
from src.sessions import (
    SessionBusy,
    SessionCapacity,
    SessionExpired,
    SessionRateLimited,
    SessionStore,
)
from tests.conftest import ORIGIN


async def test_browser_isolation_and_complete_reset(app, client):
    first = await client.post("/api/chat", json={"message": "A classic business outfit under £100"})
    assert first.status_code == 200
    assert first.json()["products"]
    token = client.cookies.get("retail_session")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://localhost:8000", headers=ORIGIN
    ) as other:
        assert (await other.get("/api/history")).status_code == 401
        new = await other.get("/api/session")
        assert (
            "HttpOnly" in new.headers["set-cookie"]
            and "SameSite=strict" in new.headers["set-cookie"]
        )
        assert other.cookies.get("retail_session") != token
        assert new.json()["history"] == []
        assert new.json()["preferences"]["occasion"] is None
    lease = await app.state.store.acquire(token)
    lease.state.wardrobe_context = "A blue shirt"
    assert await app.state.store.commit(lease)
    assert (await client.post("/api/clear")).status_code == 200
    assert await app.state.store.read(token) == SessionState()


async def test_persistence_bounded_history_and_no_raw_token(config):
    store = SessionStore(config)
    await store.initialize()
    token, created = await store.resolve("a" * 43)
    assert created and token != "a" * 43
    lease = await store.acquire(token)
    lease.state.history = [
        Turn(role=role, content=str(i)) for i in range(30) for role in ["user", "assistant"]
    ]
    lease.state.preferences = Preferences(style="classic")
    assert await store.commit(lease)
    reopened = SessionStore(config)
    state = await reopened.read(token)
    assert len(state.history) == 20 and state.history[0].content == "20"
    assert state.preferences.style == "classic"
    with sqlite3.connect(config.database_path) as db:
        assert db.execute("select id from sessions").fetchone()[0] == store.key(token)
        assert token not in str(db.execute("select * from sessions").fetchall())


async def test_cross_worker_lease_clear_and_stale_reply(config):
    first, second = SessionStore(config), SessionStore(config)
    await first.initialize()
    token, _ = await first.resolve(None)
    lease = await first.acquire(token)
    with pytest.raises(SessionBusy):
        await second.acquire(token)
    await second.clear(token)
    lease.state.history.append(Turn(role="assistant", content="stale"))
    assert not await first.commit(lease)
    fresh = await second.acquire(token)
    await first.release(lease)
    with pytest.raises(SessionBusy):
        await first.acquire(token)
    assert await second.commit(fresh)
    assert (await first.read(token)).history == []


async def test_capacity_expiry_and_rate(config):
    config.max_sessions = 1
    config.max_session_requests_per_minute = 1
    store = SessionStore(config)
    await store.initialize()
    token, _ = await store.resolve(None)
    with pytest.raises(SessionCapacity):
        await store.resolve(None)
    lease = await store.acquire(token)
    await store.release(lease)
    with pytest.raises(SessionRateLimited):
        await store.acquire(token)
    with sqlite3.connect(config.database_path) as db:
        db.execute("update sessions set expires=?,lease_until=0", (time.time() - 1,))
    with pytest.raises(SessionExpired):
        await store.read(token)
    replacement, created = await store.resolve(token)
    assert created and replacement != token


async def test_clear_while_http_reply_running_discards_old_state(app, client):
    started, resume = asyncio.Event(), asyncio.Event()
    original = app.state.orchestrator.process_message

    async def blocked(*args, **kwargs):
        started.set()
        await resume.wait()
        return await original(*args, **kwargs)

    app.state.orchestrator.process_message = blocked
    request = asyncio.create_task(client.post("/api/chat", json={"message": "casual outfit"}))
    await started.wait()
    assert (await client.post("/api/chat", json={"message": "another outfit"})).status_code == 409
    assert (await client.post("/api/clear")).status_code == 200
    resume.set()
    assert (await request).status_code == 409
    assert (await client.get("/api/history")).json()["history"] == []


async def test_request_timeout_releases_session_lease(app, client):
    app.state.config.request_timeout_seconds = 0.01
    original = app.state.orchestrator.process_message

    async def slow(*args):
        await asyncio.sleep(0.1)

    app.state.orchestrator.process_message = slow
    assert (await client.post("/api/chat", json={"message": "casual outfit"})).status_code == 504
    app.state.orchestrator.process_message = original
    assert (await client.post("/api/chat", json={"message": "hi"})).status_code == 200


async def test_session_lease_is_visible_to_independent_python_process(config):
    import sys

    store = SessionStore(config)
    await store.initialize()
    token, _ = await store.resolve(None)
    lease = await store.acquire(token)
    code = """
import asyncio,sys
from src.settings import Settings
from src.sessions import SessionStore,SessionBusy
async def main():
    store=SessionStore(Settings(_env_file=None,database_path=sys.argv[1]))
    try:
        await store.acquire(sys.argv[2])
    except SessionBusy:
        print('busy')
    else:
        raise SystemExit('lease was not enforced')
asyncio.run(main())
"""
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        code,
        str(config.database_path),
        token,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()
    assert process.returncode == 0, stderr.decode()
    assert stdout.decode().strip() == "busy"
    await store.release(lease)
