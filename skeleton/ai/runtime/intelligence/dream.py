"""Dream consolidation — fold a user's episodic clusters into citeable themes.

Themes are indexes, not copies. A dream record names the tag, the episode
ids, and a digest. It does not paste episode bodies into shared retrieval.
"""

from __future__ import annotations

import hashlib
from typing import Any

from skeleton.kernel.primitives import EventBus
from skeleton.memory.types import MemoryChunk


class DreamError(RuntimeError):
    """A dream cycle could not be stored."""


class DreamEngine:
    """Consolidate MAG tag clusters into idempotent RAG theme records."""

    def __init__(self, mag: Any, rag: Any, bus: EventBus | None = None) -> None:
        if not hasattr(mag, "clusters") or not hasattr(mag, "user_id"):
            raise TypeError("mag must expose user_id and clusters()")
        if not hasattr(rag, "add"):
            raise TypeError("rag must expose add()")
        if bus is not None and not isinstance(bus, EventBus):
            raise TypeError("bus must be an EventBus")
        self._mag = mag
        self._rag = rag
        self._bus = bus
        self._dreams: dict[str, dict[str, Any]] = {}
        self._stats = {"cycles": 0, "themes": 0}

    def dream(self, min_cluster: int = 2) -> list[dict[str, Any]]:
        if isinstance(min_cluster, bool) or not isinstance(min_cluster, int) or min_cluster < 2:
            raise ValueError("min_cluster must be an integer >= 2")
        self._stats["cycles"] += 1
        user_id = str(self._mag.user_id).strip()
        if not user_id:
            raise DreamError("mag user_id is required")
        clusters = self._mag.clusters(min_size=min_cluster)
        if not isinstance(clusters, tuple):
            raise DreamError("mag.clusters() must return a tuple")
        current: dict[str, dict[str, Any]] = {}
        for item in clusters:
            if not isinstance(item, tuple) or len(item) != 2:
                raise DreamError("mag cluster entry is invalid")
            tag, episode_ids = item
            if not isinstance(tag, str) or not tag.strip():
                raise DreamError("dream tag is required")
            if not isinstance(episode_ids, tuple) or len(episode_ids) < min_cluster:
                raise DreamError("dream cluster is below the minimum")
            if any(not isinstance(episode_id, str) or not episode_id for episode_id in episode_ids):
                raise DreamError("dream episode ids must be non-empty strings")
            current[tag] = self._store_theme(user_id, tag, episode_ids)
        stale = [tag for tag in self._dreams if tag not in current]
        for tag in stale:
            chunk_id = self._chunk_id(user_id, tag)
            if hasattr(self._rag, "delete"):
                self._rag.delete(chunk_id)
        self._dreams = current
        self._stats["themes"] = len(self._dreams)
        themes = [dict(theme) for _, theme in sorted(self._dreams.items())]
        if self._bus is not None and themes:
            self._bus.emit(
                "memory.dream.cycle",
                {"themes": len(themes), "tags": [theme["tag"] for theme in themes], "user_id": user_id},
            )
        return themes

    def recent_dreams(self, n: int = 10) -> list[dict[str, Any]]:
        if isinstance(n, bool) or not isinstance(n, int) or n < 0:
            raise ValueError("n must be a non-negative integer")
        themes = [dict(theme) for _, theme in sorted(self._dreams.items())]
        return themes[:n]

    def stats(self) -> dict[str, int]:
        return dict(self._stats)

    def _chunk_id(self, user_id: str, tag: str) -> str:
        digest = hashlib.sha256(tag.encode("utf-8")).hexdigest()[:16]
        return f"dream:{user_id}:{digest}"

    def _store_theme(self, user_id: str, tag: str, episode_ids: tuple[str, ...]) -> dict[str, Any]:
        ordered = tuple(sorted(episode_ids))
        joined = "\n".join(ordered)
        digest = hashlib.sha256(joined.encode("utf-8")).hexdigest()
        text = f"dream tag={tag} user={user_id} episodes={len(ordered)} digest={digest}"
        chunk_id = self._chunk_id(user_id, tag)
        chunk = MemoryChunk(
            id=chunk_id,
            text=text,
            metadata={
                "source": "dream",
                "tag": tag,
                "user_id": user_id,
                "episode_ids": list(ordered),
                "digest": digest,
            },
            source_tier="rag",
            confidence=1.0,
        )
        self._rag.add(chunk)
        return {
            "tag": tag,
            "user_id": user_id,
            "episodes": len(ordered),
            "episode_ids": list(ordered),
            "digest": digest,
            "chunk_id": chunk_id,
        }


__all__ = ["DreamEngine", "DreamError"]
