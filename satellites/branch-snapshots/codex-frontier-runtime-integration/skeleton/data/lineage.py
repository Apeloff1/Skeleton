"""Data lineage — end-to-end data flow tracking across subsystems.

Records where data originates, which transforms touch it, and where
it lands. Provides upstream/downstream tracing for any dataset,
impact analysis for schema changes, and compliance export (who saw
what data when) for the audit surface.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set


@dataclass
class LineageNode:
    dataset: str
    owner: str
    kind: str = "table"
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LineageEdge:
    source: str
    target: str
    transform: str
    subsystem: str
    timestamp_ns: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "target": self.target,
            "transform": self.transform,
            "subsystem": self.subsystem,
        }


class DataLineage:
    """Dataset-level lineage graph with impact analysis."""

    def __init__(self):
        self._nodes: Dict[str, LineageNode] = {}
        self._edges: List[LineageEdge] = []
        self._access_log: List[Dict[str, Any]] = []

    def register_dataset(self, dataset: str, owner: str, kind: str = "table",
                         **metadata: Any) -> LineageNode:
        node = LineageNode(dataset=dataset, owner=owner, kind=kind, metadata=metadata)
        self._nodes[dataset] = node
        return node

    def record_transform(self, source: str, target: str, transform: str,
                         subsystem: str) -> LineageEdge:
        for ds in (source, target):
            if ds not in self._nodes:
                self.register_dataset(ds, owner=subsystem)
        edge = LineageEdge(source=source, target=target, transform=transform,
                           subsystem=subsystem, timestamp_ns=time.time_ns())
        self._edges.append(edge)
        return edge

    def record_access(self, dataset: str, actor: str, operation: str) -> None:
        self._access_log.append({
            "dataset": dataset, "actor": actor, "operation": operation,
            "timestamp_ns": time.time_ns(),
        })

    def upstream(self, dataset: str) -> List[str]:
        seen: Set[str] = set()
        queue = [dataset]
        while queue:
            current = queue.pop()
            for edge in self._edges:
                if edge.target == current and edge.source not in seen:
                    seen.add(edge.source)
                    queue.append(edge.source)
        return sorted(seen)

    def downstream(self, dataset: str) -> List[str]:
        seen: Set[str] = set()
        queue = [dataset]
        while queue:
            current = queue.pop()
            for edge in self._edges:
                if edge.source == current and edge.target not in seen:
                    seen.add(edge.target)
                    queue.append(edge.target)
        return sorted(seen)

    def impact_analysis(self, dataset: str) -> Dict[str, Any]:
        downstream = self.downstream(dataset)
        owners = {self._nodes[d].owner for d in downstream if d in self._nodes}
        return {
            "dataset": dataset,
            "impacted_datasets": downstream,
            "impacted_owners": sorted(owners),
            "severity": "high" if len(downstream) > 5 else "medium" if downstream else "low",
        }

    def access_report(self, dataset: str) -> List[Dict[str, Any]]:
        return [a for a in self._access_log if a["dataset"] == dataset]

    def card(self) -> Dict[str, Any]:
        return {
            "kind": "lineage-card",
            "datasets": len(self._nodes),
            "transforms": len(self._edges),
            "access_events": len(self._access_log),
            "orphans": sorted(n for n in self._nodes
                              if not any(e.source == n or e.target == n for e in self._edges)),
        }
