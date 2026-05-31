"""
cli/cache.py
------------
Lightweight SQLite cache used by the HTTP layer for offline-mode fallback.

When a request fails (network down, server unreachable), `cli.http.client`
serves the last cached body for the same key as a synthetic 200 response.
That is the cache's only job.

Threading: sqlite3 connections are not safe to share across threads when
opened with check_same_thread=False, so writes are serialised through a
single threading.Lock. The async wrappers offload to the default executor
to keep the event loop unblocked.
"""
from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
import threading
import time
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


class CacheDB:
    """Thread-safe SQLite cache with async convenience wrappers."""

    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._path = db_path
        self._lock = threading.Lock()
        self._conn: sqlite3.Connection | None = None
        self._ensure_schema()

    def _connection(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self._path), check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
        return self._conn

    @contextmanager
    def _tx(self) -> Generator[sqlite3.Connection, None, None]:
        with self._lock:
            conn = self._connection()
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    def _ensure_schema(self) -> None:
        with self._tx() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS cache_entries (
                    key       TEXT PRIMARY KEY,
                    payload   TEXT NOT NULL,
                    cached_at REAL NOT NULL,
                    ttl       REAL NOT NULL DEFAULT 0
                )
                """
            )
        log.debug("SQLite schema verified at %s", self._path)

    # ── Synchronous API ─────────────────────────────────────────────────────

    def set(self, key: str, payload: Any, ttl: float = 3600.0) -> None:
        data = json.dumps(payload, default=str)
        with self._tx() as conn:
            conn.execute(
                """
                INSERT INTO cache_entries (key, payload, cached_at, ttl)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    payload   = excluded.payload,
                    cached_at = excluded.cached_at,
                    ttl       = excluded.ttl
                """,
                (key, data, time.time(), ttl),
            )

    def get(self, key: str) -> Any | None:
        with self._lock:
            row = self._connection().execute(
                "SELECT payload, cached_at, ttl FROM cache_entries WHERE key = ?",
                (key,),
            ).fetchone()
        if row is None:
            return None
        if row["ttl"] > 0 and time.time() - row["cached_at"] > row["ttl"]:
            self.delete(key)
            return None
        return json.loads(row["payload"])

    def delete(self, key: str) -> None:
        with self._tx() as conn:
            conn.execute("DELETE FROM cache_entries WHERE key = ?", (key,))

    def close(self) -> None:
        with self._lock:
            if self._conn:
                self._conn.close()
                self._conn = None

    # ── Async wrappers ──────────────────────────────────────────────────────

    async def aset(self, key: str, payload: Any, ttl: float = 3600.0) -> None:
        await asyncio.get_running_loop().run_in_executor(
            None, lambda: self.set(key, payload, ttl)
        )

    async def aget(self, key: str) -> Any | None:
        return await asyncio.get_running_loop().run_in_executor(
            None, lambda: self.get(key)
        )


from cli.settings import settings as _settings  # noqa: E402  — avoid circular import at module top

cache: CacheDB = CacheDB(_settings.db_path)
