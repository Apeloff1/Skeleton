from __future__ import annotations
"""
Latent Metrics Table — Structured tracking for retrieval quality, agent performance, latency, GEPA improvements, queue health, thermal/concurrency, RAG scores, etc.
App-wide, queryable, drives self-improvement (GEPA, Grok reflection).
Interconnects with Hybrid RAG, Vector Shards, MCP, Jeeves queues, exocortex, every room.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import time
import hashlib

@dataclass
class MetricEntry:
    metric_id: str
    timestamp: float
    category: str  # retrieval, agent, queue, thermal, rag, ge pa, concurrency, etc.
    name: str
    value: float
    metadata: Dict[str, Any]
    room_id: str = "global"

class LatentMetricsTable:
    """
    Latent Metrics Table for the CNS.
    Tracks hidden/performance metrics to enable continuous self-improvement.
    """

    def __init__(self):
        self.metrics: Dict[str, List[MetricEntry]] = {}  # category -> list of entries
        self.summary: Dict[str, Dict[str, float]] = {}   # quick aggregates

    def record_metric(self, category: str, name: str, value: float, metadata: Dict = None, room_id: str = "global"):
        """Record a new metric entry."""
        entry = MetricEntry(
            metric_id=hashlib.md5(f"{category}{name}{time.time()}".encode()).hexdigest()[:10],
            timestamp=time.time(),
            category=category,
            name=name,
            value=value,
            metadata=metadata or {},
            room_id=room_id
        )
        if category not in self.metrics:
            self.metrics[category] = []
        self.metrics[category].append(entry)

        # Update summary
        if category not in self.summary:
            self.summary[category] = {}
        self.summary[category][name] = value  # latest value

        return entry.metric_id

    def query_metrics(self, category: str = None, name: str = None, room_id: str = None, limit: int = 50) -> List[MetricEntry]:
        """Query metrics with filters."""
        results = []
        categories = [category] if category else list(self.metrics.keys())
        for cat in categories:
            for entry in self.metrics.get(cat, []):
                if name and entry.name != name:
                    continue
                if room_id and entry.room_id != room_id and entry.room_id != "global":
                    continue
                results.append(entry)
        results.sort(key=lambda x: x.timestamp, reverse=True)
        return results[:limit]

    def get_summary(self, category: str = None) -> Dict[str, Any]:
        if category:
            return self.summary.get(category, {})
        return self.summary

    def status(self) -> Dict[str, Any]:
        total_entries = sum(len(v) for v in self.metrics.values())
        return {
            "total_entries": total_entries,
            "categories": list(self.metrics.keys()),
            "summary": self.summary,
            "key_capabilities": "structured_metrics, queryable, drives_self_improvement, room_aware",
            "cowabunga_note": "Latent metrics now powering GEPA/Grok reflection and room optimization across the entire CNS"
        }
