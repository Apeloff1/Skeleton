"""Boundary adapters for promoted memory implementations.

The Prood/Tutolage RAG implementation uses a Chroma-style synchronous
collection API. This module preserves those useful collection/query/filter
semantics behind ``MemoryContract`` without making ChromaDB (or any provider) a
kernel dependency.

``SQLiteCollection`` is a dependency-free persistent implementation of that
same structural collection surface. It is intentionally a backend, not a new
memory primitive: callers still program against ``MemoryContract`` through
``CollectionMemoryAdapter``.
"""

from __future__ import annotations

import asyncio
import heapq
import json
import math
import os
import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence

from skeleton.ai.model_runtime.private_sqlite import (
    PrivateSQLiteHandle, PrivateSQLiteUnavailable, open_private_sqlite,
)
from skeleton.frontier.runtime.memory import (
    lexical_relevance,
    normalize_memory_filters,
    normalize_memory_item,
    normalize_memory_metadata,
)


class CollectionLike(Protocol):
    """Small structural contract matching the promoted RAG collection surface."""

    def add(
        self,
        *,
        documents: Sequence[str],
        metadatas: Sequence[Mapping[str, Any]],
        ids: Sequence[str],
    ) -> Any:
        ...

    def query(
        self,
        *,
        query_texts: Sequence[str],
        n_results: int,
        where: Mapping[str, Any] | None = None,
    ) -> Mapping[str, Any]:
        ...

    def delete(
        self,
        *,
        ids: Sequence[str] | None = None,
        where: Mapping[str, Any] | None = None,
    ) -> Any:
        ...


class MemoryStoreCorruptionError(ValueError):
    """Raised when persisted memory cannot safely cross the memory boundary."""


def _reject_json_constant(value: str) -> object:
    raise ValueError(f"non-finite JSON numeric constant: {value}")


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON object key: {key}")
        result[key] = value
    return result


def _first_row(value: Any) -> list[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    if not value:
        return []
    first = value[0]
    if isinstance(first, Sequence) and not isinstance(first, (str, bytes)):
        return list(first)
    return list(value)


@dataclass(slots=True)
class CollectionMemoryAdapter:
    """Adapt a Chroma-like collection to ``MemoryContract``.

    All input normalization is shared with ``InMemoryStore``: ids are
    non-empty, content comes from content/text/document, metadata and filters
    stay inside the strict finite-JSON domain, and conflicting top-level/nested
    filter fields fail closed. Provider results are normalized again on ingress
    so an external backend cannot silently widen the canonical memory contract.
    """

    collection: CollectionLike

    async def put(self, item: Mapping[str, Any]) -> str:
        item_id, content, metadata = normalize_memory_item(item)
        await asyncio.to_thread(
            self.collection.add,
            documents=[content],
            metadatas=[metadata],
            ids=[item_id],
        )
        return item_id

    async def search(
        self,
        query: str,
        *,
        limit: int = 10,
        filters: Mapping[str, Any] | None = None,
    ) -> Sequence[Mapping[str, Any]]:
        if limit < 1:
            return []
        where = normalize_memory_filters(filters)
        raw = await asyncio.to_thread(
            self.collection.query,
            query_texts=[query],
            n_results=limit,
            where=where or None,
        )
        if not isinstance(raw, Mapping):
            raise TypeError("collection query result must be a mapping")
        documents = _first_row(raw.get("documents", []))
        metadatas = _first_row(raw.get("metadatas", []))
        ids = _first_row(raw.get("ids", []))
        distances = _first_row(raw.get("distances", []))

        hits: list[Mapping[str, Any]] = []
        for index, document in enumerate(documents[:limit]):
            if not isinstance(document, str):
                raise TypeError("collection result document must be a string")
            hit: dict[str, Any] = {"content": document}
            if index < len(ids):
                if not isinstance(ids[index], str):
                    raise TypeError("collection result memory id must be a string")
                item_id = ids[index].strip()
                if not item_id:
                    raise ValueError("collection result memory id must not be empty")
                if item_id != ids[index]:
                    raise ValueError("collection result memory id must be normalized")
                hit["id"] = item_id
            if index < len(metadatas):
                raw_metadata = metadatas[index] or {}
                if not isinstance(raw_metadata, Mapping):
                    raise TypeError("collection result metadata must be a mapping")
                hit["metadata"] = normalize_memory_metadata(raw_metadata)
            if index < len(distances):
                try:
                    distance = float(distances[index])
                except (TypeError, ValueError) as exc:
                    raise ValueError("collection result distance must be numeric") from exc
                if not math.isfinite(distance):
                    raise ValueError("collection result distance must be finite")
                relevance = 1.0 - distance
                hit["relevance"] = max(0.0, min(1.0, relevance))
            hits.append(hit)
        return hits

    async def delete(self, item_id: str) -> None:
        normalized = str(item_id).strip()
        if not normalized:
            raise ValueError("memory id must not be empty")
        await asyncio.to_thread(self.collection.delete, ids=[normalized])


MAX_DATABASE_ROWS = 500_000
MAX_DATABASE_LOGICAL_BYTES = 512 * 1024 * 1024


class SQLiteCollection:
    """Persistent stdlib collection backend for contract conformance.

    The class intentionally exposes the same tiny synchronous collection shape
    consumed by ``CollectionMemoryAdapter``. It provides deterministic lexical
    retrieval, exact metadata filtering, namespace isolation and idempotent
    upsert behavior without becoming the canonical retrieval engine. Persisted
    rows are decoded fail-closed; malformed identity, document or metadata never
    becomes a memory hit or participates in a filtered mutation.
    """

    def __init__(
        self,
        path: str | Path = ":memory:",
        *,
        namespace: str = "frontier_memory",
        capacity: int = 10_000,
        max_namespace_bytes: int = 64 * 1024 * 1024,
        _private_handle: PrivateSQLiteHandle | None = None,
    ) -> None:
        if not isinstance(namespace, str):
            raise TypeError("namespace must be a string")
        normalized_namespace = namespace.strip()
        if not normalized_namespace:
            raise ValueError("namespace must not be empty")
        if normalized_namespace != namespace:
            raise ValueError("namespace must be normalized")

        if len(namespace) > 128:
            raise ValueError("namespace must not exceed 128 characters")
        if type(capacity) is not int or not 1 <= capacity <= 100_000:
            raise ValueError("capacity must be in [1, 100000]")
        if type(max_namespace_bytes) is not int or not 1 <= max_namespace_bytes <= 256 * 1024 * 1024:
            raise ValueError("invalid namespace byte budget")
        self.namespace = namespace
        self.capacity = capacity
        self.max_namespace_bytes = max_namespace_bytes
        self._private_handle = _private_handle
        self._owner_pid = os.getpid()
        self._lock = threading.RLock()
        if _private_handle is None:
            self._connection = sqlite3.connect(
                str(path), check_same_thread=False, timeout=5.0,
            )
        else:
            if type(_private_handle) is not PrivateSQLiteHandle or str(path) != ":memory:":
                raise ValueError("exclusive private SQLite handle required")
            _private_handle.assert_current()
            self._connection = _private_handle.connection
            # The private opener defaults to autocommit; this adapter uses
            # explicit write transactions, including cross-thread calls.
            self._connection.isolation_level = "DEFERRED"
        self._connection.row_factory = sqlite3.Row
        with self._lock:
            self._connection.execute("PRAGMA foreign_keys = ON")
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS frontier_memory_items (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    namespace TEXT NOT NULL,
                    item_id TEXT NOT NULL,
                    document TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    UNIQUE(namespace, item_id)
                )
                """
            )
            self._connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_frontier_memory_namespace_seq
                ON frontier_memory_items(namespace, seq DESC)
                """
            )
            self._connection.commit()

    @classmethod
    def from_private_database(
        cls, directory: str | Path, *, create: bool = False,
        filename: str = "frontier-memory.db",
        max_database_bytes: int = 64 << 20,
        namespace: str = "frontier_memory", capacity: int = 10_000,
        max_namespace_bytes: int = 64 * 1024 * 1024,
    ) -> "SQLiteCollection":
        """Explicit private POSIX storage; no silent bootstrap on reopen.

        This class owns the handle. Its RLock serializes every connection use
        including CollectionMemoryAdapter's asyncio.to_thread calls. The
        legacy path constructor is retained for compatibility, not certified
        private storage. This does not protect against malicious same-UID races.
        """
        handle = open_private_sqlite(
            directory, filename=filename, create=create,
            max_database_bytes=max_database_bytes, check_same_thread=False,
        )
        try:
            return cls(namespace=namespace, capacity=capacity,
                       max_namespace_bytes=max_namespace_bytes, _private_handle=handle)
        except BaseException:
            handle.close()
            raise

    def _require_owner_process(self) -> None:
        # Reject before acquiring an inherited thread lock after fork.
        if os.getpid() != self._owner_pid:
            raise PrivateSQLiteUnavailable("inherited memory collection requires reopening")

    def _assert_private_custody(self) -> None:
        if self._private_handle is not None:
            self._private_handle.assert_current()

    @staticmethod
    def _metadata_json(metadata: Mapping[str, Any]) -> str:
        normalized = normalize_memory_metadata(metadata)
        try:
            return json.dumps(
                normalized,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            )
        except (TypeError, ValueError) as exc:
            raise TypeError("memory metadata must be JSON serializable") from exc

    @staticmethod
    def _metadata_from_json(value: object) -> Mapping[str, Any]:
        if not isinstance(value, str):
            raise MemoryStoreCorruptionError(
                "memory metadata must be stored as JSON text"
            )
        try:
            metadata = json.loads(
                value,
                parse_constant=_reject_json_constant,
                object_pairs_hook=_unique_json_object,
            )
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            raise MemoryStoreCorruptionError(
                "memory metadata is not valid strict JSON"
            ) from exc
        if not isinstance(metadata, dict):
            raise MemoryStoreCorruptionError(
                "memory metadata must decode to a JSON object"
            )
        try:
            return normalize_memory_metadata(metadata)
        except (TypeError, ValueError) as exc:
            raise MemoryStoreCorruptionError(
                "memory metadata violates the canonical JSON boundary"
            ) from exc

    @staticmethod
    def _matches(
        metadata: Mapping[str, Any],
        where: Mapping[str, Any] | None,
    ) -> bool:
        return not where or all(metadata.get(key) == value for key, value in where.items())

    @staticmethod
    def _normalized_ids(ids: Sequence[str] | None) -> set[str] | None:
        if ids is None:
            return None
        if isinstance(ids, (str, bytes)) or len(ids) > 100_000:
            raise ValueError("memory identifier inventory exceeds budget")
        normalized: set[str] = set()
        for item_id in ids:
            if not isinstance(item_id, str):
                raise TypeError("memory id must be a string")
            value = item_id.strip()
            if not value or len(value) > 256 or value != item_id:
                raise ValueError("invalid normalized memory id")
            normalized.add(value)
        return normalized

    @staticmethod
    def _row_identity(row: sqlite3.Row) -> tuple[int, str, str]:
        seq = row["seq"]
        if not isinstance(seq, int) or isinstance(seq, bool) or seq < 1:
            raise MemoryStoreCorruptionError(
                "memory sequence must be a positive integer"
            )
        item_id = row["item_id"]
        if not isinstance(item_id, str) or not item_id.strip():
            raise MemoryStoreCorruptionError(
                "memory item id must be stored as a non-empty string"
            )
        if item_id != item_id.strip():
            raise MemoryStoreCorruptionError(
                "memory item id must be stored in normalized form"
            )
        document = row["document"]
        if not isinstance(document, str):
            raise MemoryStoreCorruptionError(
                "memory document must be stored as text"
            )
        return seq, item_id, document

    def _decoded_row(
        self,
        row: sqlite3.Row,
    ) -> tuple[int, str, str, Mapping[str, Any]]:
        seq, item_id, document = self._row_identity(row)
        metadata = self._metadata_from_json(row["metadata_json"])
        return seq, item_id, document, metadata

    def _assert_namespace_budget(self) -> None:
        count, size = self._connection.execute(
            """
            SELECT COUNT(*), COALESCE(SUM(
                length(CAST(item_id AS BLOB)) +
                length(CAST(document AS BLOB)) +
                length(CAST(metadata_json AS BLOB))
            ), 0)
            FROM frontier_memory_items WHERE namespace = ?
            """,
            (self.namespace,),
        ).fetchone()
        if count > self.capacity or size > self.max_namespace_bytes:
            raise OverflowError("memory namespace capacity exceeded")

    def _assert_database_budget(self) -> None:
        # Logical row bytes; not a physical SQLite/WAL disk reservation.
        count, size = self._connection.execute(
            """SELECT COUNT(*), COALESCE(SUM(
                length(CAST(namespace AS BLOB)) + length(CAST(item_id AS BLOB)) +
                length(CAST(document AS BLOB)) + length(CAST(metadata_json AS BLOB))
            ), 0) FROM frontier_memory_items"""
        ).fetchone()
        if count > MAX_DATABASE_ROWS or size > MAX_DATABASE_LOGICAL_BYTES:
            raise OverflowError("memory database capacity exceeded")

    def _rows(self) -> list[sqlite3.Row]:
        self._require_owner_process()
        with self._lock:
            self._assert_private_custody()
            result: list[sqlite3.Row] = []
            size = 0
            cursor = self._connection.execute(
                """
                SELECT seq, item_id, document, metadata_json
                FROM frontier_memory_items
                WHERE namespace = ?
                ORDER BY seq DESC
                LIMIT ?
                """,
                (self.namespace, self.capacity + 1),
            )
            try:
                for row in cursor:
                    if len(result) >= self.capacity:
                        raise OverflowError("memory namespace capacity exceeded")
                    for key in ("item_id", "document", "metadata_json"):
                        value = row[key]
                        if isinstance(value, str):
                            size += len(value.encode("utf-8"))
                        elif isinstance(value, bytes):
                            size += len(value)
                        if size > self.max_namespace_bytes:
                            raise OverflowError("memory namespace byte budget exceeded")
                    result.append(row)
            finally:
                cursor.close()
            return result

    def add(
        self,
        *,
        documents: Sequence[str],
        metadatas: Sequence[Mapping[str, Any]],
        ids: Sequence[str],
    ) -> None:
        self._require_owner_process()
        if not (len(documents) == len(metadatas) == len(ids)):
            raise ValueError("documents, metadatas and ids must have equal lengths")

        if len(ids) > self.capacity:
            raise OverflowError("memory batch exceeds capacity")
        rows: list[tuple[str, str, str, str]] = []
        batch_bytes = 0
        seen_ids: set[str] = set()
        for document, metadata, item_id in zip(documents, metadatas, ids):
            if not isinstance(item_id, str):
                raise TypeError("memory id must be a string")
            normalized_id = item_id.strip()
            if not normalized_id or len(normalized_id) > 256 or normalized_id != item_id:
                raise ValueError("invalid normalized memory id")
            if normalized_id in seen_ids:
                raise ValueError("duplicate memory id in batch")
            seen_ids.add(normalized_id)
            if not isinstance(document, str):
                raise TypeError("memory document must be a string")
            if not isinstance(metadata, Mapping):
                raise TypeError("metadata must be a mapping")
            metadata_json = self._metadata_json(metadata)
            batch_bytes += sum(len(value.encode("utf-8")) for value in (normalized_id, document, metadata_json))
            if batch_bytes > self.max_namespace_bytes:
                raise OverflowError("memory batch exceeds byte budget")
            rows.append((self.namespace, normalized_id, document, metadata_json))

        # Cross-process serialization: the write and its quota check share
        # one transaction. A failed quota check rolls back every batch row.
        with self._lock, self._connection:
            self._assert_private_custody()
            self._connection.execute("BEGIN IMMEDIATE")
            self._connection.executemany(
                """
                INSERT INTO frontier_memory_items(
                    namespace, item_id, document, metadata_json
                ) VALUES (?, ?, ?, ?)
                ON CONFLICT(namespace, item_id) DO UPDATE SET
                    document = excluded.document,
                    metadata_json = excluded.metadata_json
                """,
                rows,
            )
            self._assert_namespace_budget()
            self._assert_database_budget()
            self._assert_private_custody()

    def query(
        self,
        *,
        query_texts: Sequence[str],
        n_results: int,
        where: Mapping[str, Any] | None = None,
    ) -> Mapping[str, Any]:
        if n_results < 1:
            return {
                "documents": [[]],
                "metadatas": [[]],
                "ids": [[]],
                "distances": [[]],
            }

        normalized_where = normalize_memory_filters(where)
        query = str(query_texts[0]) if query_texts else ""
        ranked: list[tuple[float, int, str, str, Mapping[str, Any]]] = []
        n_results = min(n_results, self.capacity)
        for row in self._rows():
            seq, item_id, document, metadata = self._decoded_row(row)
            if not self._matches(metadata, normalized_where):
                continue
            score = lexical_relevance(document, query)
            if query.strip() and score <= 0.0:
                continue
            candidate = (score, seq, item_id, document, metadata)
            if len(ranked) < n_results:
                heapq.heappush(ranked, candidate)
            elif candidate[:2] > ranked[0][:2]:
                heapq.heapreplace(ranked, candidate)

        selected = sorted(ranked, key=lambda candidate: (candidate[0], candidate[1]), reverse=True)
        return {
            "documents": [[candidate[3] for candidate in selected]],
            "metadatas": [[candidate[4] for candidate in selected]],
            "ids": [[candidate[2] for candidate in selected]],
            "distances": [[1.0 - candidate[0] for candidate in selected]],
        }

    def get(
        self,
        *,
        ids: Sequence[str] | None = None,
        where: Mapping[str, Any] | None = None,
    ) -> Mapping[str, Any]:
        wanted = self._normalized_ids(ids)
        normalized_where = normalize_memory_filters(where)
        selected: list[tuple[str, str, Mapping[str, Any]]] = []
        for row in self._rows():
            raw_id = row["item_id"]
            if wanted is not None and raw_id not in wanted:
                continue
            _, item_id, document, metadata = self._decoded_row(row)
            if not self._matches(metadata, normalized_where):
                continue
            selected.append((item_id, document, metadata))
        return {
            "documents": [candidate[1] for candidate in selected],
            "metadatas": [candidate[2] for candidate in selected],
            "ids": [candidate[0] for candidate in selected],
        }

    def delete(
        self,
        *,
        ids: Sequence[str] | None = None,
        where: Mapping[str, Any] | None = None,
    ) -> None:
        self._require_owner_process()
        wanted = self._normalized_ids(ids)

        # Exact or full deletion is also the repair path for corrupt rows and
        # therefore deliberately does not require row deserialization.
        if where is None:
            with self._lock, self._connection:
                self._assert_private_custody()
                self._connection.execute("BEGIN IMMEDIATE")
                if wanted is None:
                    self._connection.execute(
                        "DELETE FROM frontier_memory_items WHERE namespace = ?",
                        (self.namespace,),
                    )
                elif wanted:
                    self._connection.executemany(
                        """
                        DELETE FROM frontier_memory_items
                        WHERE namespace = ? AND item_id = ?
                        """,
                        [(self.namespace, item_id) for item_id in wanted],
                    )
                self._assert_private_custody()
            return

        normalized_where = normalize_memory_filters(where)
        # Hold the database write reservation across selection and deletion.
        # A second process cannot change a matched row between these phases.
        with self._lock, self._connection:
            self._assert_private_custody()
            self._connection.execute("BEGIN IMMEDIATE")
            targets: list[str] = []
            for row in self._rows():
                raw_id = row["item_id"]
                if wanted is not None and raw_id not in wanted:
                    continue
                _, item_id, _, metadata = self._decoded_row(row)
                if not self._matches(metadata, normalized_where):
                    continue
                targets.append(item_id)

            if targets:
                self._connection.executemany(
                    """
                    DELETE FROM frontier_memory_items
                    WHERE namespace = ? AND item_id = ?
                    """,
                    [(self.namespace, item_id) for item_id in targets],
                )
            self._assert_private_custody()

    def count(self) -> int:
        self._require_owner_process()
        with self._lock:
            self._assert_private_custody()
            row = self._connection.execute(
                """
                SELECT COUNT(*)
                FROM frontier_memory_items
                WHERE namespace = ?
                """,
                (self.namespace,),
            ).fetchone()
            return int(row[0])

    def close(self) -> None:
        self._require_owner_process()
        with self._lock:
            if self._private_handle is not None:
                self._private_handle.close()
            else:
                self._connection.close()

    def __enter__(self) -> "SQLiteCollection":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()
