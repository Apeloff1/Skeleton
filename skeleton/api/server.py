"""FastAPI application factory wiring every subsystem into a cohesive surface."""

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
from skeleton.kernel.events import DomainEvent, EventBus
from skeleton.kernel.ids import UserId
from skeleton.kernel.registry import bootstrap_registry

from skeleton.agents.ledger import ActivityLedger
from skeleton.agents.mesh import AgentMesh
from skeleton.agents.scheduler import SwarmScheduler

from skeleton.memory import CAGStore, InMemoryTFIDFStore, MAGStore, MemoryTrinity
from skeleton.resilience import ResilienceFortress
from skeleton.intelligence import IntelligenceOrchestrator
from skeleton.jeeves.core import Jeeves
from skeleton.jeeves.matrices import ClomMatrix, KremMatrix, SamMatrix
from skeleton.jeeves.rag import RagMemory
from skeleton.forge.universal import Forge
from skeleton.pipelines.npc import NpcPipeline
from skeleton.pipelines.game_logic import GameLogicPipeline
from skeleton.pipelines.animation import AnimationPipeline


class AppState:
    """Holds all subsystem instances for dependency injection."""

    def __init__(self) -> None:
        self.settings: Optional[Settings] = None
        self.bus: Optional[EventBus] = None
        self.registry = None
        self.ledger: Optional[ActivityLedger] = None
        self.mesh: Optional[AgentMesh] = None
        self.scheduler: Optional[SwarmScheduler] = None
        self.memory_trinity: Optional[MemoryTrinity] = None
        self.resilience: Optional[ResilienceFortress] = None
        self.intelligence: Optional[IntelligenceOrchestrator] = None
        self.jeeves: Optional[Jeeves] = None
        self.jeeves_sam: Optional[SamMatrix] = None
        self.jeeves_clom: Optional[ClomMatrix] = None
        self.jeeves_krem: Optional[KremMatrix] = None
        self.jeeves_memory: Optional[RagMemory] = None
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


_app_state = AppState()


def get_state() -> AppState:
    return _app_state


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    state = get_state()
    state.settings = get_settings()
    state.bus = EventBus(replay_capacity=10000)
    state.registry = bootstrap_registry(state.bus)
    state.ledger = ActivityLedger()
    state.mesh = AgentMesh(bus=state.bus)
    state.scheduler = SwarmScheduler(bus=state.bus, ledger=state.ledger)

    rag = InMemoryTFIDFStore()
    cag = CAGStore()
    mag = MAGStore(user_id=UserId.new())
    state.memory_trinity = MemoryTrinity(rag=rag, cag=cag, mag=mag, bus=state.bus)

    state.resilience = ResilienceFortress(bus=state.bus)
    state.intelligence = IntelligenceOrchestrator(bus=state.bus)

    state.jeeves_sam = SamMatrix()
    state.jeeves_clom = ClomMatrix()
    state.jeeves_krem = KremMatrix()
    state.jeeves_memory = RagMemory(bus=state.bus)
    state.jeeves = Jeeves(
        bus=state.bus,
        max_turns=state.settings.jeeves.max_session_turns,
    )

    state.forge = Forge(bus=state.bus)
    state.npc_pipeline = NpcPipeline(bus=state.bus)
    state.game_logic_pipeline = GameLogicPipeline(bus=state.bus)
    state.animation_pipeline = AnimationPipeline(bus=state.bus)
    state.started_at = time.time()

    state.bus.publish(DomainEvent(
        topic="system.startup",
        payload={
            "version": state.settings.version,
            "environment": state.settings.environment,
            "subsystems": list(state.is_healthy().keys()),
        },
        correlation_id=uuid.uuid4().hex,
    ))
    yield
    state.bus.clear_history()


async def skeleton_error_handler(request: Request, exc: SkeletonError) -> JSONResponse:
    return JSONResponse(status_code=http_status_for(exc), content=exc.to_dict())


async def request_id_middleware(request: Request, call_next: Any) -> Any:
    request_id = uuid.uuid4().hex
    request.state.request_id = request_id
    start = time.time()
    response = await call_next(request)
    duration = time.time() - start
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Response-Time"] = f"{duration:.3f}s"
    return response


def create_app() -> FastAPI:
    app = FastAPI(
        title="Skeleton",
        description="Tutolage AI Platform — v16",
        version="16.0.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.middleware("http")(request_id_middleware)
    app.add_exception_handler(SkeletonError, skeleton_error_handler)

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
        return {"name": "Skeleton", "version": "16.0.0", "status": "operational"}

    return app
