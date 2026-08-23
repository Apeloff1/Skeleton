"""
================================================================================
skeleton.api.server — Unified Application Factory
================================================================================
FastAPI application factory wiring every subsystem into a cohesive surface:
  - Kernel: errors, events, ids, registry
  - Memory: RAG/CAG/MAG trinity
  - Agents: swarm mesh with consensus, auction, chaos
  - Resilience: adversarial fortress with shadow mode
  - Intelligence: temporal, causal, meta-learning, neuro-symbolic, economic
  - Jeeves: tutor core, matrices, RAG
  - Forge: universal blueprint synthesis
  - Pipelines: NPC, game-logic, animation

Design invariants:
  1. create_app() returns a fully configured FastAPI instance with lifespan management.
  2. All subsystems are instantiated in lifespan startup and disposed in shutdown.
  3. Error → HTTP mapping is deterministic and exhaustive.
  4. Request-id middleware traces every call through the event bus.
  5. Health endpoint reports per-subsystem status.
================================================================================
"""
from __future__ import annotations

import time
import uuid
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Dict, Optional

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from skeleton.config.settings import Settings, get_settings
from skeleton.kernel.errors import SkeletonError, http_status_for
from skeleton.kernel.events import EventBus
from skeleton.kernel.ids import AgentId, UserId
from skeleton.kernel.registry import CapabilityRegistry

from skeleton.agents.ledger import ActivityLedger
from skeleton.agents.mesh import SwarmMesh
from skeleton.agents.scheduler import SwarmScheduler

from skeleton.memory import (
    CAGStore, ChromaDBStore, MAGStore, MemoryTrinity,
)

from skeleton.resilience import ResilienceFortress

from skeleton.intelligence_part1 import TemporalReasoner, CausalInference
from skeleton.intelligence_part2 import (
    IntelligenceOrchestrator, MetaLearner, NeuralSymbolicEngine, EconomicOptimiser,
)

from skeleton.jeeves.core import JeevesCore
from skeleton.jeeves.matrices import SAM, CLOM, KREM
from skeleton.jeeves.rag import JeevesRAG

from skeleton.forge.universal import UniversalForge

from skeleton.pipelines.npc import NpcPipeline
from skeleton.pipelines.game_logic import GameLogicPipeline
from skeleton.pipelines.animation import AnimationPipeline


# =============================================================================
# APPLICATION STATE
# =============================================================================

class AppState:
    """Holds all subsystem instances for dependency injection."""

    def __init__(self) -> None:
        self.settings: Optional[Settings] = None
        self.bus: Optional[EventBus] = None
        self.registry: Optional[CapabilityRegistry] = None
        self.ledger: Optional[ActivityLedger] = None
        self.mesh: Optional[SwarmMesh] = None
        self.scheduler: Optional[SwarmScheduler] = None
        self.memory_trinity: Optional[MemoryTrinity] = None
        self.resilience: Optional[ResilienceFortress] = None
        self.intelligence: Optional[IntelligenceOrchestrator] = None
        self.jeeves: Optional[JeevesCore] = None
        self.forge: Optional[UniversalForge] = None
        self.npc_pipeline: Optional[NpcPipeline] = None
        self.game_logic_pipeline: Optional[GameLogicPipeline] = None
        self.animation_pipeline: Optional[AnimationPipeline] = None
        self.started_at: Optional[float] = None

    def is_healthy(self) -> Dict[str, Any]:
        checks = {
            "kernel": self.bus is not None and self.registry is not None,
            "memory": self.memory_trinity is not None,
            "agents": self.mesh is not None and self.scheduler is not None,
            "resilience": self.resilience is not None,
            "intelligence": self.intelligence is not None,
            "jeeves": self.jeeves is not None,
            "forge": self.forge is not None,
            "pipelines": all([
                self.npc_pipeline is not None,
                self.game_logic_pipeline is not None,
                self.animation_pipeline is not None,
            ]),
        }
        checks["overall"] = all(checks.values())
        return checks


# Global state container (managed by lifespan)
_app_state = AppState()


def get_state() -> AppState:
    return _app_state


# =============================================================================
# LIFESPAN
# =============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Startup and shutdown lifecycle."""
    state = get_state()
    state.settings = get_settings()
    state.bus = EventBus(history_size=10000)
    state.registry = CapabilityRegistry(bus=state.bus)
    state.ledger = ActivityLedger()
    state.mesh = SwarmMesh(bus=state.bus)
    state.scheduler = SwarmScheduler(bus=state.bus)

    # Memory trinity
    rag = ChromaDBStore(collection_name="skeleton_rag")
    cag = CAGStore()
    mag = MAGStore(user_id=UserId.generate())
    state.memory_trinity = MemoryTrinity(rag=rag, cag=cag, mag=mag, bus=state.bus)

    # Resilience fortress
    state.resilience = ResilienceFortress(bus=state.bus)

    # Intelligence orchestrator
    state.intelligence = IntelligenceOrchestrator(bus=state.bus)

    # Jeeves brain
    state.jeeves = JeevesCore(
        bus=state.bus,
        memory=state.memory_trinity,
        sam=SAM(),
        clom=CLOM(),
        krem=KREM(),
    )

    # Forge
    state.forge = UniversalForge(bus=state.bus, registry=state.registry)

    # Pipelines
    state.npc_pipeline = NpcPipeline(bus=state.bus, mesh=state.mesh)
    state.game_logic_pipeline = GameLogicPipeline(bus=state.bus, mesh=state.mesh)
    state.animation_pipeline = AnimationPipeline(bus=state.bus, mesh=state.mesh)

    state.started_at = time.time()

    # Emit startup event
    state.bus.publish(
        EventBus.DomainEvent(
            topic="system.startup",
            payload={"version": "16.1.0", "subsystems": list(state.is_healthy().keys())},
            correlation_id=str(uuid.uuid4()),
        )
    )

    yield

    # Shutdown
    if state.bus:
        state.bus.close()


# =============================================================================
# ERROR HANDLERS
# =============================================================================

async def skeleton_error_handler(request: Request, exc: SkeletonError) -> JSONResponse:
    return JSONResponse(
        status_code=http_status_for(exc),
        content=exc.to_dict(),
    )


# =============================================================================
# MIDDLEWARE
# =============================================================================

async def request_id_middleware(request: Request, call_next: Any) -> Any:
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    start = time.time()
    response = await call_next(request)
    duration = time.time() - start
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Response-Time"] = f"{duration:.3f}s"
    return response


# =============================================================================
# APP FACTORY
# =============================================================================

def create_app() -> FastAPI:
    app = FastAPI(
        title="Skeleton",
        description="Tutolage AI Platform — v16.1 Frontier",
        version="16.1.0",
        lifespan=lifespan,
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Custom middleware
    app.middleware("http")(request_id_middleware)

    # Exception handlers
    app.add_exception_handler(SkeletonError, skeleton_error_handler)

    # Include routers
    from skeleton.api.routes import router
    app.include_router(router, prefix="/api/v1")

    @app.get("/health")
    async def health() -> Dict[str, Any]:
        state = get_state()
        checks = state.is_healthy()
        return {
            "status": "healthy" if checks["overall"] else "degraded",
            "checks": checks,
            "uptime_seconds": time.time() - state.started_at if state.started_at else 0,
        }

    @app.get("/")
    async def root() -> Dict[str, str]:
        return {"name": "Skeleton", "version": "16.1.0", "status": "operational"}

    return app
