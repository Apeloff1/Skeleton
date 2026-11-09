#!/usr/bin/env python3
"""
Context Engine 3×
Buffered Active Context + Redundant Context Memory + Meta-Context + Real-time Noise Filter
"""

from typing import List, Dict, Any
from dataclasses import dataclass
import time

@dataclass
class ContextItem:
    content: str
    timestamp: float
    source: str
    importance: float = 0.5
    noise_score: float = 0.0

class ContextEngine3x:
    def __init__(self, buffer_size: int = 50):
        self.active_context: List[ContextItem] = []
        self.redundant_memory: List[ContextItem] = []  # Redundant copy
        self.meta_context: Dict[str, Any] = {"context_about_context": {}}
        self.buffer_size = buffer_size
        self.noise_filter_threshold = 0.3

    def add_context(self, content: str, source: str, importance: float = 0.5):
        """Add new context with noise filtering."""
        noise_score = self._calculate_noise_score(content)
        
        if noise_score > self.noise_filter_threshold:
            return  # Filtered out as noise

        item = ContextItem(
            content=content,
            timestamp=time.time(),
            source=source,
            importance=importance,
            noise_score=noise_score
        )
        
        self.active_context.append(item)
        self.redundant_memory.append(item)  # Maintain redundancy
        
        if len(self.active_context) > self.buffer_size:
            self.active_context.pop(0)
            self.redundant_memory.pop(0)

        self._update_meta_context(item)

    def _calculate_noise_score(self, content: str) -> float:
        """Simple real-time noise detection (expand with real models later)."""
        noise_indicators = ["filler", "irrelevant", "low value", "contradictory"]
        score = sum(1 for word in noise_indicators if word in content.lower()) / len(noise_indicators)
        return min(score, 1.0)

    def _update_meta_context(self, item: ContextItem):
        """Maintain meta-context about the current context state."""
        self.meta_context["last_update"] = time.time()
        self.meta_context["context_length"] = len(self.active_context)
        self.meta_context["average_importance"] = sum(i.importance for i in self.active_context) / max(len(self.active_context), 1)

    def get_active_context(self, include_meta: bool = False) -> Dict:
        context = {
            "active_context": [item.content for item in self.active_context[-10:]],
            "redundant_memory_size": len(self.redundant_memory)
        }
        if include_meta:
            context["meta_context"] = self.meta_context
        return context

    def clear_noise(self):
        """Force clean the active context."""
        self.active_context = [item for item in self.active_context if item.noise_score < self.noise_filter_threshold]

# Global instance
context_engine_3x = ContextEngine3x()