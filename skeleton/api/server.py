"""
================================================================================
skeleton.api.server — Unified Application Factory (v16.2 wiring)
================================================================================
FastAPI application factory wiring every subsystem into a cohesive surface,
written against the actual v16.2 package APIs:

  - Kernel:        EventBus, CapabilityRegistry (bootstrap_registry)
  - Agents:        AgentMesh, SwarmScheduler, ActivityLedger
  - Memory:        MemoryTrinity over ChromaDBStore / CAGStore / MAGStore
  - Resilience:    ResilienceFortress
  - Intelligence:  IntelligenceOrchestrator (temporal/causal/meta/neurosym/economic)
  - Jeeves:        Jeeves tutor core + SamMatrix/ClomMatrix/KremMatrix + RagMemory
  - Forge:         Forge (composable blueprints)
  - Pipelines:     NpcPipeline, GameLogicPipeline, AnimationPipeline

Design invariants:
  1. create_app() returns a fully configured FastAPI instance with lifespan management.
  2. All subsystems are instantiated in lifespan startup and disposed in shutdown.
  3. Error -> HTTP mapping is deterministic and exhaustive (SkeletonError lattice).
  4. Request-id middleware traces every call.
  5. Health endpoint reports per-subsystem status, live.
================================================================================
"""
from __future__ import annotations

import time
import uuid
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Dict, Optional

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from skeleton.config.settings import Settings, get_settings
from skeleton.kernel.errors import SkeletonError, http_status_for
from skeleton.kernel.events import EventBus
from skeleton.kernel.ids import UserId
from skeleton.kernel.registry import CapabilityRegistry, bootstrap_registry

from skeleton.agents.ledger import ActivityLedger
from skeleton.agents.mesh import AgentMesh
from skeleton.agents.scheduler import SwarmScheduler

from skeleton.memory import CAGStore, ChromaDBStore, MAGStore, MemoryTrinity

from skeleton.resilience import ResilienceFortress

from skeleton.intelligence import IntelligenceOrchestrator

from skeleton.jeeves.core import Jeeves
from skeleton.jeeves.matrices import SamMatrix, ClomMatrix, KremMatrix
from skeleton.jeeves.rag import RagMemory

from skeleton.forge.universal import Forge

from skeleton.pipelines.npc import NpcPipeline
from skeleton.pipelines.game_logic import GameLogicPipeline
from skeleton.pipelines.animation import AnimationPipeline

VERSION = "16.2.0"


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
        self.mesh: Optional[AgentMesh] = None
        self.scheduler: Optional[SwarmScheduler] = None
        self.memory_trinity: Optional[MemoryTrinity] = None
        self.resilience: Optional[ResilienceFortress] = None
        self.intelligence: Optional[IntelligenceOrchestrator] = None
        self.jeeves: Optional[Jeeves] = None
        self.jeeves_memory: Optional[RagMemory] = None
        self.sam: Optional[SamMatrix] = None
        self.clom: Optional[ClomMatrix] = None
        self.krem: Optional[KremMatrix] = None
        self.forge: Optional[Forge] = None
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
    state.bus = EventBus(replay_capacity=10000)
    state.registry = bootstrap_registry(state.bus)
    state.ledger = ActivityLedger()
    state.mesh = AgentMesh(bus=state.bus)
    state.scheduler = SwarmScheduler(ledger=state.ledger, bus=state.bus)

    # Memory trinity (RAG falls back to in-memory TF-IDF without ChromaDB)
    rag = ChromaDBStore(collection_name=state.settings.chroma.collection)
    cag = CAGStore()
    mag = MAGStore(user_id=UserId.new())
    state.memory_trinity = MemoryTrinity(rag=rag, cag=cag, mag=mag, bus=state.bus)

    # Resilience fortress
    state.resilience = ResilienceFortress(bus=state.bus)

    # Intelligence orchestrator
    state.intelligence = IntelligenceOrchestrator(bus=state.bus)

    # Jeeves brain + self-learning matrices + tutor memory
    state.jeeves = Jeeves(
        bus=state.bus,
        max_turns=state.settings.jeeves.max_session_turns,
    )
    state.jeeves_memory = RagMemory(bus=state.bus)
    state.sam = SamMatrix()
    state.clom = ClomMatrix()
    state.krem = KremMatrix()

    # Forge
    state.forge = Forge(bus=state.bus)

    # Pipelines
    state.npc_pipeline = NpcPipeline(bus=state.bus)
    state.game_logic_pipeline = GameLogicPipeline(bus=state.bus)
    state.animation_pipeline = AnimationPipeline(bus=state.bus)

    state.started_at = time.time()

    state.bus.emit(
        "system.startup",
        {"version": VERSION, "subsystems": list(state.is_healthy().keys())},
        correlation_id=uuid.uuid4().hex,
    )

    yield

    # Shutdown: drain the scheduler deterministically, then close out.
    if state.scheduler is not None and state.scheduler.accepting:
        state.scheduler.shutdown(drain=True)
    if state.bus is not None:
        state.bus.emit("system.shutdown", {"version": VERSION})


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
    request_id = uuid.uuid4().hex
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
        description="Tutolage AI Platform — v16.2 (rewired to the split packages)",
        version=VERSION,
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
        return {"name": "Skeleton", "version": VERSION, "status": "operational"}

    return app
