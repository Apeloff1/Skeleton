"""
Skeleton Support — The Support Fabric

Spider-connected mirror of the primary ContextFabric: six support
planes (sentinel, hospice, blueprint, resonance, lens, ward), the
on-demand LoadingQueue, the AgenticRAG controller, and the Overseer
spanning graph system — all bound into one support web that mirrors,
heals, and oversees the primary fabric.

Loading discipline: all support planes are lazy. Only the LoadingQueue
and Overseer are resident at boot; every other plane materializes when
pressure from its primary justifies it, and unloads when idle.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from skeleton.kernel.events import DomainEvent, EventBus
from skeleton.support.planes import (
    SentinelContext,
    HospiceContext,
    BlueprintContext,
    ResonanceContext,
    LensContext,
    WardContext,
)
from skeleton.support.loading import LoadingQueue, LoadRequest, LoadedPlane
from skeleton.support.agentic_rag import AgenticRAG, AgenticResult, RetrievalPlan
from skeleton.overseer.graphs import Overseer, OverseerVerdict


class SupportFabric:
    """The mirror web: support planes + loader + agentic RAG + overseer."""

    def __init__(self, bus: Optional[EventBus] = None, quad: Optional[Any] = None,
                 sam: Optional[Any] = None):
        self._bus = bus

        # Always-resident: the loader and the overseer
        self.loader = LoadingQueue(bus=bus)
        self.overseer = Overseer(bus=bus)
        self.agentic_rag = AgenticRAG(quad=quad, sam=sam, bus=bus) if quad else None

        # Lazy: the six support planes, registered but not loaded
        self.loader.register("sentinel", lambda: SentinelContext(bus=self._bus))
        self.loader.register("hospice", lambda: HospiceContext(bus=self._bus))
        self.loader.register("blueprint", lambda: BlueprintContext(bus=self._bus))
        self.loader.register("resonance", lambda: ResonanceContext(bus=self._bus))
        self.loader.register("lens", lambda: LensContext(bus=self._bus))
        self.loader.register("ward", lambda: WardContext(bus=self._bus))

        self._stats = {"cycles": 0}

    # --- Pressure-driven support cycle --------------------------------------

    def support_cycle(self, fabric: Any) -> Dict[str, Any]:
        """One support pass over the primary fabric.

        Reads primary plane stats → signals pressure → pumps the loading
        queue → runs whichever support planes materialized → overseer verdict.
        """
        self._stats["cycles"] += 1
        out: Dict[str, Any] = {"loaded": [], "actions": {}}

        # Signal pressure from primary state
        wo_stats = fabric.workorders.stats()
        if wo_stats["orders"] > 5:
            self.loader.signal_pressure("sentinel", 0.8, "high order volume")
        if len(fabric.backlog.items) > 3:
            self.loader.signal_pressure("hospice", 0.7, "backlog accumulating")
        if fabric.planning.active_plans():
            self.loader.signal_pressure("blueprint", 0.5, "active plans")
        if len(fabric.queue.items) > 4:
            self.loader.signal_pressure("resonance", 0.6, "queue depth")
        if fabric.oracle.stats()["readings"] > 3:
            self.loader.signal_pressure("lens", 0.5, "oracle active")
        if fabric.syntax.stats()["issues"] > 0:
            self.loader.signal_pressure("ward", 0.6, "syntax issues seen")

        # Pump: load what's warranted (bounded, minimal footprint)
        out["loaded"] = self.loader.pump()

        # Run resident support planes against their primaries
        sentinel = self.loader.get("sentinel") if "sentinel" in self.loader.resident_planes() else None
        if sentinel is not None:
            validations = [sentinel.validate(o) for o in fabric.workorders.context.active()]
            out["actions"]["sentinel"] = {"validated": len(validations),
                                            "blocked": sum(1 for v in validations if v.verdict == "block")}

        hospice = self.loader.get("hospice") if "hospice" in self.loader.resident_planes() else None
        if hospice is not None:
            healed = hospice.heal(fabric.backlog)
            out["actions"]["hospice"] = {"healed": len(healed)}

        blueprint = self.loader.get("blueprint") if "blueprint" in self.loader.resident_planes() else None
        if blueprint is not None and fabric.planning.active_plans():
            opt = blueprint.optimize(fabric.planning.active_plans()[0])
            out["actions"]["blueprint"] = {"critical_path": len(opt["critical_path"]),
                                            "lanes": len(opt["parallel_lanes"])}

        resonance = self.loader.get("resonance") if "resonance" in self.loader.resident_planes() else None
        if resonance is not None:
            out["actions"]["resonance"] = resonance.scan(fabric.queue)

        lens = self.loader.get("lens") if "lens" in self.loader.resident_planes() else None
        if lens is not None:
            lens.track(fabric.oracle.read())
            out["actions"]["lens"] = lens.calibration()

        ward = self.loader.get("ward") if "ward" in self.loader.resident_planes() else None
        if ward is not None:
            out["actions"]["ward"] = ward.audit(fabric.syntax.scan())

        # Agentic retrieval probe when RAG is live
        if self.agentic_rag is not None:
            out["agentic_rag"] = self.agentic_rag.stats()

        # Overseer: full oversight verdict
        verdict = self.overseer.oversight_cycle()
        out["verdict"] = verdict.to_dict()

        if self._bus:
            self._bus.publish(DomainEvent(
                topic="support.cycle.completed",
                payload={"loaded": out["loaded"], "state": verdict.state},
                correlation_id=f"support_{self._stats['cycles']}",
            ))
        return out

    def summary(self) -> Dict[str, Any]:
        return {
            "cycles": self._stats["cycles"],
            "loader": self.loader.stats(),
            "overseer": self.overseer.stats(),
            "agentic_rag": self.agentic_rag.stats() if self.agentic_rag else None,
        }


__all__ = [
    "SupportFabric",
    "SentinelContext",
    "HospiceContext",
    "BlueprintContext",
    "ResonanceContext",
    "LensContext",
    "WardContext",
    "LoadingQueue",
    "LoadRequest",
    "LoadedPlane",
    "AgenticRAG",
    "AgenticResult",
    "RetrievalPlan",
    "Overseer",
    "OverseerVerdict",
]
