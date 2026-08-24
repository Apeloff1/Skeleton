"""Materialisation planner — from validated blueprint to ordered build plan.

Validation proves a blueprint *can* be built; the planner decides *in what
order* and *at what cost*. It topologically sorts the system dependency
graph into build waves (everything in wave N depends only on waves < N),
estimates per-wave cost from declared resource hints, and flags the
critical path — the dependency chain that bounds total build time.

The plan is data, not execution: pipelines, the swarm scheduler, or the
API can consume it. Materialisation itself stays in `universal.py`; this
module only decides the schedule.

Design laws
-----------
- The planner never mutates the blueprint; the plan references it.
- Waves are maximal: every system is placed in the earliest wave its
  dependencies allow. Deterministic given the same blueprint.
- Cost estimation is honest about uncertainty: each wave reports the sum
  of declared costs plus an explicit unknown-count for systems that
  declared none.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from skeleton.kernel.errors import BlueprintError
from skeleton.kernel.events import DomainEvent, EventBus


@dataclass(frozen=True)
class PlannedSystem:
    system_id: str
    wave: int
    depends_on: tuple
    declared_cost: Optional[float] = None


@dataclass(frozen=True)
class BuildWave:
    index: int
    systems: tuple
    declared_cost: float
    unknown_costs: int


@dataclass
class BuildPlan:
    blueprint_name: str
    waves: List[BuildWave] = field(default_factory=list)
    critical_path: List[str] = field(default_factory=list)
    total_declared_cost: float = 0.0
    parallelisable: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "blueprint": self.blueprint_name,
            "waves": [
                {"index": w.index, "systems": list(w.systems),
                 "declared_cost": w.declared_cost, "unknown_costs": w.unknown_costs}
                for w in self.waves
            ],
            "critical_path": self.critical_path,
            "critical_path_length": len(self.critical_path),
            "total_declared_cost": self.total_declared_cost,
            "parallelisable": self.parallelisable,
        }


class MaterialisationPlanner:
    """Plans the build order for a validated forge blueprint."""

    def __init__(self, *, bus: Optional[EventBus] = None) -> None:
        self._bus = bus
        self._plans = 0

    def plan(self, blueprint: Dict[str, Any]) -> BuildPlan:
        systems = blueprint.get("systems", [])
        if not systems:
            raise BlueprintError("cannot plan an empty blueprint")

        deps: Dict[str, List[str]] = {
            s["id"]: list(s.get("depends_on", []))
            for s in systems if s.get("id")
        }
        costs: Dict[str, Optional[float]] = {
            s["id"]: s.get("declared_cost") for s in systems if s.get("id")
        }

        # ---- wave assignment: longest path from a root ---------------------
        wave_of: Dict[str, int] = {}

        def wave(sid: str, seen: frozenset = frozenset()) -> int:
            if sid in wave_of:
                return wave_of[sid]
            if sid in seen:
                raise BlueprintError(
                    "dependency cycle during planning",
                    context={"system": sid},
                )
            parents = [d for d in deps.get(sid, []) if d in deps]
            w = 0 if not parents else max(wave(p, seen | {sid}) for p in parents) + 1
            wave_of[sid] = w
            return w

        for sid in deps:
            wave(sid)

        n_waves = max(wave_of.values()) + 1
        plan = BuildPlan(blueprint_name=str(blueprint.get("name", "unnamed")))
        for w in range(n_waves):
            members = tuple(sorted(s for s, sw in wave_of.items() if sw == w))
            declared = sum(c for m in members if (c := costs.get(m)) is not None)
            unknown = sum(1 for m in members if costs.get(m) is None)
            plan.waves.append(BuildWave(index=w, systems=members,
                                        declared_cost=declared, unknown_costs=unknown))
        plan.total_declared_cost = sum(w.declared_cost for w in plan.waves)
        plan.parallelisable = any(len(w.systems) > 1 for w in plan.waves)
        plan.critical_path = self._critical_path(deps, wave_of)

        self._plans += 1
        if self._bus:
            self._bus.publish(
                DomainEvent(
                    topic="forge.plan.created",
                    payload={
                        "blueprint": plan.blueprint_name,
                        "waves": n_waves,
                        "systems": len(deps),
                        "critical_path_length": len(plan.critical_path),
                    },
                    correlation_id=f"plan_{self._plans}",
                )
            )
        return plan

    def _critical_path(self, deps: Dict[str, List[str]],
                       wave_of: Dict[str, int]) -> List[str]:
        """One longest dependency chain — the chain that bounds build time."""
        if not wave_of:
            return []
        tail = max(wave_of, key=lambda s: wave_of[s])
        path = [tail]
        current = tail
        while deps.get(current):
            parents = [p for p in deps[current] if p in deps]
            if not parents:
                break
            current = max(parents, key=lambda p: wave_of.get(p, 0))
            path.append(current)
        path.reverse()
        return path
