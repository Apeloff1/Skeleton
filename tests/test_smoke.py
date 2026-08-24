"""Smoke tests: every public package surface imports and constructs.

These tests exist to catch exactly the class of breakage found in v16.1 —
an API layer referencing modules, classes, or constructor signatures that
no longer exist after a package split. If any subsystem's public surface
changes, these tests fail at import/call time, not in production.
"""
from __future__ import annotations


def test_kernel_surface_imports() -> None:
    from skeleton.kernel import (  # noqa: F401
        EventBus,
        DomainEvent,
        SkeletonError,
        CapabilityRegistry,
        VectorClock,
        CircuitBreaker,
        Supervisor,
    )


def test_agents_surface_imports() -> None:
    from skeleton.agents.ledger import ActivityLedger  # noqa: F401
    from skeleton.agents.mesh import AgentMesh  # noqa: F401
    from skeleton.agents.scheduler import SwarmScheduler  # noqa: F401


def test_memory_surface_imports() -> None:
    from skeleton.memory import (  # noqa: F401
        CAGStore,
        ChromaDBStore,
        InMemoryTFIDFStore,
        MAGStore,
        MemoryTrinity,
    )


def test_intelligence_surface_imports() -> None:
    from skeleton.intelligence import (  # noqa: F401
        IntelligenceOrchestrator,
        TemporalReasoner,
        CausalInference,
        MetaLearner,
        NeuralSymbolicEngine,
        EconomicOptimiser,
        DreamEngine,
    )


def test_jeeves_surface_imports() -> None:
    from skeleton.jeeves.core import Jeeves, SessionMode  # noqa: F401
    from skeleton.jeeves.matrices import SamMatrix, ClomMatrix, KremMatrix  # noqa: F401
    from skeleton.jeeves.rag import RagMemory  # noqa: F401


def test_forge_and_pipelines_import() -> None:
    from skeleton.forge.universal import Forge  # noqa: F401
    from skeleton.pipelines.npc import NpcPipeline  # noqa: F401
    from skeleton.pipelines.game_logic import GameLogicPipeline  # noqa: F401
    from skeleton.pipelines.animation import AnimationPipeline  # noqa: F401


def test_api_package_imports_create_app() -> None:
    from skeleton.api import create_app  # noqa: F401


def test_create_app_builds() -> None:
    from skeleton.api import create_app

    app = create_app()
    assert app.title == "Skeleton"
    assert app.version == "16.2.0"
    paths = {r.path for r in app.routes}
    assert "/health" in paths
    assert "/api/v1/capabilities" in paths
    assert "/api/v1/pipeline/npc" in paths
