"""Bounded SQLite browser sessions with cross-worker leases and atomic reset."""

import asyncio
import hashlib
import secrets
import sqlite3
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from src.schemas import SessionState
from src.settings import Settings


class SessionBusy(Exception):
    pass


class SessionExpired(Exception):
    pass


class SessionCapacity(Exception):
    pass


class SessionRateLimited(Exception):
    pass


@dataclass
class Lease:
    session_id: str
    owner: str
    revision: int
    state: SessionState


class SessionStore:
    def __init__(self, config: Settings):
        self.config = config
        self.path = Path(config.database_path)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.path, timeout=5, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA busy_timeout=5000")
        try:
            yield db
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    async def initialize(self) -> None:
        def run():
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self._connect() as db:
                db.execute("PRAGMA journal_mode=WAL")
                db.execute("""CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY, state TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 0,
                    expires REAL NOT NULL, lease TEXT, lease_until REAL NOT NULL DEFAULT 0,
                    rate_window REAL NOT NULL DEFAULT 0, rate_count INTEGER NOT NULL DEFAULT 0)""")

        await asyncio.to_thread(run)

    @staticmethod
    def key(token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()

    async def resolve(self, token: str | None) -> tuple[str, bool]:
        def run():
            now = time.time()
            with self._connect() as db:
                db.execute("BEGIN IMMEDIATE")
                db.execute("DELETE FROM sessions WHERE expires < ? AND lease_until < ?", (now, now))
                if (
                    token
                    and len(token) == 43
                    and db.execute(
                        "SELECT id FROM sessions WHERE id=? AND expires>=?", (self.key(token), now)
                    ).fetchone()
                ):
                    db.commit()
                    return token, False
                if (
                    db.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
                    >= self.config.max_sessions
                ):
                    raise SessionCapacity
                new_token = secrets.token_urlsafe(32)
                db.execute(
                    "INSERT INTO sessions(id,state,expires) VALUES(?,?,?)",
                    (
                        self.key(new_token),
                        SessionState().model_dump_json(),
                        now + self.config.session_ttl_seconds,
                    ),
                )
                db.commit()
                return new_token, True

        return await asyncio.to_thread(run)

    async def read(self, token: str) -> SessionState:
        def run():
            with self._connect() as db:
                row = db.execute(
                    "SELECT state FROM sessions WHERE id=? AND expires>=?",
                    (self.key(token), time.time()),
                ).fetchone()
                if not row:
                    raise SessionExpired
                return SessionState.model_validate_json(row["state"])

        return await asyncio.to_thread(run)

    async def acquire(self, token: str) -> Lease:
        def run():
            now = time.time()
            sid = self.key(token)
            with self._connect() as db:
                db.execute("BEGIN IMMEDIATE")
                row = db.execute(
                    "SELECT * FROM sessions WHERE id=? AND expires>=?", (sid, now)
                ).fetchone()
                if not row:
                    raise SessionExpired
                if row["lease"] and row["lease_until"] > now:
                    raise SessionBusy
                count = row["rate_count"] if row["rate_window"] > now - 60 else 0
                window = row["rate_window"] if count else now
                if count >= self.config.max_session_requests_per_minute:
                    raise SessionRateLimited
                owner = secrets.token_hex(16)
                db.execute(
                    "UPDATE sessions SET lease=?,lease_until=?,rate_window=?,rate_count=?,expires=? WHERE id=?",
                    (
                        owner,
                        now + 180,
                        window,
                        count + 1,
                        now + max(self.config.session_ttl_seconds, 180),
                        sid,
                    ),
                )
                db.commit()
                return Lease(
                    sid, owner, row["revision"], SessionState.model_validate_json(row["state"])
                )

        return await asyncio.to_thread(run)

    async def commit(self, lease: Lease) -> bool:
        # Keep complete exchanges; no raw image data is retained in session state.
        lease.state.history = lease.state.history[-self.config.max_history_messages :]
        payload = lease.state.model_dump_json()

        def run():
            with self._connect() as db:
                result = db.execute(
                    "UPDATE sessions SET state=?,revision=revision+1,lease=NULL,lease_until=0,expires=? WHERE id=? AND lease=? AND revision=?",
                    (
                        payload,
                        time.time() + self.config.session_ttl_seconds,
                        lease.session_id,
                        lease.owner,
                        lease.revision,
                    ),
                )
                return result.rowcount == 1

        return await asyncio.to_thread(run)

    async def release(self, lease: Lease) -> None:
        def run():
            with self._connect() as db:
                db.execute(
                    "UPDATE sessions SET lease=NULL,lease_until=0 WHERE id=? AND lease=?",
                    (lease.session_id, lease.owner),
                )

        await asyncio.to_thread(run)

    async def clear(self, token: str) -> None:
        def run():
            with self._connect() as db:
                result = db.execute(
                    "UPDATE sessions SET state=?,revision=revision+1,lease=NULL,lease_until=0 WHERE id=? AND expires>=?",
                    (SessionState().model_dump_json(), self.key(token), time.time()),
                )
                if result.rowcount != 1:
                    raise SessionExpired

        await asyncio.to_thread(run)

    async def count(self) -> int:
        def run():
            with self._connect() as db:
                return db.execute(
                    "SELECT COUNT(*) FROM sessions WHERE expires>=?", (time.time(),)
                ).fetchone()[0]

        return await asyncio.to_thread(run)
