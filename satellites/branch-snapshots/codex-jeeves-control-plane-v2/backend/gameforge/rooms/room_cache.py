from __future__ import annotations
from typing import Any, Dict, Optional
import time
from collections import OrderedDict

class RoomCache:
    """
    Fast, room-level in-memory cache.
    Acts as a high-speed layer on top of the room's 14-database Bookshelf.
    Supports TTL and simple LRU eviction.
    """

    def __init__(self, room_id: str, max_size: int = 1000, default_ttl: int = 300):
        self.room_id = room_id
        self.max_size = max_size
        self.default_ttl = default_ttl
        self._cache: OrderedDict[str, Dict[str, Any]] = OrderedDict()
        self._hits = 0
        self._misses = 0

    def get(self, key: str) -> Optional[Any]:
        if key in self._cache:
            entry = self._cache[key]
            if time.time() < entry["expires_at"]:
                self._cache.move_to_end(key)
                self._hits += 1
                return entry["value"]
            else:
                del self._cache[key]
        self._misses += 1
        return None

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        if len(self._cache) >= self.max_size:
            self._cache.popitem(last=False)  # LRU eviction

        expires_at = time.time() + (ttl or self.default_ttl)
        self._cache[key] = {
            "value": value,
            "expires_at": expires_at
        }
        self._cache.move_to_end(key)

    def invalidate(self, key: str) -> None:
        self._cache.pop(key, None)

    def clear(self) -> None:
        self._cache.clear()

    def stats(self) -> Dict[str, Any]:
        return {
            "room_id": self.room_id,
            "size": len(self._cache),
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": self._hits / (self._hits + self._misses) if (self._hits + self._misses) > 0 else 0
        }
