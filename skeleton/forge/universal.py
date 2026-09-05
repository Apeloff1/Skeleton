"""The Universal Forge — composable system blueprints.

A blueprint declares a system as a composition of named components with
typed ports and wires between them. The forge validates the graph (all wires
resolve, directions and types match, no dependency cycles), then materialises
it into a runnable, inspectable description with a topological execution
order. Blueprints compose: new component kinds can be registered at runtime.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from skeleton.kernel.errors import BlueprintError, MaterialisationError
from skeleton.kernel.events import DomainEvent, EventBus
from skeleton.kernel.ids import BlueprintId


@dataclass(frozen=True)
class Port:
    name: str
    port_type: str
    direction: str

    def __post_init__(self) -> None:
        if self.direction not in {"in", "out"}:
            raise BlueprintError("port direction must be 'in' or 'out'", context={"port": self.name})


@dataclass(frozen=True)
class Component:
    instance_id: str
    kind: str
    ports: tuple[Port, ...]
    config: dict[str, Any] = field(default_factory=dict)

    def port(self, name: str) -> Port:
        for p in self.ports:
            if p.name == name:
                return p
        raise BlueprintError("component has no such port", context={"component": self.instance_id, "port": name})


@dataclass(frozen=True)
class Wire:
    src: tuple[str, str]
    dst: tuple[str, str]


@dataclass
class Blueprint:
    blueprint_id: str
    name: str
    components: dict[str, Component] = field(default_factory=dict)
    wires: list[Wire] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)

    def add_component(self, component: Component) -> None:
        if component.instance_id in self.components:
            raise BlueprintError("duplicate component instance", context={"instance_id": component.instance_id})
        self.components[component.instance_id] = component

    def connect(self, src: tuple[str, str], dst: tuple[str, str]) -> None:
        self.wires.append(Wire(src=src, dst=dst))

    def validate(self) -> list[str]:
        problems: list[str] = []
        for wire in self.wires:
            for end, direction in ((wire.src, "out"), (wire.dst, "in")):
                comp_id, port_name = end
                comp = self.components.get(comp_id)
                if comp is None:
                    problems.append(f"wire references unknown component {comp_id!r}")
                    continue
                try:
                    port = comp.port(port_name)
                except BlueprintError:
                    problems.append(f"{comp_id!r} has no port {port_name!r}")
                    continue
                if port.direction != direction:
                    problems.append(f"{comp_id}.{port_name} is a {port.direction}-port; expected {direction}")
            src_comp = self.components.get(wire.src[0])
            dst_comp = self.components.get(wire.dst[0])
            if src_comp is not None and dst_comp is not None:
                try:
                    s = src_comp.port(wire.src[1])
                    d = dst_comp.port(wire.dst[1])
                    if s.port_type != d.port_type:
                        problems.append(f"type mismatch {wire.src[0]}.{wire.src[1]} ({s.port_type}) -> {wire.dst[0]}.{wire.dst[1]} ({d.port_type})")
                except BlueprintError:
                    pass
        edges: dict[str, list[str]] = {c: [] for c in self.components}
        for wire in self.wires:
            if wire.src[0] in edges and wire.dst[0] in edges:
                edges[wire.src[0]].append(wire.dst[0])
        visited: set[str] = set()
        stack: set[str] = set()

        def has_cycle(node: str) -> bool:
            visited.add(node)
            stack.add(node)
            for nxt in edges.get(node, []):
                if nxt not in visited:
                    if has_cycle(nxt):
                        return True
                elif nxt in stack:
                    return True
            stack.discard(node)
            return False

        if any(has_cycle(c) for c in self.components if c not in visited):
            problems.append("dependency cycle detected in component graph")
        return problems

    def to_dict(self) -> dict[str, Any]:
        return {
            "blueprint_id": self.blueprint_id,
            "name": self.name,
            "components": {
                cid: {"kind": c.kind, "ports": [{"name": p.name, "type": p.port_type, "direction": p.direction} for p in c.ports], "config": c.config}
                for cid, c in self.components.items()
            },
            "wires": [{"from": list(w.src), "to": list(w.dst)} for w in self.wires],
            "created_at": self.created_at,
        }


class Forge:
    """The universal synthesis engine."""

    def __init__(self, bus: EventBus | None = None, *, root=None) -> None:
        self._bus = bus or EventBus()
        self._kinds: dict[str, tuple[Port, ...]] = {}
        self._root = root
        self._register_stdlib()

    def _register_stdlib(self) -> None:
        self.register_kind("source", (Port("out", "event", "out"),))
        self.register_kind("transform", (Port("in", "event", "in"), Port("out", "event", "out")))
        self.register_kind("sink", (Port("in", "event", "in"),))
        self.register_kind("state_store", (Port("write", "state", "in"), Port("read", "state", "out")))
        self.register_kind("player", (Port("intent", "event", "out"), Port("state", "state", "out")))
        self.register_kind("heat", (Port("in", "event", "in"), Port("critical", "signal", "out")))
        self.register_kind("weapon_forge", (Port("parts", "resource", "in"), Port("weapon", "event", "out")))
        self.register_kind("enemy_spawner", (Port("tick", "event", "in"), Port("spawn", "event", "out")))
        self.register_kind("collapse", (Port("tick", "event", "in"), Port("fail", "signal", "out")))
        self.register_kind("extract", (Port("cores", "resource", "in"), Port("success", "signal", "out")))
        self.register_kind("jeeves", (Port("telemetry", "state", "in"), Port("advice", "event", "out")))

    def register_kind(self, kind: str, ports: tuple[Port, ...]) -> None:
        if not kind.strip():
            raise BlueprintError("kind name must be non-empty")
        self._kinds[kind] = tuple(ports)

    def available_kinds(self) -> list[str]:
        return sorted(self._kinds)

    def new_blueprint(self, name: str) -> Blueprint:
        if not name.strip():
            raise BlueprintError("blueprint name must be non-empty")
        bp = Blueprint(blueprint_id=str(BlueprintId.new()), name=name)
        self._bus.emit("forge.blueprint.created", {"blueprint_id": bp.blueprint_id, "name": name})
        return bp

    def instantiate(self, blueprint: Blueprint, kind: str, instance_id: str, *, config: dict[str, Any] | None = None) -> Component:
        ports = self._kinds.get(kind)
        if ports is None:
            raise BlueprintError("unknown component kind", context={"kind": kind, "available": self.available_kinds()})
        component = Component(instance_id=instance_id, kind=kind, ports=tuple(Port(p.name, p.port_type, p.direction) for p in ports), config=dict(config or {}))
        blueprint.add_component(component)
        return component

    def materialise(self, blueprint: Blueprint, *, era: str = "extraction_now", target: str = "json", pack: dict[str, Any] | None = None, build_plan: dict[str, Any] | None = None, repair: bool = False, max_rounds: int = 3) -> dict[str, Any]:
        from skeleton.forge.eras import compile_era
        from skeleton.forge.godot_emit import emit_godot
        from skeleton.forge.planner import MaterialisationPlanner
        from skeleton.intelligence.forge_verifier import ForgeVerifier
        from skeleton.organism.quality_state import append_quality

        problems = blueprint.validate()
        if problems:
            raise MaterialisationError("blueprint failed validation", context={"blueprint_id": blueprint.blueprint_id, "problems": problems})
        pack = pack or compile_era(era)
        order = self._topological_order(blueprint)
        plan = MaterialisationPlanner(bus=self._bus).plan_blueprint(blueprint)
        result: dict[str, Any] = {
            "blueprint_id": blueprint.blueprint_id,
            "name": blueprint.name,
            "era": pack["era"],
            "primary_dps": pack["primary_dps"],
            "pack": pack,
            "topology": blueprint.to_dict(),
            "execution_order": order,
            "plan": plan.to_dict(),
            "build_plan": build_plan or {},
        }
        if target == "godot":
            files = emit_godot(pack, title=blueprint.name, build_plan=build_plan)
            verifier = ForgeVerifier(root=self._root)
            if repair:
                # F-5: revise-until-green via VerificationLoop + CodeVerifier.verdict.
                from skeleton.forge.verify_loop import forge_verify_until_green
                looped = forge_verify_until_green(
                    files,
                    request=blueprint.name,
                    root=self._root,
                    max_rounds=max_rounds,
                )
                result["files"] = looped["files"]
                result["file_count"] = len(looped["files"])
                result["verification"] = looped["verification"]
                result["verification_stats"] = looped["verification_stats"]
                result["verify_loop"] = {
                    "accepted": looped["accepted"],
                    "trace": looped["trace"],
                    "code_verdict": looped.get("code_verdict"),
                    "stopped_reason": looped.get("stopped_reason"),
                    "rounds_detail": looped.get("rounds_detail"),
                    "threshold": looped.get("threshold"),
                }
                if looped.get("repairs"):
                    result["repair"] = looped["repairs"][-1]
                    result["repairs"] = looped["repairs"]
                verification_accepted = bool(looped["accepted"])
                verification_payload = looped["verification"]
                evidence = {
                    "project_issues": list(verification_payload.get("project_issues") or []),
                    "blocking_issues": list(verification_payload.get("blocking_issues") or []),
                    "top_file_reports": list(verification_payload.get("file_reports") or [])[:3],
                    "verify_loop": result["verify_loop"],
                }
                append_quality({
                    "kind": "quality",
                    "surface": "forge",
                    "accepted": verification_accepted,
                    "reason": verification_payload.get("reason"),
                    "score": verification_payload.get("score"),
                    "weakest_path": verification_payload.get("weakest_path"),
                    "summary": verification_payload.get("summary") or {},
                    "metadata": (verification_payload.get("quality") or {}).get("metadata") or {"kind": "forge"},
                    "evidence": evidence,
                }, root=self._root)
                self._bus.publish(DomainEvent(
                    topic="forge.verification.completed" if verification_accepted else "forge.verification.failed",
                    payload={
                        "blueprint_id": blueprint.blueprint_id,
                        "name": blueprint.name,
                        "target": target,
                        "accepted": verification_accepted,
                        "reason": verification_payload.get("reason"),
                        "score": verification_payload.get("score"),
                        "weakest_path": verification_payload.get("weakest_path"),
                        "summary": verification_payload.get("summary") or {},
                        "verify_loop": result["verify_loop"]["trace"],
                    },
                    correlation_id=f"forge_verify_{blueprint.blueprint_id}",
                ))
                if looped.get("repairs"):
                    last = looped["repairs"][-1]
                    self._bus.publish(DomainEvent(
                        topic="forge.repair.completed" if last.get("ok") else "forge.repair.failed",
                        payload={
                            "blueprint_id": blueprint.blueprint_id,
                            "name": blueprint.name,
                            "accepted": bool(last.get("ok")),
                            "reason": last.get("reason"),
                            "targeted_path": last.get("targeted_path"),
                            "changed": last.get("changed"),
                            "rounds": looped["trace"].get("rounds"),
                        },
                        correlation_id=f"forge_repair_{blueprint.blueprint_id}",
                    ))
                if not verification_accepted:
                    raise MaterialisationError(
                        "emitted Godot project failed verification",
                        context={
                            "blueprint_id": blueprint.blueprint_id,
                            "verification": verification_payload,
                            "verification_stats": looped["verification_stats"],
                            "verify_loop": result["verify_loop"],
                        },
                    )
            else:
                verification = verifier.verify(files, request=blueprint.name)
                result["files"] = files
                result["file_count"] = len(files)
                result["verification"] = verification.to_dict()
                result["verification_stats"] = verifier.stats()
                evidence = {
                    "project_issues": list(verification.project_issues),
                    "blocking_issues": list(verification.blocking_issues),
                    "top_file_reports": [r.to_dict() for r in verification.file_reports[:3]],
                }
                append_quality({
                    "kind": "quality",
                    "surface": "forge",
                    "accepted": verification.accepted,
                    "reason": verification.reason,
                    "score": verification.score,
                    "weakest_path": verification.weakest_path,
                    "summary": verification.summary,
                    "metadata": verification.quality.metadata,
                    "evidence": evidence,
                }, root=self._root)
                self._bus.publish(DomainEvent(
                    topic="forge.verification.completed" if verification.accepted else "forge.verification.failed",
                    payload={
                        "blueprint_id": blueprint.blueprint_id,
                        "name": blueprint.name,
                        "target": target,
                        "accepted": verification.accepted,
                        "reason": verification.reason,
                        "score": verification.score,
                        "weakest_path": verification.weakest_path,
                        "summary": verification.summary,
                    },
                    correlation_id=f"forge_verify_{blueprint.blueprint_id}",
                ))
                if not verification.accepted:
                    raise MaterialisationError(
                        "emitted Godot project failed verification",
                        context={
                            "blueprint_id": blueprint.blueprint_id,
                            "verification": verification.to_dict(),
                            "verification_stats": verifier.stats(),
                        },
                    )
        self._bus.emit("forge.blueprint.materialised", {"blueprint_id": blueprint.blueprint_id, "components": len(blueprint.components), "wires": len(blueprint.wires), "era": pack["era"], "target": target})
        return result

    @staticmethod
    def _topological_order(blueprint: Blueprint) -> list[str]:
        indegree = {c: 0 for c in blueprint.components}
        for wire in blueprint.wires:
            if wire.dst[0] in indegree:
                indegree[wire.dst[0]] += 1
        queue = sorted([c for c, d in indegree.items() if d == 0])
        order: list[str] = []
        while queue:
            node = queue.pop(0)
            order.append(node)
            for wire in blueprint.wires:
                if wire.src[0] == node and wire.dst[0] in indegree:
                    indegree[wire.dst[0]] -= 1
                    if indegree[wire.dst[0]] == 0:
                        queue.append(wire.dst[0])
        return order
