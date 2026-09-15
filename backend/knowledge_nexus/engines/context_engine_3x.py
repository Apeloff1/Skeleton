#!/usr/bin/env python3
"""
Context Engine 3×
Buffered Active Context + Redundant Context Memory + Meta-Context + Real-time Noise Filter
"""

from collections import deque
from dataclasses import dataclass
from itertools import islice
import time
from typing import Any, Deque, Dict, List


_NOISE_INDICATORS = ("filler", "irrelevant", "low value", "contradictory")


@dataclass
class ContextItem:
    content: str
    timestamp: float
    source: str
    importance: float = 0.5
    noise_score: float = 0.0


class ContextEngine3x:
    def __init__(self, buffer_size: int = 50):
        self.buffer_size = max(1, int(buffer_size))
        self.active_context: Deque[ContextItem] = deque(maxlen=self.buffer_size)
        self.redundant_memory: Deque[ContextItem] = deque(maxlen=self.buffer_size)
        self.meta_context: Dict[str, Any] = {"context_about_context": {}}
        self.noise_filter_threshold = 0.3
        self._importance_total = 0.0

    def add_context(self, content: str, source: str, importance: float = 0.5):
        """Add new context with noise filtering and O(1) bounded eviction."""
        noise_score = self._calculate_noise_score(content)
        if noise_score > self.noise_filter_threshold:
            return

        item = ContextItem(
            content=content,
            timestamp=time.time(),
            source=source,
            importance=importance,
            noise_score=noise_score,
        )

        if len(self.active_context) == self.buffer_size:
            self._importance_total -= self.active_context[0].importance

        self.active_context.append(item)
        self.redundant_memory.append(item)
        self._importance_total += item.importance
        self._update_meta_context(item)

    def _calculate_noise_score(self, content: str) -> float:
        """Simple real-time noise detection (expand with real models later)."""
        normalized = content.casefold()
        matches = sum(indicator in normalized for indicator in _NOISE_INDICATORS)
        return matches / len(_NOISE_INDICATORS)

    def _update_meta_context(self, item: ContextItem):
        """Maintain meta-context without rescanning the active buffer."""
        self._refresh_meta_context(item.timestamp)

    def _refresh_meta_context(self, timestamp: float) -> None:
        context_length = len(self.active_context)
        self.meta_context["last_update"] = timestamp
        self.meta_context["context_length"] = context_length
        self.meta_context["average_importance"] = (
            self._importance_total / context_length if context_length else 0.0
        )

    def get_active_context(self, include_meta: bool = False) -> Dict:
        recent_items: List[ContextItem] = list(islice(reversed(self.active_context), 10))
        recent_items.reverse()
        context = {
            "active_context": [item.content for item in recent_items],
            "redundant_memory_size": len(self.redundant_memory),
        }
        if include_meta:
            context["meta_context"] = self.meta_context
        return context

    def clear_noise(self):
        """Force clean both context copies and keep aggregate metadata synchronized."""
        retained = [
            item
            for item in self.active_context
            if item.noise_score <= self.noise_filter_threshold
        ]
        if len(retained) == len(self.active_context):
            return

        self.active_context.clear()
        self.active_context.extend(retained)
        self.redundant_memory.clear()
        self.redundant_memory.extend(retained)
        self._importance_total = sum(item.importance for item in retained)
        self._refresh_meta_context(time.time())


# Global instance
context_engine_3x = ContextEngine3x()
