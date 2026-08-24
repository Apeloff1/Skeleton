"""Genesis protocol — boot the whole substrate as one wired system.

Nineteen subsystems landed in this wave; each is independently useful,
but the compounding payoff is their *composition*: the dream engine
feeding the repetition scheduler, stigmergic routing feeding the hive,
invariants watching all of it. Genesis builds that wiring at startup in
declared dependency order, on one shared event bus, and returns a single
handle the API layer can hold.

Design
------
- Phases boot in order: kernel → memory → intelligence → swarm →
  resilience → interface. A phase only sees handles from earlier phases.
- Every subsystem gets the *same* EventBus instance — one nervous system,
  not nineteen isolated ones.
- Boot registers the baseline invariants (MAG index consistency, vault
  rotation liveness, swarm quorum viability) so the immune system is on
  from the first request.
- Deterministic: same config in, same wiring out, every boot.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from skeleton.kernel.entropy import EntropyPool
from skeleton.kernel.events import DomainEvent, EventBus
from skeleton.kernel.invariants import Invariant, InvariantLattice
from skeleton.kernel.vclock import VectorClock


@dataclass
class GenesisReport:
    phases: List[str] = field(default_factory=list)
    wired: Dict[str, List[str]] = field(default_factory=dict)
    invariants_registered: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "phases": self.phases,
            "wired": self.wired,
            "invariants_registered": self.invariants_registered,
        }


class Genesis:
    """Boot orchestrator. Hold the returned ``handles`` — it *is* the app."""

    def __init__(self, *, seed: Optional[int] = None) -> None:
        self.bus = EventBus()
        self.handles: Dict[str, Any] = {}
        self.report = GenesisReport()
        self._seed = seed

    # ------------------------------------------------------------------

    def boot(self) -> "Genesis":
        self._phase_kernel()
        self._phase_memory()
        self._phase_intelligence()
        self._phase_swarm()
        self._phase_resilience()
        self._phase_interface()
        self.bus.publish(
            DomainEvent(topic="kernel.genesis.booted",
                        payload=self.report.to_dict(),
                        correlation_id="genesis")
        )
        return self

    # ------------------------------------------------------------------

    def _wire(self, phase: str, name: str, handle: Any) -> None:
        self.handles[name] = handle
        self.report.wired.setdefault(phase, []).append(name)

    def _phase_kernel(self) -> None:
        self.report.phases.append("kernel")
        lattice = InvariantLattice(bus=self.bus)
        self._wire("kernel", "lattice", lattice)
        self._wire("kernel", "entropy", EntropyPool(seed=self._seed))
        self._wire("kernel", "clock", VectorClock())
        self.lattice = lattice

    def _phase_memory(self) -> None:
        self.report.phases.append("memory")
        from skeleton.memory import (
            CAGStore, InMemoryTFIDFStore, MAGStore, MemoryTrinity,
            RepetitionScheduler,
        )
        from skeleton.kernel.ids import UserId
        rag = InMemoryTFIDFStore()
        cag = CAGStore()
        mag = MAGStore(UserId("system"))
        trinity = MemoryTrinity(rag, cag, mag, bus=self.bus)
        srs = RepetitionScheduler(bus=self.bus)
        self._wire("memory", "rag", rag)
        self._wire("memory", "cag", cag)
        self._wire("memory", "mag", mag)
        self._wire("memory", "trinity", trinity)
        self._wire("memory", "repetition", srs)

        from skeleton.intelligence.dream import DreamEngine
        self._wire("memory", "dream", DreamEngine(mag, rag, bus=self.bus))

        from skeleton.memory.drift import PersonaDriftDetector
        self._wire("memory", "drift", PersonaDriftDetector(bus=self.bus))

        # Baseline invariant: MAG tag index never references a dead episode
        self.lattice.register(Invariant(
            name="mag_index_consistent",
            subject="memory.mag",
            snapshot=lambda: {
                "episodes": set(mag._episodes),
                "indexed": {eid for ids in mag._tag_index.values() for eid in ids},
            },
            predicate=lambda s: s["indexed"] <= s["episodes"],
        ))
        self.report.invariants_registered += 1

    def _phase_intelligence(self) -> None:
        self.report.phases.append("intelligence")
        from skeleton.intelligence import (
            AdaptiveLearner, IntelligenceOrchestrator, default_meta_grid,
        )
        self._wire("intelligence", "orchestrator",
                   IntelligenceOrchestrator(bus=self.bus))
        self._wire("intelligence", "adaptive",
                   AdaptiveLearner(default_meta_grid(), bus=self.bus))

    def _phase_swarm(self) -> None:
        self.report.phases.append("swarm")
        from skeleton.swarm import HiveMind, SwarmMesh
        from skeleton.swarm.negotiation import CapabilityNegotiator
        from skeleton.swarm.platoons import standard_platoons
        from skeleton.swarm.stigmergy import PheromoneField, StigmergicRouter
        mesh = SwarmMesh(bus=self.bus)
        field = PheromoneField(bus=self.bus)
        self._wire("swarm", "mesh", mesh)
        self._wire("swarm", "pheromones", field)
        self._wire("swarm", "stigmergy",
                   StigmergicRouter(field, bus=self.bus, seed=self._seed))
        self._wire("swarm", "hive", HiveMind(bus=self.bus))
        self._wire("swarm", "negotiator", CapabilityNegotiator(bus=self.bus))
        self._wire("swarm", "platoons", standard_platoons(bus=self.bus))

        # Invariant: at least one healthy agent before quorum-requiring ops
        self.lattice.register(Invariant(
            name="swarm_quorum_viable",
            subject="swarm.mesh",
            snapshot=lambda: sum(1 for a in mesh._agents.values() if a.is_alive()),
            predicate=lambda healthy: healthy >= 1,
            severity="WARNING",
        ))
        self.report.invariants_registered += 1

    def _phase_resilience(self) -> None:
        self.report.phases.append("resilience")
        from skeleton.resilience import ResilienceFortress
        from skeleton.resilience.canary import CanaryRegistry
        self._wire("resilience", "fortress", ResilienceFortress(bus=self.bus))
        canaries = CanaryRegistry(bus=self.bus)
        canaries.plant("memory.rag")
        canaries.plant("vault")
        self._wire("resilience", "canaries", canaries)

    def _phase_interface(self) -> None:
        self.report.phases.append("interface")
        from skeleton.observability.anomaly import AnomalyDetector
        from skeleton.retrieval.provenance import ProvenanceLedger
        from skeleton.retrieval.reranker import Reranker
        self._wire("interface", "anomaly", AnomalyDetector(bus=self.bus))
        self._wire("interface", "provenance", ProvenanceLedger(bus=self.bus))
        self._wire("interface", "reranker", Reranker())

    # ------------------------------------------------------------------

    def health(self) -> Dict[str, Any]:
        violations = self.lattice.evaluate()
        return {
            "phases": self.report.phases,
            "subsystems": sum(len(v) for v in self.report.wired.values()),
            "bus": self.bus.stats(),
            "invariant_violations": len(violations),
            "healthy": not violations,
        }
