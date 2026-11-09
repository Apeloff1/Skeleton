"""Bounded provider-neutral episodic memory for Jeeves.

Adapted from the strongest idea in the private Prood agent-memory subsystem:
retain episodes, rank recall by relevance/recency/importance, and preserve the
lineage of explicit reflections.  Storage and model invocation are intentionally
left outside this module so the memory primitive can be used by game agents,
Jeeves coding agents, tests, and alternate persistence backends.
"""
from __future__ import annotations

import math
import re
import threading
import time
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Iterable, Sequence


_STOPWORDS = frozenset(
    {
        "a", "an", "and", "are", "as", "at", "be", "but", "by", "for",
        "from", "in", "is", "it", "of", "on", "or", "that", "the", "this",
        "to", "was", "were", "with",
    }
)


def tokenize(text: str) -> frozenset[str]:
    return frozenset(
        token
        for token in re.findall(r"[a-z0-9][a-z0-9_-]*", (text or "").lower())
        if len(token) > 1 and token not in _STOPWORDS
    )


@dataclass(frozen=True)
class MemoryRecord:
    memory_id: str
    agent_id: str
    content: str
    kind: str = "episode"
    importance: float = 0.5
    tags: tuple[str, ...] = field(default_factory=tuple)
    created_at: float = field(default_factory=time.time)
    source_ids: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not self.memory_id.strip() or not self.agent_id.strip():
            raise ValueError("memory_id and agent_id are required")
        if not self.content.strip():
            raise ValueError("memory content cannot be empty")
        if len(self.content) > 16_000:
            raise ValueError("memory content exceeds 16000 characters")
        if not math.isfinite(self.importance) or not 0.0 <= self.importance <= 1.0:
            raise ValueError("importance must be finite and within [0, 1]")
        if not math.isfinite(self.created_at) or self.created_at < 0:
            raise ValueError("created_at must be a non-negative finite timestamp")

    @property
    def keywords(self) -> frozenset[str]:
        return tokenize(self.content) | frozenset(self.tags)


@dataclass(frozen=True)
class RecallResult:
    record: MemoryRecord
    score: float
    overlap: float
    recency: float

    def as_dict(self) -> dict:
        return {
            "memory_id": self.record.memory_id,
            "agent_id": self.record.agent_id,
            "content": self.record.content,
            "kind": self.record.kind,
            "importance": self.record.importance,
            "tags": list(self.record.tags),
            "created_at": self.record.created_at,
            "source_ids": list(self.record.source_ids),
            "score": round(self.score, 8),
            "overlap": round(self.overlap, 8),
            "recency": round(self.recency, 8),
        }


class MemoryBank:
    """Thread-safe bounded episodic bank with deterministic relevance scoring."""

    def __init__(
        self,
        *,
        per_agent_capacity: int = 512,
        recency_half_life_seconds: float = 7 * 24 * 3600,
        reflection_bonus: float = 0.12,
    ) -> None:
        if per_agent_capacity < 1:
            raise ValueError("per_agent_capacity must be >= 1")
        if recency_half_life_seconds <= 0 or not math.isfinite(recency_half_life_seconds):
            raise ValueError("recency_half_life_seconds must be finite and > 0")
        self.per_agent_capacity = int(per_agent_capacity)
        self.recency_half_life_seconds = float(recency_half_life_seconds)
        self.reflection_bonus = float(reflection_bonus)
        self._lock = threading.RLock()
        self._by_agent: dict[str, deque[MemoryRecord]] = defaultdict(
            lambda: deque(maxlen=self.per_agent_capacity)
        )
        self._ids: dict[str, MemoryRecord] = {}

    @staticmethod
    def _normalize_tags(tags: Iterable[str]) -> tuple[str, ...]:
        return tuple(
            dict.fromkeys(
                token
                for raw in tags
                for token in tokenize(str(raw))
            )
        )[:32]

    def remember(
        self,
        agent_id: str,
        content: str,
        *,
        kind: str = "episode",
        importance: float = 0.5,
        tags: Iterable[str] = (),
        source_ids: Sequence[str] = (),
        memory_id: str | None = None,
        created_at: float | None = None,
    ) -> MemoryRecord:
        record = MemoryRecord(
            memory_id=memory_id or uuid.uuid4().hex,
            agent_id=(agent_id or "").strip(),
            content=(content or "").strip(),
            kind=(kind or "episode").strip().lower(),
            importance=float(importance),
            tags=self._normalize_tags(tags),
            source_ids=tuple(dict.fromkeys(str(x).strip() for x in source_ids if str(x).strip())),
            created_at=time.time() if created_at is None else float(created_at),
        )
        with self._lock:
            if record.memory_id in self._ids:
                raise ValueError(f"duplicate memory_id: {record.memory_id}")
            lane = self._by_agent[record.agent_id]
            evicted = lane[0] if len(lane) == lane.maxlen else None
            lane.append(record)
            self._ids[record.memory_id] = record
            if evicted is not None:
                self._ids.pop(evicted.memory_id, None)
        return record

    def get(self, memory_id: str) -> MemoryRecord | None:
        with self._lock:
            return self._ids.get(memory_id)

    def _recency(self, record: MemoryRecord, now: float) -> float:
        age = max(0.0, now - record.created_at)
        return math.pow(0.5, age / self.recency_half_life_seconds)

    def recall(
        self,
        agent_id: str,
        query: str = "",
        *,
        limit: int = 8,
        kind: str | None = None,
        now: float | None = None,
    ) -> list[RecallResult]:
        if limit < 1:
            return []
        now = time.time() if now is None else float(now)
        q = tokenize(query)
        with self._lock:
            pool = list(self._by_agent.get((agent_id or "").strip(), ()))

        out: list[RecallResult] = []
        for record in pool:
            if kind and record.kind != kind:
                continue
            keywords = record.keywords
            if q:
                overlap = len(q & keywords) / len(q)
            else:
                overlap = 0.0
            recency = self._recency(record, now)
            score = overlap * 0.52 + recency * 0.20 + record.importance * 0.28
            if record.kind == "reflection":
                score += self.reflection_bonus
            out.append(RecallResult(record, score, overlap, recency))

        out.sort(
            key=lambda row: (
                row.score,
                row.record.importance,
                row.record.created_at,
                row.record.memory_id,
            ),
            reverse=True,
        )
        return out[:limit]

    def reflection_window(
        self,
        agent_id: str,
        *,
        limit: int = 12,
        exclude_reflections: bool = True,
    ) -> tuple[MemoryRecord, ...]:
        with self._lock:
            pool = list(self._by_agent.get((agent_id or "").strip(), ()))
        if exclude_reflections:
            pool = [record for record in pool if record.kind != "reflection"]
        pool.sort(key=lambda record: (record.created_at, record.memory_id), reverse=True)
        return tuple(reversed(pool[: max(0, limit)]))

    def remember_reflection(
        self,
        agent_id: str,
        insight: str,
        source_ids: Sequence[str],
        *,
        importance: float = 0.9,
        tags: Iterable[str] = (),
    ) -> MemoryRecord:
        agent_id = (agent_id or "").strip()
        if not agent_id:
            raise ValueError("agent_id is required")
        source_ids = tuple(dict.fromkeys(str(x).strip() for x in source_ids if str(x).strip()))
        if not source_ids:
            raise ValueError("reflection requires at least one source memory")
        with self._lock:
            missing = [source_id for source_id in source_ids if source_id not in self._ids]
            wrong_agent = [
                source_id
                for source_id in source_ids
                if source_id in self._ids and self._ids[source_id].agent_id != agent_id
            ]
        if missing:
            raise ValueError(f"unknown reflection source ids: {', '.join(missing[:5])}")
        if wrong_agent:
            raise ValueError("reflection sources must belong to the same agent")
        return self.remember(
            agent_id,
            insight,
            kind="reflection",
            importance=importance,
            tags=("reflection", *tuple(tags)),
            source_ids=source_ids,
        )

    def forget(self, agent_id: str) -> int:
        agent_id = (agent_id or "").strip()
        with self._lock:
            lane = self._by_agent.pop(agent_id, None)
            if lane is None:
                return 0
            records = list(lane)
            for record in records:
                self._ids.pop(record.memory_id, None)
            return len(records)

    def profile(self, agent_id: str) -> dict:
        agent_id = (agent_id or "").strip()
        with self._lock:
            records = list(self._by_agent.get(agent_id, ()))
        by_kind: dict[str, int] = {}
        tag_counts: dict[str, int] = {}
        for record in records:
            by_kind[record.kind] = by_kind.get(record.kind, 0) + 1
            for tag in record.tags:
                tag_counts[tag] = tag_counts.get(tag, 0) + 1
        top_tags = sorted(tag_counts.items(), key=lambda row: (-row[1], row[0]))[:16]
        return {
            "agent_id": agent_id,
            "count": len(records),
            "capacity": self.per_agent_capacity,
            "by_kind": by_kind,
            "top_tags": [{"tag": tag, "count": count} for tag, count in top_tags],
            "reflection_count": by_kind.get("reflection", 0),
        }
