"""
Skeleton Intelligence — Dream engine for generative memory synthesis

Provides:
- DreamEngine: Offline consolidation of episodic memory into themes
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from skeleton.kernel.events import EventBus


class DreamEngine:
    """Consolidate episodic memory (MAG) into thematic clusters (dreams).

    Runs offline over MAG episodes, groups them by shared tags,
    and writes synthesized theme documents back into RAG.
    """

    def __init__(self, mag: Any, rag: Any, bus: Optional[EventBus] = None):
        self._mag = mag
        self._rag = rag
        self._bus = bus
        self._dreams: List[Dict[str, Any]] = []
        self._stats = {"cycles": 0, "themes": 0}

    def dream(self, min_cluster: int = 2) -> List[Dict[str, Any]]:
        """Run one dream cycle: cluster episodes by tag and synthesize themes."""
        self._stats["cycles"] += 1
        tag_index = getattr(self._mag, "_tag_index", {})
        episodes = getattr(self._mag, "_episodes", {})

        new_dreams: List[Dict[str, Any]] = []
        for tag, episode_ids in tag_index.items():
            if len(episode_ids) < min_cluster:
                continue
            contents = [episodes[eid]["content"] for eid in episode_ids if eid in episodes]
            theme = {
                "tag": tag,
                "episodes": len(contents),
                "summary": f"Theme '{tag}' across {len(contents)} episodes: " + " | ".join(c[:50] for c in contents[:3]),
                "dreamed_at": time.time(),
            }
            new_dreams.append(theme)

            # Write theme back into RAG for retrieval
            try:
                from skeleton.memory.core import Chunk
                self._rag.add(Chunk(text=theme["summary"], chunk_id=f"dream-{tag}", metadata={"source": "dream", "tag": tag}))
            except Exception:
                pass

        self._dreams.extend(new_dreams)
        self._stats["themes"] += len(new_dreams)

        if self._bus and new_dreams:
            self._bus.emit("memory.dream.cycle", {"themes": len(new_dreams), "tags": [d["tag"] for d in new_dreams]})

        return new_dreams

    def recent_dreams(self, n: int = 10) -> List[Dict[str, Any]]:
        return self._dreams[-n:]

    def stats(self) -> Dict[str, Any]:
        return dict(self._stats)
