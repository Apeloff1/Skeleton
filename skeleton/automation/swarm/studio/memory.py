"""Project memory on the existing retrieval stores.

Decisions, constraints, and failures are written into the RAG plane and the
multi-agent episodic store. Recall is bounded: ``top_k`` is a small integer,
never a bool, and never an unbounded scan.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from skeleton.memory.core import Chunk, InMemoryTFIDFStore, MAGStore


MAX_TOP_K = 32
KINDS = frozenset({"decision", "constraint", "failure", "artefact"})


def bound_top_k(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("top_k must be an integer")
    if not 1 <= value <= MAX_TOP_K:
        raise ValueError(f"top_k must be between 1 and {MAX_TOP_K}")
    return value


class ProjectMemory:
    """Remember what this build already decided and where it already failed."""

    def __init__(self, project_id: str, *, top_k: int = 5) -> None:
        if not isinstance(project_id, str) or not project_id.strip():
            raise ValueError("project_id is required")
        self.project_id = project_id
        self.top_k = bound_top_k(top_k)
        self._rag = InMemoryTFIDFStore()
        self._mag = MAGStore(project_id)
        self._rows: list[dict[str, Any]] = []

    def remember(self, kind: str, text: str, *, tags: list[str] | None = None) -> str:
        if kind not in KINDS:
            raise ValueError(f"unknown memory kind {kind}")
        if not isinstance(text, str) or not text.strip():
            raise ValueError("memory text is required")
        clean_tags = []
        for tag in tags or []:
            if isinstance(tag, str) and tag.strip():
                clean_tags.append(tag.strip()[:40])
        if kind not in clean_tags:
            clean_tags.append(kind)
        episode_id = f"{self.project_id}-{len(self._rows) + 1}-{uuid4().hex[:8]}"
        body = text.strip()[:2000]
        self._rag.add(
            Chunk(
                text=body,
                chunk_id=episode_id,
                metadata={
                    "kind": kind,
                    "tags": list(clean_tags),
                    "project_id": self.project_id,
                },
            )
        )
        self._mag.record(episode_id, body, tags=clean_tags)
        row = {"id": episode_id, "kind": kind, "text": body, "tags": list(clean_tags)}
        self._rows.append(row)
        return episode_id

    def recall(self, query: str, *, top_k: int | None = None) -> list[dict[str, Any]]:
        limit = self.top_k if top_k is None else bound_top_k(top_k)
        if not isinstance(query, str) or not query.strip():
            return []
        hits = self._rag.query(query, top_k=limit)
        found: list[dict[str, Any]] = []
        for hit in hits:
            meta = hit.chunk.metadata if isinstance(hit.chunk.metadata, dict) else {}
            found.append(
                {
                    "kind": meta.get("kind", ""),
                    "text": hit.chunk.text,
                    "score": hit.score,
                    "tags": list(meta.get("tags") or []),
                }
            )
        return found

    def snapshot(self) -> list[dict[str, Any]]:
        return [dict(row) for row in self._rows]

    def restore(self, rows: list[dict[str, Any]] | None) -> None:
        self._rag = InMemoryTFIDFStore()
        self._mag = MAGStore(self.project_id)
        self._rows = []
        for row in rows or []:
            if not isinstance(row, dict):
                continue
            kind = row.get("kind")
            text = row.get("text")
            tags = row.get("tags") if isinstance(row.get("tags"), list) else []
            if isinstance(kind, str) and isinstance(text, str):
                self.remember(kind, text, tags=[tag for tag in tags if isinstance(tag, str)])
