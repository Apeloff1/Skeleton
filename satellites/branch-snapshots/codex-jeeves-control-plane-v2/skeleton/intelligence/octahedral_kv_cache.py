"""Octahedral KV cache — structured attention cache with octahedral eviction.

Provides a key-value cache for transformer attention with a geometric
eviction policy shaped like an octahedron: keep recent tokens (time axis),
keep diverse semantic clusters (space axis), and keep high-attention
spikes (importance axis). Eviction trims the corners of this 3D shape.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class CacheEntry:
    key: List[float]
    value: List[float]
    token_id: int
    layer: int
    head: int
    at: float = field(default_factory=time.time)
    access_count: int = 1
    last_access: float = field(default_factory=time.time)
    attention_score: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "token_id": self.token_id,
            "layer": self.layer,
            "head": self.head,
            "at": self.at,
            "access_count": self.access_count,
            "last_access": self.last_access,
            "attention_score": round(self.attention_score, 6),
        }


class OctahedralKVCache:
    """KV cache with octahedral eviction: time + diversity + importance."""

    def __init__(self, max_entries: int = 4096, layers: int = 12, heads: int = 8):
        self.max_entries = max_entries
        self.layers = layers
        self.heads = heads
        self._entries: Dict[Tuple[int, int, int], CacheEntry] = {}
        self._sequence: List[Tuple[int, int, int]] = []
        self._hit_count = 0
        self._miss_count = 0

    def _key(self, token_id: int, layer: int, head: int) -> Tuple[int, int, int]:
        return (token_id, layer, head)

    def get(self, token_id: int, layer: int, head: int) -> Optional[CacheEntry]:
        k = self._key(token_id, layer, head)
        entry = self._entries.get(k)
        if entry:
            entry.access_count += 1
            entry.last_access = time.time()
            self._hit_count += 1
            return entry
        self._miss_count += 1
        return None

    def put(self, token_id: int, layer: int, head: int, key: List[float], value: List[float], attention_score: float = 0.0) -> None:
        k = self._key(token_id, layer, head)
        if k in self._entries:
            self._entries[k].key = key
            self._entries[k].value = value
            self._entries[k].attention_score = attention_score
            return
        entry = CacheEntry(key=key, value=value, token_id=token_id, layer=layer, head=head, attention_score=attention_score)
        self._entries[k] = entry
        self._sequence.append(k)
        if len(self._entries) > self.max_entries:
            self._evict()

    def _evict(self) -> None:
        """Evict entries that are worst on the octahedron axes."""
        if not self._entries:
            return
        now = time.time()
        scores: List[Tuple[float, Tuple[int, int, int]]] = []
        for k, e in self._entries.items():
            # Time recency: higher is better (keep recent)
            time_score = (now - e.at)
            # Diversity: keep entries from different layers/heads
            diversity_score = (e.layer + e.head) / max(1, self.layers + self.heads)
            # Importance: keep high-attention entries
            importance_score = -e.attention_score
            # Octahedral distance from ideal (0,0,0) — lower is better
            oct_dist = math.sqrt(time_score ** 2 + diversity_score ** 2 + importance_score ** 2)
            scores.append((oct_dist, k))
        scores.sort(reverse=True)
        to_evict = scores[:max(1, len(scores) // 8)]
        for _, k in to_evict:
            del self._entries[k]
            if k in self._sequence:
                self._sequence.remove(k)

    def stats(self) -> Dict[str, Any]:
        total = self._hit_count + self._miss_count
        return {
            "entries": len(self._entries),
            "max_entries": self.max_entries,
            "hit_rate": round(self._hit_count / max(1, total), 4),
            "miss_rate": round(self._miss_count / max(1, total), 4),
            "layers": self.layers,
            "heads": self.heads,
        }

    def card(self) -> Dict[str, Any]:
        return {"kind": "octahedral-kv-cache-card", **self.stats(), "stored_prose": 0}
