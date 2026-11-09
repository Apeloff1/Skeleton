"""Deepen the developer visualize path — topology analysis + scoring."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from skeleton.developer.surface_inventory import (
    SurfaceInventory,
    SurfacePath,
    inventory_from_blueprint,
)


@dataclass
class TopologyStats:
    component_count: int = 0
    wire_count: int = 0
    orphan_components: List[str] = field(default_factory=list)
    dangling_wires: List[str] = field(default_factory=list)
    kinds: Dict[str, int] = field(default_factory=dict)
    max_degree: int = 0
    connected: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "component_count": self.component_count,
            "wire_count": self.wire_count,
            "orphan_components": list(self.orphan_components),
            "dangling_wires": list(self.dangling_wires),
            "kinds": dict(self.kinds),
            "max_degree": self.max_degree,
            "connected": self.connected,
        }


@dataclass
class VisualizeSnapshot:
    blueprint_name: str
    topology: Dict[str, Any]
    stats: TopologyStats
    inventory: SurfaceInventory
    render_text: str = ""
    compact: bool = False
    stored_prose: int = 0

    @property
    def mean_score(self) -> float:
        return self.inventory.mean_score(SurfacePath.VISUALIZE)

    def fingerprint(self) -> str:
        payload = json.dumps(
            {
                "name": self.blueprint_name,
                "stats": self.stats.to_dict(),
                "inv": self.inventory.fingerprint(),
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": "stu-tools-visualize-snapshot",
            "blueprint_name": self.blueprint_name,
            "stats": self.stats.to_dict(),
            "mean_score": self.mean_score,
            "inventory": self.inventory.to_dict(),
            "render_text_len": len(self.render_text),
            "compact": self.compact,
            "fingerprint": self.fingerprint(),
            "stored_prose": self.stored_prose,
        }


def _component_ids(topology: Mapping[str, Any]) -> List[str]:
    components = topology.get("components")
    if isinstance(components, Mapping):
        return [str(k) for k in components.keys()]
    if isinstance(components, list):
        out = []
        for i, c in enumerate(components):
            if isinstance(c, Mapping):
                out.append(str(c.get("id") or c.get("name") or i))
            else:
                out.append(str(i))
        return out
    return []


def _wire_endpoints(wire: Any) -> Tuple[Optional[str], Optional[str]]:
    if isinstance(wire, Mapping):
        src = wire.get("src") or wire.get("source") or wire.get("from")
        dst = wire.get("dst") or wire.get("destination") or wire.get("to")
        def _id(endpoint: Any) -> Optional[str]:
            if endpoint is None:
                return None
            if isinstance(endpoint, (list, tuple)) and endpoint:
                return str(endpoint[0])
            if isinstance(endpoint, Mapping):
                return str(endpoint.get("component") or endpoint.get("id") or endpoint.get("name") or "")
            return str(endpoint)
        return _id(src), _id(dst)
    if isinstance(wire, (list, tuple)) and len(wire) >= 2:
        a, b = wire[0], wire[1]
        sa = a[0] if isinstance(a, (list, tuple)) and a else a
        sb = b[0] if isinstance(b, (list, tuple)) and b else b
        return str(sa), str(sb)
    return None, None


def analyze_topology(topology: Mapping[str, Any]) -> TopologyStats:
    ids = _component_ids(topology)
    id_set = set(ids)
    wires = topology.get("wires") or []
    if not isinstance(wires, list):
        wires = []
    degree: Dict[str, int] = {i: 0 for i in ids}
    dangling: List[str] = []
    connected_nodes = set()
    for idx, wire in enumerate(wires):
        src, dst = _wire_endpoints(wire)
        label = f"wire[{idx}]"
        if src is None or dst is None:
            dangling.append(label)
            continue
        if src not in id_set or dst not in id_set:
            dangling.append(f"{label}:{src}->{dst}")
            continue
        degree[src] = degree.get(src, 0) + 1
        degree[dst] = degree.get(dst, 0) + 1
        connected_nodes.add(src)
        connected_nodes.add(dst)
    orphans = sorted(i for i in ids if degree.get(i, 0) == 0)
    kinds: Dict[str, int] = {}
    components = topology.get("components")
    if isinstance(components, Mapping):
        for comp in components.values():
            if isinstance(comp, Mapping):
                k = str(comp.get("kind") or "unknown")
                kinds[k] = kinds.get(k, 0) + 1
    elif isinstance(components, list):
        for comp in components:
            if isinstance(comp, Mapping):
                k = str(comp.get("kind") or "unknown")
                kinds[k] = kinds.get(k, 0) + 1
    return TopologyStats(
        component_count=len(ids),
        wire_count=len(wires),
        orphan_components=orphans,
        dangling_wires=dangling,
        kinds=kinds,
        max_degree=max(degree.values()) if degree else 0,
        connected=bool(ids) and len(connected_nodes) == len(ids),
    )


def topology_from_blueprint(blueprint: Any) -> Dict[str, Any]:
    """Normalize a blueprint object or dict into a topology mapping."""
    if isinstance(blueprint, Mapping):
        return dict(blueprint)
    if hasattr(blueprint, "to_dict"):
        data = blueprint.to_dict()
        if isinstance(data, Mapping):
            return dict(data)
    components: Dict[str, Any] = {}
    wires: List[Any] = []
    name = getattr(blueprint, "name", "unnamed")
    raw_components = getattr(blueprint, "components", {}) or {}
    if isinstance(raw_components, Mapping):
        for cid, comp in raw_components.items():
            if hasattr(comp, "kind"):
                ports = []
                for port in getattr(comp, "ports", []) or []:
                    ports.append(
                        {
                            "name": getattr(port, "name", ""),
                            "direction": getattr(port, "direction", ""),
                            "port_type": getattr(port, "port_type", ""),
                        }
                    )
                components[str(cid)] = {"kind": getattr(comp, "kind", "component"), "ports": ports}
            elif isinstance(comp, Mapping):
                components[str(cid)] = dict(comp)
            else:
                components[str(cid)] = {"kind": "opaque"}
    for wire in getattr(blueprint, "wires", []) or []:
        if hasattr(wire, "src") and hasattr(wire, "dst"):
            wires.append({"src": wire.src, "dst": wire.dst})
        elif isinstance(wire, Mapping):
            wires.append(dict(wire))
        else:
            wires.append(wire)
    return {
        "name": name,
        "blueprint_id": getattr(blueprint, "blueprint_id", ""),
        "components": components,
        "wires": wires,
    }


def snapshot_visualize(
    blueprint: Any = None,
    *,
    topology: Optional[Mapping[str, Any]] = None,
    name: str = "",
    compact: bool = False,
    render_text: str = "",
) -> VisualizeSnapshot:
    topo = dict(topology) if topology is not None else topology_from_blueprint(blueprint)
    bp_name = name or str(topo.get("name") or "unnamed")
    stats = analyze_topology(topo)
    inventory = inventory_from_blueprint(topo, name=bp_name)
    if not render_text and blueprint is not None:
        try:
            from skeleton.developer.wizard import BlueprintVisualizer
            render_text = BlueprintVisualizer.render(blueprint, compact=compact)
        except Exception:
            render_text = ""
    return VisualizeSnapshot(
        blueprint_name=bp_name,
        topology=topo,
        stats=stats,
        inventory=inventory,
        render_text=render_text,
        compact=compact,
        stored_prose=0,
    )


def deepen_visualize_report(
    blueprint: Any = None,
    *,
    topology: Optional[Mapping[str, Any]] = None,
    name: str = "",
    compact: bool = False,
) -> Dict[str, Any]:
    snap = snapshot_visualize(blueprint, topology=topology, name=name, compact=compact)
    return {
        "kind": "stu-tools-visualize-report",
        "snapshot": snap.to_dict(),
        "topology": snap.topology,
        "weakest": [s.to_dict() for s in snap.inventory.weakest(fraction=0.15, path=SurfacePath.VISUALIZE)],
        "recommendations": visualize_recommendations(snap),
        "stored_prose": 0,
    }


def visualize_recommendations(snapshot: VisualizeSnapshot) -> List[Dict[str, str]]:
    recs: List[Dict[str, str]] = []
    if snapshot.stats.component_count == 0:
        recs.append({"action": "add_components", "trigger": "empty_topology", "detail": "no components"})
    if snapshot.stats.orphan_components:
        recs.append(
            {
                "action": "wire_orphans",
                "trigger": "orphan_components",
                "detail": ",".join(snapshot.stats.orphan_components[:8]),
            }
        )
    if snapshot.stats.dangling_wires:
        recs.append(
            {
                "action": "fix_dangling_wires",
                "trigger": "dangling_wires",
                "detail": ",".join(snapshot.stats.dangling_wires[:8]),
            }
        )
    if not snapshot.stats.connected and snapshot.stats.component_count > 1:
        recs.append({"action": "connect_graph", "trigger": "disconnected", "detail": "topology not fully connected"})
    if snapshot.mean_score < 0.7:
        recs.append(
            {
                "action": "regenerate_weak_components",
                "trigger": "mean_score<0.7",
                "detail": f"mean_score={snapshot.mean_score}",
            }
        )
    if not recs:
        recs.append({"action": "maintain", "trigger": "healthy", "detail": "topology ok"})
    return recs


def render_visualize_deep(report: Mapping[str, Any]) -> str:
    snap = report.get("snapshot") or {}
    stats = snap.get("stats") or {}
    lines = [
        "STU-TOOLS Visualize Deep Report",
        f"  blueprint: {snap.get('blueprint_name')}",
        f"  components: {stats.get('component_count')}  wires: {stats.get('wire_count')}",
        f"  connected: {stats.get('connected')}  max_degree: {stats.get('max_degree')}",
        f"  mean_score: {snap.get('mean_score')}  fp: {snap.get('fingerprint')}",
    ]
    orphans = stats.get("orphan_components") or []
    if orphans:
        lines.append(f"  orphans: {', '.join(orphans[:10])}")
    dangling = stats.get("dangling_wires") or []
    if dangling:
        lines.append(f"  dangling: {', '.join(dangling[:10])}")
    return "\n".join(lines)


__all__ = [
    "TopologyStats",
    "VisualizeSnapshot",
    "analyze_topology",
    "topology_from_blueprint",
    "snapshot_visualize",
    "deepen_visualize_report",
    "visualize_recommendations",
    "render_visualize_deep",
]
