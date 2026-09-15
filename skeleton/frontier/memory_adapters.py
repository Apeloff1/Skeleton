"""Boundary adapters for promoted memory implementations.

The Prood/Tutolage RAG implementation uses a Chroma-style synchronous
collection API. This module preserves those useful collection/query semantics
behind ``MemoryContract`` without making ChromaDB (or any provider) a kernel
dependency.

``SQLiteCollection`` is a dependency-free persistent implementation of that
same structural collection surface. It is intentionally a backend, not a new
memory primitive: callers still program against ``MemoryContract`` through
``CollectionMemoryAdapter``.
"""

from __future__ import annotations

import asyncio
import json
import re
import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence
from uuid import uuid4


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


def _first_row(value: Any) -> list[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    if not value:
        return []
    first = value[0]
    if isinstance(first, Sequence) and not isinstance(first, (str, bytes)):
        return list(first)
    return list(value)


def _portable_metadata(item: Mapping[str, Any]) -> dict[str, Any]:
    """Flatten portable item fields into collection metadata.

    ``MemoryContract`` items historically allowed useful filter fields at the
    top level while the Prood/Tutolage RAG service stores filter state as
    collection metadata. Flattening non-content fields here makes both models
    conform without changing the public contract. Conflicts fail closed rather
    than silently selecting one representation.
    """

    raw_metadata = item.get("metadata") or {}
    if not isinstance(raw_metadata, Mapping):
        raise TypeError("memory item metadata must be a mapping")

    metadata = dict(raw_metadata)
    ignored = {"id", "content", "text", "document", "metadata"}
    for key, value in item.items():
        if key in ignored:
            continue
        if key in metadata and metadata[key] != value:
            raise ValueError(f"conflicting memory metadata field: {key}")
        metadata[key] = value
    return metadata


@dataclass(slots=True)
class CollectionMemoryAdapter:
    """Adapt a Chroma-like collection to ``MemoryContract``.

    Input items intentionally use a tiny portable shape: ``id`` is optional,
    content may be supplied as ``content``, ``text`` or ``document``. Explicit
    ``metadata`` and additional top-level fields become filterable collection
    metadata. Search results preserve source ids, metadata and relevance when
    available.
    """

    collection: CollectionLike

    @staticmethod
    def _content(item: Mapping[str, Any]) -> str:
        for key in ("content", "text", "document"):
            value = item.get(key)
            if value is not None:
                text = str(value).strip()
                if text:
                    return text
        raise ValueError("memory item requires non-empty content/text/document")

    async def put(self, item: Mapping[str, Any]) -> str:
        item_id = str(item.get("id") or uuid4())
        metadata = _portable_metadata(item)
        content = self._content(item)
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
        raw = await asyncio.to_thread(
            self.collection.query,
            query_texts=[query],
            n_results=limit,
            where=dict(filters) if filters else None,
        )
        documents = _first_row(raw.get("documents", []))
        metadatas = _first_row(raw.get("metadatas", []))
        ids = _first_row(raw.get("ids", []))
        distances = _first_row(raw.get("distances", []))

        hits: list[Mapping[str, Any]] = []
        for index, document in enumerate(documents[:limit]):
            hit: dict[str, Any] = {"content": document}
            if index < len(ids):
                hit["id"] = ids[index]
            if index < len(metadatas):
                hit["metadata"] = metadatas[index] or {}
            if index < len(distances):
                try:
                    relevance = 1.0 - float(distances[index])
                    hit["relevance"] = max(0.0, min(1.0, relevance))
                except (TypeError, ValueError):
                    pass
            hits.append(hit)
        return hits

    async def delete(self, item_id: str) -> None:
        await asyncio.to_thread(self.collection.delete, ids=[item_id])


class SQLiteCollection:
    """Persistent stdlib collection backend for contract conformance.

    The class intentionally exposes the same tiny synchronous collection shape
    consumed by ``CollectionMemoryAdapter``. It provides deterministic lexical
    retrieval, exact metadata filtering, namespace isolation and idempotent
    upsert behavior without becoming the canonical retrieval engine.
    """

    def __init__(
        self,
        path: str | Path = ":memory:",
        *,
        namespace: str = "frontier_memory",
    ) -> None:
        namespace = namespace.strip()
        if not namespace:
            raise ValueError("namespace must not be empty")

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
        return json.dumps(
            dict(metadata),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )

    @staticmethod
    def _matches(
        metadata: Mapping[str, Any],
        where: Mapping[str, Any] | None,
    ) -> bool:
        return not where or all(metadata.get(key) == value for key, value in where.items())

    @staticmethod
    def _score(document: str, query: str) -> float:
        query = query.casefold().strip()
        if not query:
            return 1.0

        haystack = document.casefold()
        if query in haystack:
            return 1.0

        terms = tuple(dict.fromkeys(re.findall(r"\w+", query)))
        if not terms:
            return 1.0
        return sum(1 for term in terms if term in haystack) / len(terms)

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
            normalized_id = str(item_id).strip()
            if not normalized_id:
                raise ValueError("memory id must not be empty")
            if not isinstance(metadata, Mapping):
                raise TypeError("metadata must be a mapping")
            rows.append(
                (
                    self.namespace,
                    normalized_id,
                    str(document),
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

        query = str(query_texts[0]) if query_texts else ""
        ranked: list[tuple[float, int, str, str, Mapping[str, Any]]] = []
        for row in self._rows():
            metadata = json.loads(row["metadata_json"])
            if not self._matches(metadata, where):
                continue
            score = self._score(row["document"], query)
            if query.strip() and score <= 0.0:
                continue
            ranked.append(
                (
                    score,
                    int(row["seq"]),
                    row["item_id"],
                    row["document"],
                    metadata,
                )
            )

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
        wanted = {str(item_id) for item_id in ids} if ids is not None else None
        selected: list[tuple[str, str, Mapping[str, Any]]] = []
        for row in self._rows():
            metadata = json.loads(row["metadata_json"])
            if wanted is not None and row["item_id"] not in wanted:
                continue
            if not self._matches(metadata, where):
                continue
            selected.append((row["item_id"], row["document"], metadata))
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
        wanted = {str(item_id) for item_id in ids} if ids is not None else None
        targets: list[str] = []
        for row in self._rows():
            metadata = json.loads(row["metadata_json"])
            if wanted is not None and row["item_id"] not in wanted:
                continue
            if not self._matches(metadata, where):
                continue
            targets.append(row["item_id"])

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
