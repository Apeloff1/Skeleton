"""
Skeleton Overseer — Spanning Multi-Graph System

Multiple system graphs, each spanning a facet of the organism, all
feeding one Overseer module that maintains total internal oversight
with max efficiency and capability.

The graphs:

1. FlowGraph    — data/control flow between subsystems (who feeds whom)
2. HealthGraph  — live health state per node (green/yellow/red with trends)
3. LoadGraph    — resource load and queue depths (the hardware-software
                  equilibrium telemetry surface)
4. FateGraph    — oracle predictions + realized outcomes (trajectory
                  alignment between plan and reality)

Each graph is small, incremental, and independently queryable. The
Overseer walks all four on each oversight cycle and emits a single
coherent verdict: system state, anomalies, recommended interventions.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from skeleton.kernel.events import DomainEvent, EventBus


# ---------------------------------------------------------------------------
# Graph primitives
# ---------------------------------------------------------------------------

@dataclass
class GraphNode:
    node_id: str
    kind: str
    attrs: Dict[str, Any] = field(default_factory=dict)
    updated_at: float = field(default_factory=time.time)


@dataclass
class GraphEdge:
    src: str
    dst: str
    kind: str
    weight: float = 1.0


class SystemGraph:
    """Small incremental directed graph; one per system facet."""

    def __init__(self, name: str):
        self.name = name
        self.nodes: Dict[str, GraphNode] = {}
        self.edges: List[GraphEdge] = []

    def upsert(self, node_id: str, kind: str, **attrs) -> GraphNode:
        node = self.nodes.get(node_id)
        if node is None:
            node = GraphNode(node_id=node_id, kind=kind)
            self.nodes[node_id] = node
        node.attrs.update(attrs)
        node.updated_at = time.time()
        return node

    def link(self, src: str, dst: str, kind: str, weight: float = 1.0) -> None:
        self.edges.append(GraphEdge(src=src, dst=dst, kind=kind, weight=weight))
        if len(self.edges) > 256:
            self.edges = self.edges[-128:]

    def neighbors(self, node_id: str, direction: str = "out") -> List[str]:
        if direction == "out":
            return [e.dst for e in self.edges if e.src == node_id]
        return [e.src for e in self.edges if e.dst == node_id]

    def summary(self) -> Dict[str, Any]:
        return {"graph": self.name, "nodes": len(self.nodes), "edges": len(self.edges)}


# ---------------------------------------------------------------------------
# The four facet graphs
# ---------------------------------------------------------------------------

class FlowGraph(SystemGraph):
    """Data/control flow between subsystems."""

    def __init__(self):
        super().__init__("flow")

    def record_flow(self, src: str, dst: str, volume: float = 1.0) -> None:
        self.upsert(src, "subsystem")
        self.upsert(dst, "subsystem")
        self.link(src, dst, "flow", weight=volume)


class HealthGraph(SystemGraph):
    """Health state per node with trend tracking."""

    def __init__(self):
        super().__init__("health")

    def mark(self, node_id: str, state: str) -> None:
        node = self.upsert(node_id, "subsystem")
        prev = node.attrs.get("state")
        node.attrs["state"] = state
        node.attrs["trend"] = (
            "improving" if prev in ("red", "yellow") and state == "green" else
            "degrading" if prev == "green" and state in ("yellow", "red") else
            "steady"
        )

    def worst(self, n: int = 5) -> List[Tuple[str, str]]:
        order = {"red": 0, "yellow": 1, "green": 2}
        ranked = sorted(
            ((nid, node.attrs.get("state", "green")) for nid, node in self.nodes.items()),
            key=lambda x: order.get(x[1], 2),
        )
        return ranked[:n]


class LoadGraph(SystemGraph):
    """Resource load: queue depths, resident planes, execution pressure.

    This is the hardware-software equilibrium surface — where software
    demand meets hardware budget in one observable graph.
    """

    def __init__(self):
        super().__init__("load")

    def gauge(self, node_id: str, load: float, capacity: float = 1.0) -> None:
        self.upsert(node_id, "resource", load=round(load, 3), capacity=capacity,
                    utilization=round(load / max(0.01, capacity), 3))

    def pressure(self) -> float:
        """Aggregate system pressure 0..1 across all gauges."""
        if not self.nodes:
            return 0.0
        utils = [n.attrs.get("utilization", 0.0) for n in self.nodes.values()]
        return round(sum(utils) / len(utils), 3)

    def saturated(self, threshold: float = 0.85) -> List[str]:
        return [nid for nid, n in self.nodes.items()
                if n.attrs.get("utilization", 0.0) >= threshold]


class FateGraph(SystemGraph):
    """Prediction vs reality: oracle forecasts alongside realized outcomes."""

    def __init__(self):
        super().__init__("fate")

    def predict(self, event: str, probability: float) -> None:
        self.upsert(event, "prediction", probability=probability)

    def realize(self, event: str, realized: float) -> None:
        node = self.upsert(event, "prediction")
        node.attrs["realized"] = realized
        node.attrs["alignment"] = round(1.0 - abs(node.attrs.get("probability", 0.5) - realized), 3)

    def alignment(self) -> float:
        aligned = [n.attrs["alignment"] for n in self.nodes.values() if "alignment" in n.attrs]
        return round(sum(aligned) / len(aligned), 3) if aligned else 1.0


# ---------------------------------------------------------------------------
# The Overseer
# ---------------------------------------------------------------------------

@dataclass
class OverseerVerdict:
    """One oversight cycle's coherent verdict."""
    at: float
    state: str  # thriving | stable | strained | critical
    pressure: float
    worst_health: List[Tuple[str, str]]
    fate_alignment: float
    anomalies: List[str] = field(default_factory=list)
    interventions: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "at": self.at,
            "state": self.state,
            "pressure": self.pressure,
            "worst_health": self.worst_health,
            "fate_alignment": self.fate_alignment,
            "anomalies": self.anomalies,
            "interventions": self.interventions,
        }


class Overseer:
    """Full system oversight: walks all facet graphs, emits one verdict."""

    def __init__(self, bus: Optional[EventBus] = None):
        self._bus = bus
        self.flow = FlowGraph()
        self.health = HealthGraph()
        self.load = LoadGraph()
        self.fate = FateGraph()
        self._verdicts: List[OverseerVerdict] = []
        self._stats = {"cycles": 0, "interventions_issued": 0, "critical_verdicts": 0}

    def observe_event(self, topic: str, payload: Dict[str, Any]) -> None:
        """Feed a bus event into the facet graphs."""
        parts = topic.split(".")
        if len(parts) >= 2:
            self.flow.record_flow(parts[0], ".".join(parts[:2]))

        if topic == "organism.health.checked":
            for name, check in (payload.get("checks") or {}).items():
                state = "green" if check.get("healthy", True) else "red"
                self.health.mark(name, state)
        elif topic == "support.loader.loaded":
            self.load.gauge(f"plane.{payload.get('plane')}", 1.0, capacity=4.0)
        elif topic == "contexts.queue.enqueued":
            self.load.gauge("queue", float(payload.get("blended", 0.5)), capacity=32.0)
        elif topic == "contexts.oracle.reading":
            self.fate.predict(payload.get("next_event", "unknown"),
                              float(payload.get("probability", 0.5)))

    def oversight_cycle(self) -> OverseerVerdict:
        """Walk all four graphs; produce the single coherent verdict."""
        self._stats["cycles"] += 1
        pressure = self.load.pressure()
        worst = self.health.worst()
        alignment = self.fate.alignment()
        anomalies: List[str] = []
        interventions: List[str] = []

        # Anomaly detection across graphs
        saturated = self.load.saturated()
        if saturated:
            anomalies.append(f"saturated resources: {', '.join(saturated[:3])}")
            interventions.append("shed load via LoadingQueue eviction of idle planes")
        red_nodes = [nid for nid, state in worst if state == "red"]
        if red_nodes:
            anomalies.append(f"unhealthy subsystems: {', '.join(red_nodes[:3])}")
            interventions.append("route traffic around red nodes; trigger hospice healing")
        if alignment < 0.6:
            anomalies.append(f"oracle alignment degraded ({alignment})")
            interventions.append("recalibrate oracle confidence via LensContext")

        # Coherent state
        if red_nodes or pressure > 0.9:
            state = "critical"
            self._stats["critical_verdicts"] += 1
        elif pressure > 0.7 or alignment < 0.6:
            state = "strained"
        elif worst and worst[0][1] == "yellow":
            state = "stable"
        else:
            state = "thriving"

        verdict = OverseerVerdict(
            at=time.time(), state=state, pressure=pressure,
            worst_health=worst, fate_alignment=alignment,
            anomalies=anomalies, interventions=interventions,
        )
        self._verdicts.append(verdict)
        if len(self._verdicts) > 64:
            self._verdicts.pop(0)

        self._stats["interventions_issued"] += len(interventions)
        if self._bus:
            self._bus.publish(DomainEvent(
                topic="overseer.verdict",
                payload=verdict.to_dict(),
                correlation_id=f"overseer_{self._stats['cycles']}",
            ))
        return verdict

    def graphs_summary(self) -> Dict[str, Any]:
        return {
            "flow": self.flow.summary(),
            "health": self.health.summary(),
            "load": self.load.summary(),
            "fate": self.fate.summary(),
        }

    def equilibrium(self) -> Dict[str, Any]:
        """The hardware-software equilibrium report."""
        return {
            "pressure": self.load.pressure(),
            "saturated": self.load.saturated(),
            "gauges": {nid: n.attrs for nid, n in self.load.nodes.items()},
        }

    def stats(self) -> Dict[str, Any]:
        return {**self._stats, "graphs": self.graphs_summary()}
