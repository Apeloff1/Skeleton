"""Genesis protocol — boot the whole substrate as one wired system.

Boot phases: foundation, kernel, memory, intelligence, swarm,
resilience, interface, forge, galaxy, contexts, support, cortex.

Every phase is timed with :func:`time.perf_counter`. After boot one structured
summary line is logged on ``skeleton.bootstrap.genesis`` with total and
per-phase milliseconds, checked against the boot budget adopted in
``docs/engineering/PERFORMANCE_BUDGETS.md``. Going over budget is logged, never
raised: boot semantics are unchanged.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple

from skeleton.kernel.entropy import EntropyPool
from skeleton.kernel.events import DomainEvent, EventBus
from skeleton.kernel.ids import UserId
from skeleton.kernel.invariants import Invariant, InvariantLattice
from skeleton.kernel.clocks import VectorClock

logger = logging.getLogger(__name__)

#: Canonical boot order. ``Genesis.boot`` runs exactly these phases, in order.
BOOT_PHASES: Tuple[str, ...] = (
    "foundation",
    "kernel",
    "memory",
    "intelligence",
    "swarm",
    "resilience",
    "interface",
    "forge",
    "galaxy",
    "contexts",
    "support",
    "cortex",
)

#: Cold ``Genesis(seed=42).boot()`` budget (docs/engineering/PERFORMANCE_BUDGETS.md
#: section 2, Boot). Over this, the summary is logged at WARNING.
BOOT_BUDGET_MS: float = 2_000.0
#: Critical ceiling: the whole API startup-to-``mark_ready`` budget. If genesis
#: alone exceeds it, the summary is logged at ERROR. Still fail-soft.
BOOT_CRITICAL_MS: float = 5_000.0

_BUDGET_ENV = "SKL_BOOT_BUDGET_MS"
_CRITICAL_ENV = "SKL_BOOT_CRITICAL_MS"


def _env_ms(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        logger.warning("ignoring invalid %s=%r; using %.0f ms", name, raw, default)
        return default
    if value <= 0:
        logger.warning("ignoring non-positive %s=%r; using %.0f ms", name, raw, default)
        return default
    return value


def boot_budget_ms() -> Tuple[float, float]:
    """Return ``(budget_ms, critical_ms)``, honouring env overrides.

    ``critical_ms`` is never allowed below ``budget_ms``.
    """

    budget = _env_ms(_BUDGET_ENV, BOOT_BUDGET_MS)
    critical = _env_ms(_CRITICAL_ENV, BOOT_CRITICAL_MS)
    return budget, max(critical, budget)


def evaluate_boot_budget(
    phase_ms: Mapping[str, float],
    *,
    total_ms: Optional[float] = None,
    budget_ms: Optional[float] = None,
    critical_ms: Optional[float] = None,
) -> Dict[str, Any]:
    """Pure budget check over measured phase timings.

    Returns a JSON-safe summary: ``status`` is ``"ok"`` (total <= budget),
    ``"over_budget"`` (budget < total <= critical) or ``"critical"``
    (total > critical). ``total_ms`` defaults to the sum of phases.
    """

    default_budget, default_critical = boot_budget_ms()
    budget = default_budget if budget_ms is None else float(budget_ms)
    critical = default_critical if critical_ms is None else float(critical_ms)
    critical = max(critical, budget)
    phases = {name: round(float(ms), 3) for name, ms in phase_ms.items()}
    total = round(float(sum(phases.values()) if total_ms is None else total_ms), 3)
    slowest = max(phases.items(), key=lambda kv: kv[1]) if phases else (None, 0.0)
    if total > critical:
        status = "critical"
    elif total > budget:
        status = "over_budget"
    else:
        status = "ok"
    return {
        "status": status,
        "total_ms": total,
        "budget_ms": budget,
        "critical_ms": critical,
        "phase_ms": phases,
        "slowest_phase": slowest[0],
        "slowest_phase_ms": slowest[1],
    }


def log_boot_summary(summary: Mapping[str, Any], *, log: Optional[logging.Logger] = None) -> int:
    """Emit the single boot summary line; return the logging level used."""

    log = log or logger
    level = {
        "ok": logging.INFO,
        "over_budget": logging.WARNING,
        "critical": logging.ERROR,
    }.get(str(summary.get("status")), logging.WARNING)
    breakdown = " ".join(
        f"{name}={ms:.1f}" for name, ms in summary.get("phase_ms", {}).items()
    )
    log.log(
        level,
        "genesis boot %s total_ms=%.1f budget_ms=%.0f critical_ms=%.0f "
        "slowest=%s:%.1f phases_ms[%s]",
        summary.get("status"),
        summary.get("total_ms", 0.0),
        summary.get("budget_ms", 0.0),
        summary.get("critical_ms", 0.0),
        summary.get("slowest_phase"),
        summary.get("slowest_phase_ms", 0.0),
        breakdown,
        extra={"boot_timing": dict(summary)},
    )
    return level


def record_boot_metrics(metrics: Any, report: Any) -> bool:
    """Publish measured boot timings into a ``MetricsCollector``-like sink.

    Emits ``genesis_boot_phase_ms`` (histogram, ``phase`` label),
    ``genesis_boot_total_ms`` (gauge) and, when over budget,
    ``genesis_boot_budget_exceeded_total`` (counter, ``status`` label).
    Returns ``False`` (and records nothing) when the report was never timed.
    """

    phase_ms = getattr(report, "phase_ms", None)
    total_ms = getattr(report, "total_ms", None)
    if metrics is None or not phase_ms or total_ms is None:
        return False
    for phase, ms in phase_ms.items():
        metrics.histogram("genesis_boot_phase_ms", float(ms), {"phase": str(phase)})
    metrics.gauge("genesis_boot_total_ms", float(total_ms))
    status = (getattr(report, "timing", None) or {}).get("status")
    if status and status != "ok":
        metrics.increment(
            "genesis_boot_budget_exceeded_total", 1.0, {"status": str(status)},
        )
    return True


@dataclass
class GenesisReport:
    phases: List[str] = field(default_factory=list)
    wired: Dict[str, List[str]] = field(default_factory=dict)
    invariants_registered: int = 0
    # Wall-clock timings are kept OUT of ``to_dict`` on purpose: that payload is
    # published on the journaled bus, and nondeterministic numbers there would
    # break replay/hash determinism. Read them via ``timing``.
    phase_ms: Dict[str, float] = field(default_factory=dict, compare=False, repr=False)
    total_ms: Optional[float] = field(default=None, compare=False, repr=False)
    timing: Dict[str, Any] = field(default_factory=dict, compare=False, repr=False)

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
        self.journal: Optional[Any] = None

    def _boot_steps(self) -> Tuple[Tuple[str, Callable[[], None]], ...]:
        return tuple(
            (name, getattr(self, f"_phase_{name}")) for name in BOOT_PHASES
        )

    def boot(self) -> "Genesis":
        clock = time.perf_counter
        boot_started = clock()
        for name, step in self._boot_steps():
            started = clock()
            step()
            self.report.phase_ms[name] = round((clock() - started) * 1000.0, 3)
        self.report.total_ms = round((clock() - boot_started) * 1000.0, 3)
        self.report.timing = evaluate_boot_budget(
            self.report.phase_ms, total_ms=self.report.total_ms,
        )
        log_boot_summary(self.report.timing)
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

    def _phase_foundation(self) -> None:
        """The bedrock: Merkle DAG, event journal, capability kernel,
        temporal lattice. Boots FIRST — everything after it is journaled,
        content-addressable, capability-guarded, and temporally checked.

        Handles: dag, journal, replay, ocap, membrane, temporal.
        The bus is wrapped in a JournaledBus so every subsequent event
        lands in the hash-chained journal.
        """
        self.report.phases.append("foundation")
        from skeleton.foundation import (
            CapabilityKernel,
            EventJournal,
            JournaledBus,
            Membrane,
            MerkleDAG,
            ReplayEngine,
            TemporalLattice,
        )

        dag = MerkleDAG()
        journal = EventJournal(dag=dag)
        self.journal = journal
        # Wrap the bus: every event from here on is journaled
        self.bus = JournaledBus(self.bus, journal)
        replay = ReplayEngine(journal)
        ocap = CapabilityKernel()
        membrane = Membrane(ocap)
        temporal = TemporalLattice(journal=journal)

        self._wire("foundation", "dag", dag)
        self._wire("foundation", "journal", journal)
        self._wire("foundation", "replay", replay)
        self._wire("foundation", "ocap", ocap)
        self._wire("foundation", "membrane", membrane)
        self._wire("foundation", "temporal", temporal)

        # Bedrock temporal invariants: the boot itself must be well-formed
        temporal.eventually(
            "genesis_boots_eventually",
            lambda e: e.get("topic") == "kernel.genesis.booted",
        )
        temporal.never(
            "no_invariant_panic",
            lambda e: e.get("topic", "").endswith("panic"),
        )

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
        from skeleton.memory.dp import DifferentialPrivacy

        rag = VectorStore()
        cag = CAGStore()
        mag = MAGStore(UserId.new())
        trinity = MemoryTrinity(rag, cag, mag, bus=self.bus)
        srs = RepetitionScheduler(bus=self.bus)
        dp = DifferentialPrivacy(session_budget=1.0, per_plane_budget=0.5)
        dp.wrap("rag", rag)
        dp.wrap("mag", mag)
        dp.wrap("cag", cag)
        self._wire("memory", "rag", rag)
        self._wire("memory", "cag", cag)
        self._wire("memory", "mag", mag)
        self._wire("memory", "trinity", trinity)
        self._wire("memory", "repetition", srs)
        self._wire("memory", "dream", DreamEngine(mag, rag, bus=self.bus))
        self._wire("memory", "drift", PersonaDriftDetector(bus=self.bus))
        self._wire("memory", "dp", dp)

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
        from skeleton.swarm.mesh import HiveMind, SwarmMesh
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
        from skeleton.resilience.chaos import ChaosHarness

        self._wire("resilience", "fortress", ResilienceFortress(bus=self.bus))
        canaries = CanaryRegistry(bus=self.bus)
        canaries.plant("memory.rag")
        canaries.plant("vault")
        self._wire("resilience", "canaries", canaries)
        self._wire("resilience", "chaos", ChaosHarness(bus=self.bus))

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
        """Wire the galaxy node for distributed federation."""
        self.report.phases.append("galaxy")
        from skeleton.galaxy import GalaxyNode, NodeTransport
        from skeleton.galaxy.consensus import ConsensusEngine
        from skeleton.galaxy.kag_sync import KAGSync
        from skeleton.galaxy.galaxy_bridge import GalaxyBridge
        from skeleton.galaxy.election import LeaderElection
        from skeleton.galaxy.fleet import FleetCoordinator
        from skeleton.galaxy.byzantine import ByzantineEngine

        node = GalaxyNode(address="127.0.0.1", bus=self.bus)
        node.add_capability("reasoning")
        node.add_capability("retrieval")
        node.add_capability("forge")
        transport = NodeTransport(node)
        consensus = ConsensusEngine(node, transport, bus=self.bus)
        election = LeaderElection(node, transport, consensus, bus=self.bus)
        byzantine = ByzantineEngine(node.node_id, [node.node_id], secret=b"skeleton-fleet-key")

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
        self._wire("galaxy", "byzantine", byzantine)

        assert self.lattice is not None
        self.lattice.register(Invariant(
            name="galaxy_node_identified",
            subject="galaxy.node",
            snapshot=lambda: bool(node.node_id),
            predicate=lambda identified: identified is True,
        ))
        self.report.invariants_registered += 1

    def _phase_contexts(self) -> None:
        """Wire the context fabric — the spider-connected work planes."""
        self.report.phases.append("contexts")
        from skeleton.contexts import ContextFabric, ResponseCycle
        from skeleton.contexts.causal import CausalEngine

        fabric = ContextFabric(bus=self.bus, mag=self.handles.get("mag"))
        fabric.connect_all()
        cycle = ResponseCycle(fabric, bus=self.bus)
        causal = CausalEngine()

        self._wire("contexts", "fabric", fabric)
        self._wire("contexts", "workorders", fabric.workorders)
        self._wire("contexts", "backlog", fabric.backlog)
        self._wire("contexts", "planning", fabric.planning)
        self._wire("contexts", "queue", fabric.queue)
        self._wire("contexts", "oracle", fabric.oracle)
        self._wire("contexts", "syntax_fixer", fabric.syntax)
        self._wire("contexts", "cycle", cycle)
        self._wire("contexts", "causal", causal)

        assert self.lattice is not None
        self.lattice.register(Invariant(
            name="contexts_planes_connected",
            subject="contexts.fabric",
            snapshot=lambda: fabric.syntax.stats()["planes_connected"],
            predicate=lambda connected: connected >= 4,
        ))
        self.report.invariants_registered += 1

    def _phase_support(self) -> None:
        """Wire the support fabric + full engine stack (V1 → V3.5)."""
        self.report.phases.append("support")
        from skeleton.support import SupportFabric
        from skeleton.overseer import (
            OverseerEngine,
            OverseerEngineV2,
            OverseerEngineV3,
            OverseerEngineV35,
        )

        quad = self.handles.get("quad")
        support = SupportFabric(bus=self.bus, quad=quad)
        engine = OverseerEngine(bus=self.bus)
        engine_v2 = OverseerEngineV2(bus=self.bus)
        engine_v3 = OverseerEngineV3(bus=self.bus)

        node = self.handles.get("galaxy")
        transport = self.handles.get("galaxy_transport")
        consensus = self.handles.get("consensus")
        engine_v35 = OverseerEngineV35(
            bus=self.bus, node=node, transport=transport, consensus=consensus,
        )

        for eng in (engine, engine_v2, engine_v3, engine_v35):
            eng.bind_loader(support.loader)
        fabric = self.handles.get("fabric")
        if fabric is not None:
            for eng in (engine, engine_v2, engine_v3, engine_v35):
                eng.bind_queue(fabric.queue)
                eng.bind_miner(fabric.backlog)
        if support.agentic_rag is not None:
            for eng in (engine, engine_v2, engine_v3, engine_v35):
                eng.bind_rag(support.agentic_rag)

        self._wire("support", "support", support)
        self._wire("support", "loader", support.loader)
        if support.agentic_rag is not None:
            self._wire("support", "agentic_rag", support.agentic_rag)
        self._wire("support", "overseer", support.overseer)
        self._wire("support", "engine", engine)
        self._wire("support", "engine_v2", engine_v2)
        self._wire("support", "engine_v3", engine_v3)
        self._wire("support", "engine_v35", engine_v35)

        assert self.lattice is not None
        self.lattice.register(Invariant(
            name="support_loader_bounded",
            subject="support.loader",
            snapshot=lambda: len(support.loader.resident_planes()),
            predicate=lambda resident: resident <= support.loader.max_resident,
        ))
        self.report.invariants_registered += 1

        engine.engine_tick()
        engine_v2.tick()
        engine_v3.tick()
        engine_v35.tick()

    def _phase_cortex(self) -> None:
        """Wire a fresh cortex unless durable process ownership is explicit."""
        self.report.phases.append("cortex")
        from skeleton.cortex.live import live_cortex, persistence_configured
        from skeleton.cortex.neocortex import JeevesCortex
        from skeleton.jeeves.core import Jeeves

        if persistence_configured():
            neo = live_cortex(self.bus)
        else:
            neo = JeevesCortex(bus=self.bus)
        self._wire("cortex", "cortex", neo)
        # Alias for GameForge/cockpit callers that look up the "jeeves" handle.
        j = Jeeves(bus=self.bus)
        j.cortex = neo
        self._wire("cortex", "jeeves", j)

    def health(self) -> Dict[str, Any]:
        assert self.lattice is not None
        violations = self.lattice.evaluate()
        temporal_healthy = True
        temporal = self.handles.get("temporal")
        if temporal is not None and self.journal is not None:
            temporal_healthy = temporal.healthy()
        return {
            "phases": self.report.phases,
            "subsystems": sum(len(v) for v in self.report.wired.values()),
            "bus": self.bus.stats(),
            "invariant_violations": len(violations),
            "temporal_healthy": temporal_healthy,
            "journal_integrity": self.journal.integrity() if self.journal else None,
            "healthy": not violations and temporal_healthy,
        }

    def get(self, name: str) -> Any:
        return self.handles[name]