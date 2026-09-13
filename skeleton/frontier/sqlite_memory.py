"""Persistent, namespaced MemoryContract using Python's SQLite driver.

    async with SQLiteMemoryStore("memory.sqlite3", namespace="learner-1") as store:
        await store.put({"text": "A retained observation"})

Database operations run on worker threads. Writes use BEGIN IMMEDIATE so the
capacity check and upsert are atomic across processes. Cancellation stops the
waiter; a transaction already running in a worker may still commit.
"""
from __future__ import annotations

import asyncio
import json
import sqlite3
from pathlib import Path
from threading import RLock
from typing import Any, Callable, Mapping, TypeVar
from uuid import uuid4

from skeleton.frontier.execution import positive_int
from skeleton.frontier.payloads import json_snapshot, memory_payload

T = TypeVar("T")


class SQLiteMemoryStore:
    def __init__(self, path: str | Path, *, namespace: str = "default",
                 capacity: int = 10_000, max_payload_bytes: int = 1_048_576) -> None:
        if not isinstance(namespace, str) or not namespace.strip() or len(namespace) > 128:
            raise ValueError("namespace must contain 1 to 128 characters")
        self.namespace = namespace
        self.capacity = positive_int("capacity", capacity)
        self.max_payload_bytes = positive_int("max_payload_bytes", max_payload_bytes)
        self._lock = RLock()
        self._closed = False
        self._connection = sqlite3.connect(str(path), timeout=5, check_same_thread=False)
        try:
            self._connection.execute("PRAGMA journal_mode=WAL")
            self._connection.execute("PRAGMA synchronous=FULL")
            with self._connection:
                self._connection.execute("""
                    CREATE TABLE IF NOT EXISTS frontier_memory (
                        namespace TEXT NOT NULL,
                        item_id TEXT NOT NULL,
                        payload TEXT NOT NULL,
                        search_text TEXT NOT NULL,
                        PRIMARY KEY (namespace, item_id)
                    )
                """)
        except BaseException:
            self._connection.close()
            raise

    async def _run(self, operation: Callable[[], T]) -> T:
        def guarded() -> T:
            with self._lock:
                if self._closed:
                    raise RuntimeError("memory store is closed")
                return operation()

        return await asyncio.to_thread(guarded)

    async def put(self, item: Mapping[str, Any]) -> str:
        item_id = item.get("id", str(uuid4()))
        payload = memory_payload(item, item_id, self.max_payload_bytes)
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
        search_text = repr(payload).casefold()

        def write() -> str:
            with self._connection:
                self._connection.execute("BEGIN IMMEDIATE")
                exists = self._connection.execute(
                    "SELECT 1 FROM frontier_memory WHERE namespace=? AND item_id=?",
                    (self.namespace, item_id),
                ).fetchone()
                if not exists:
                    count = self._connection.execute(
                        "SELECT COUNT(*) FROM frontier_memory WHERE namespace=?", (self.namespace,)
                    ).fetchone()[0]
                    if count >= self.capacity:
                        raise OverflowError("memory store capacity reached")
                self._connection.execute("""
                    INSERT INTO frontier_memory(namespace, item_id, payload, search_text)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(namespace, item_id) DO UPDATE SET
                        payload=excluded.payload, search_text=excluded.search_text
                """, (self.namespace, item_id, encoded, search_text))
            return item_id

        return await self._run(write)

    async def search(self, query: str, *, limit: int = 10,
                     filters: Mapping[str, Any] | None = None) -> list[Mapping[str, Any]]:
        positive_int("limit", limit, minimum=0)
        if not isinstance(query, str):
            raise ValueError("query must be a string")
        needle = query.casefold().strip()
        conditions = json_snapshot(dict(filters or {}), max_bytes=self.max_payload_bytes)

        def read() -> list[Mapping[str, Any]]:
            if limit == 0:
                return []
            hits = []
            cursor = self._connection.execute("""
                SELECT payload FROM frontier_memory
                WHERE namespace=? AND instr(search_text, ?) > 0 ORDER BY item_id
            """, (self.namespace, needle))
            try:
                for (encoded,) in cursor:
                    payload = json.loads(encoded)
                    if all(payload.get(key) == value for key, value in conditions.items()):
                        hits.append(payload)
                        if len(hits) >= limit:
                            break
            finally:
                cursor.close()
            return hits

        return await self._run(read)

    async def delete(self, item_id: str) -> None:
        def remove() -> None:
            with self._connection:
                self._connection.execute(
                    "DELETE FROM frontier_memory WHERE namespace=? AND item_id=?",
                    (self.namespace, item_id),
                )

        await self._run(remove)

    async def count(self) -> int:
        return await self._run(lambda: self._connection.execute(
            "SELECT COUNT(*) FROM frontier_memory WHERE namespace=?", (self.namespace,)
        ).fetchone()[0])

    async def aclose(self) -> None:
        def close() -> None:
            with self._lock:
                if not self._closed:
                    self._connection.close()
                    self._closed = True

        await asyncio.to_thread(close)

    async def __aenter__(self) -> SQLiteMemoryStore:
        if self._closed:
            raise RuntimeError("memory store is closed")
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        await self.aclose()
