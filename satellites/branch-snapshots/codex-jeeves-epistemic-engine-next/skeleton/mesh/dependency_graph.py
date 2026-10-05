"""Dependency graph — subsystem dependency analysis and impact mapping.

Builds a live dependency graph across all Skeleton subsystems from
declared edges. Provides topological ordering, blast-radius analysis
(what breaks if X fails), cycle detection, and critical-path ranking
for the doctor card and deployment ordering.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Set


@dataclass
class DependencyEdge:
    source: str
    target: str
    kind: str = "requires"   # requires | optional | data_flow


class DependencyGraph:
    """Directed dependency graph with blast-radius analysis."""

    def __init__(self):
        self._edges: List[DependencyEdge] = []
        self._nodes: Set[str] = set()
        self._metadata: Dict[str, Dict[str, Any]] = {}

    def add_node(self, name: str, **metadata: Any) -> None:
        self._nodes.add(name)
        self._metadata[name] = {**self._metadata.get(name, {}), **metadata}

    def add_edge(self, source: str, target: str, kind: str = "requires") -> None:
        self._nodes.update({source, target})
        self._edges.append(DependencyEdge(source, target, kind))

    def dependencies_of(self, node: str) -> List[str]:
        return [e.target for e in self._edges if e.source == node]

    def dependents_of(self, node: str) -> List[str]:
        return [e.source for e in self._edges if e.target == node]

    def topological_order(self) -> List[str]:
        order: List[str] = []
        visited: Set[str] = set()
        temp: Set[str] = set()

        def visit(n: str) -> None:
            if n in visited:
                return
            if n in temp:
                raise ValueError(f"dependency cycle involving: {n}")
            temp.add(n)
            for dep in self.dependencies_of(n):
                visit(dep)
            temp.discard(n)
            visited.add(n)
            order.append(n)

        for node in sorted(self._nodes):
            visit(node)
        return order

    def cycles(self) -> List[List[str]]:
        try:
            self.topological_order()
            return []
        except ValueError as exc:
            return [[str(exc)]]

    def blast_radius(self, node: str) -> Dict[str, Any]:
        """Everything transitively impacted if `node` fails."""
        affected: Set[str] = set()
        queue = [node]
        while queue:
            current = queue.pop()
            for dependent in self.dependents_of(current):
                if dependent not in affected:
                    affected.add(dependent)
                    queue.append(dependent)
        return {
            "node": node,
            "affected": sorted(affected),
            "blast_size": len(affected),
            "critical": len(affected) >= max(1, len(self._nodes) // 3),
        }

    def critical_path_ranking(self) -> List[Dict[str, Any]]:
        return sorted(
            (self.blast_radius(n) for n in self._nodes),
            key=lambda r: -r["blast_size"],
        )

    def card(self) -> Dict[str, Any]:
        return {
            "kind": "dependency-graph-card",
            "nodes": len(self._nodes),
            "edges": len(self._edges),
            "cycles": self.cycles(),
            "most_critical": self.critical_path_ranking()[:5],
        }
