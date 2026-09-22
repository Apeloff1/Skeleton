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
import json
import math
import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence

from skeleton.frontier.memory import (
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
    ) -> None:
        if not isinstance(namespace, str):
            raise TypeError("namespace must be a string")
        normalized_namespace = namespace.strip()
        if not normalized_namespace:
            raise ValueError("namespace must not be empty")
        if normalized_namespace != namespace:
            raise ValueError("namespace must be normalized")

        self.namespace = namespace
        self._connection = sqlite3.connect(
            str(path),
            check_same_thread=False,
            timeout=5.0,
        )
        self._connection.row_factory = sqlite3.Row
        self._lock = threading.RLock()
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
        normalized: set[str] = set()
        for item_id in ids:
            if not isinstance(item_id, str):
                raise TypeError("memory id must be a string")
            value = item_id.strip()
            if not value:
                raise ValueError("memory id must not be empty")
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

    def _rows(self) -> list[sqlite3.Row]:
        with self._lock:
            return list(
                self._connection.execute(
                    """
                    SELECT seq, item_id, document, metadata_json
                    FROM frontier_memory_items
                    WHERE namespace = ?
                    ORDER BY seq DESC
                    """,
                    (self.namespace,),
                )
            )

    def add(
        self,
        *,
        documents: Sequence[str],
        metadatas: Sequence[Mapping[str, Any]],
        ids: Sequence[str],
    ) -> None:
        if not (len(documents) == len(metadatas) == len(ids)):
            raise ValueError("documents, metadatas and ids must have equal lengths")

        rows: list[tuple[str, str, str, str]] = []
        for document, metadata, item_id in zip(documents, metadatas, ids):
            if not isinstance(item_id, str):
                raise TypeError("memory id must be a string")
            normalized_id = item_id.strip()
            if not normalized_id:
                raise ValueError("memory id must not be empty")
            if not isinstance(document, str):
                raise TypeError("memory document must be a string")
            if not isinstance(metadata, Mapping):
                raise TypeError("metadata must be a mapping")
            rows.append(
                (
                    self.namespace,
                    normalized_id,
                    document,
                    self._metadata_json(metadata),
                )
            )

        with self._lock:
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
            self._connection.commit()

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
        for row in self._rows():
            seq, item_id, document, metadata = self._decoded_row(row)
            if not self._matches(metadata, normalized_where):
                continue
            score = lexical_relevance(document, query)
            if query.strip() and score <= 0.0:
                continue
            ranked.append((score, seq, item_id, document, metadata))

        ranked.sort(key=lambda candidate: (candidate[0], candidate[1]), reverse=True)
        selected = ranked[:n_results]
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
        wanted = self._normalized_ids(ids)

        # Exact or full deletion is also the repair path for corrupt rows and
        # therefore deliberately does not require row deserialization.
        if where is None:
            with self._lock:
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
                self._connection.commit()
            return

        normalized_where = normalize_memory_filters(where)
        targets: list[str] = []
        for row in self._rows():
            raw_id = row["item_id"]
            if wanted is not None and raw_id not in wanted:
                continue
            _, item_id, _, metadata = self._decoded_row(row)
            if not self._matches(metadata, normalized_where):
                continue
            targets.append(item_id)

        if not targets:
            return
        with self._lock:
            self._connection.executemany(
                """
                DELETE FROM frontier_memory_items
                WHERE namespace = ? AND item_id = ?
                """,
                [(self.namespace, item_id) for item_id in targets],
            )
            self._connection.commit()

    def count(self) -> int:
        with self._lock:
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
        with self._lock:
            self._connection.close()

    def __enter__(self) -> "SQLiteCollection":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()
