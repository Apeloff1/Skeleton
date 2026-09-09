"""Genesis protocol — boot the whole substrate as one wired system.

Boot phases: kernel, memory, intelligence, swarm, resilience,
interface, forge, galaxy, contexts, cortex.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from skeleton.kernel.entropy import EntropyPool
from skeleton.kernel.events import DomainEvent, EventBus
from skeleton.kernel.ids import UserId
from skeleton.kernel.invariants import Invariant, InvariantLattice
from skeleton.kernel.clocks import VectorClock


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
    """Boot orchestrator. Hold the returned handles — it is the app."""

    def __init__(self, *, seed: Optional[int] = None) -> None:
        self.bus = EventBus()
        self.handles: Dict[str, Any] = {}
        self.report = GenesisReport()
        self._seed = seed
        self.lattice: InvariantLattice | None = None

    def boot(self) -> "Genesis":
        self._phase_kernel()
        self._phase_memory()
        self._phase_intelligence()
        self._phase_swarm()
        self._phase_resilience()
        self._phase_interface()
        self._phase_forge()
        self._phase_galaxy()
        self._phase_contexts()
        self._phase_cortex()
        self.bus.publish(
            DomainEvent(
                topic="kernel.genesis.booted",
                payload=self.report.to_dict(),
                correlation_id="genesis",
            )
        )
        return self

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
        from skeleton.intelligence.dream import DreamEngine
        from skeleton.memory import (
            CAGStore,
            MAGStore,
            MemoryTrinity,
            RepetitionScheduler,
        )
        from skeleton.memory.vector import VectorStore
        from skeleton.memory.drift import PersonaDriftDetector

        rag = VectorStore()
        cag = CAGStore()
        mag = MAGStore(UserId.new())
        trinity = MemoryTrinity(rag, cag, mag, bus=self.bus)
        srs = RepetitionScheduler(bus=self.bus)
        self._wire("memory", "rag", rag)
        self._wire("memory", "cag", cag)
        self._wire("memory", "mag", mag)
        self._wire("memory", "trinity", trinity)
        self._wire("memory", "repetition", srs)
        self._wire("memory", "dream", DreamEngine(mag, rag, bus=self.bus))
        self._wire("memory", "drift", PersonaDriftDetector(bus=self.bus))

        assert self.lattice is not None
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
            AdaptiveLearner,
            IntelligenceOrchestrator,
            default_meta_grid,
        )
        self._wire("intelligence", "orchestrator", IntelligenceOrchestrator(bus=self.bus))
        self._wire("intelligence", "adaptive", AdaptiveLearner(default_meta_grid(), bus=self.bus))

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
        self._wire("swarm", "stigmergy", StigmergicRouter(field, bus=self.bus, seed=self._seed))
        self._wire("swarm", "hive", HiveMind(bus=self.bus))
        self._wire("swarm", "negotiator", CapabilityNegotiator(bus=self.bus))
        self._wire("swarm", "platoons", standard_platoons(bus=self.bus))

        from skeleton.agents import Coordinator
        from skeleton.agents.bridge import MeshBridge
        coordinator = Coordinator(bus=self.bus)
        bridge = MeshBridge(mesh, bus=self.bus)
        self._wire("swarm", "coordinator", coordinator)
        self._wire("swarm", "bridge", bridge)

        assert self.lattice is not None
        self.lattice.register(Invariant(
            name="swarm_quorum_viable",
            subject="swarm.mesh",
            snapshot=lambda: sum(1 for a in mesh._agents.values() if a.is_alive()),
            predicate=lambda healthy: healthy >= 0,
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
        from skeleton.retrieval.quad import QuadRetriever
        from skeleton.retrieval.reranker import FeatureReranker
        from skeleton.retrieval.kag import KAGRetriever
        from skeleton.retrieval.ranking import Ranker

        anomaly = AnomalyDetector(bus=self.bus)
        provenance = ProvenanceLedger(bus=self.bus)
        reranker = FeatureReranker(bus=self.bus)
        ranker = Ranker()

        quad = QuadRetriever(bus=self.bus)
        quad.register_plane("rag", self.handles.get("rag"))
        quad.register_plane("cag", self.handles.get("cag"))
        quad.register_plane("mag", self.handles.get("mag"))
        quad.register_plane("kag", KAGRetriever())

        self._wire("interface", "anomaly", anomaly)
        self._wire("interface", "provenance", provenance)
        self._wire("interface", "reranker", reranker)
        self._wire("interface", "ranker", ranker)
        self._wire("interface", "quad", quad)

    def _phase_forge(self) -> None:
        """Wire the universal forge as a first-class genesis handle."""
        self.report.phases.append("forge")
        from skeleton.forge.universal import Forge

        forge = Forge(bus=self.bus)
        self._wire("forge", "forge", forge)

        assert self.lattice is not None
        self.lattice.register(Invariant(
            name="forge_kinds_registered",
            subject="forge",
            snapshot=lambda: len(forge.available_kinds()),
            predicate=lambda kinds: kinds >= 5,
        ))
        self.report.invariants_registered += 1

    def _phase_galaxy(self) -> None:
        """Wire the galaxy node for distributed federation.

        Handles: galaxy node, transport, consensus, kag_sync,
        galaxy_bridge, leader election, and fleet coordinator.
        """
        self.report.phases.append("galaxy")
        from skeleton.galaxy import GalaxyNode, NodeTransport
        from skeleton.galaxy.consensus import ConsensusEngine
        from skeleton.galaxy.kag_sync import KAGSync
        from skeleton.galaxy.galaxy_bridge import GalaxyBridge
        from skeleton.galaxy.election import LeaderElection
        from skeleton.galaxy.fleet import FleetCoordinator

        node = GalaxyNode(address="127.0.0.1", bus=self.bus)
        node.add_capability("reasoning")
        node.add_capability("retrieval")
        node.add_capability("forge")
        transport = NodeTransport(node)
        consensus = ConsensusEngine(node, transport, bus=self.bus)
        election = LeaderElection(node, transport, consensus, bus=self.bus)

        quad = self.handles.get("quad")
        kag_sync = None
        if quad is not None:
            kag = quad._planes.get("kag")
            if kag is not None:
                kag_sync = KAGSync(kag, node, transport, consensus=consensus, bus=self.bus)
                self._wire("galaxy", "kag_sync", kag_sync)

        mesh_bridge = self.handles.get("bridge")
        if mesh_bridge is not None:
            galaxy_bridge = GalaxyBridge(mesh_bridge, node, transport, bus=self.bus)
            self._wire("galaxy", "galaxy_bridge", galaxy_bridge)

        fleet = FleetCoordinator(node, transport, election, kag_sync=kag_sync, bus=self.bus)

        self._wire("galaxy", "galaxy", node)
        self._wire("galaxy", "galaxy_transport", transport)
        self._wire("galaxy", "consensus", consensus)
        self._wire("galaxy", "election", election)
        self._wire("galaxy", "fleet", fleet)

        assert self.lattice is not None
        self.lattice.register(Invariant(
            name="galaxy_node_identified",
            subject="galaxy.node",
            snapshot=lambda: bool(node.node_id),
            predicate=lambda identified: identified is True,
        ))
        self.report.invariants_registered += 1

    def _phase_contexts(self) -> None:
        """Wire the context fabric — the spider-connected work planes.

        Sits after galaxy (connectors live) and before cortex (so cortex
        observes every context event). Handles:
        - fabric: the ContextFabric spider web (workorders, backlog,
          planning, queue, oracle, syntax — all connected)
        - workorders: the WorkOrderEngine for external-tool parsing
        - backlog: the BacklogContext with tensor cubes + work chain
        - planning: the PlanningContext for goal decomposition
        - queue: the QueByPriority 18-system adaptive queue
        - oracle: the OracleMatrix for fate-string guidance
        - syntax_fixer: the ContextSyntaxFixer spider repair engine
        """
        self.report.phases.append("contexts")
        from skeleton.contexts import ContextFabric

        fabric = ContextFabric(bus=self.bus, mag=self.handles.get("mag"))
        fabric.connect_all()

        self._wire("contexts", "fabric", fabric)
        self._wire("contexts", "workorders", fabric.workorders)
        self._wire("contexts", "backlog", fabric.backlog)
        self._wire("contexts", "planning", fabric.planning)
        self._wire("contexts", "queue", fabric.queue)
        self._wire("contexts", "oracle", fabric.oracle)
        self._wire("contexts", "syntax_fixer", fabric.syntax)

        assert self.lattice is not None
        self.lattice.register(Invariant(
            name="contexts_planes_connected",
            subject="contexts.fabric",
            snapshot=lambda: fabric.syntax.stats()["planes_connected"],
            predicate=lambda connected: connected >= 4,
        ))
        self.report.invariants_registered += 1

    def _phase_cortex(self) -> None:
        """The Jeeves neocortex — wired last so it can observe the whole bus."""
        self.report.phases.append("cortex")
        from skeleton.cortex.neocortex import JeevesCortex

        self._wire("cortex", "cortex", JeevesCortex(bus=self.bus))

    def health(self) -> Dict[str, Any]:
        assert self.lattice is not None
        violations = self.lattice.evaluate()
        return {
            "phases": self.report.phases,
            "subsystems": sum(len(v) for v in self.report.wired.values()),
            "bus": self.bus.stats(),
            "invariant_violations": len(violations),
            "healthy": not violations,
        }

    def get(self, name: str) -> Any:
        return self.handles[name]
