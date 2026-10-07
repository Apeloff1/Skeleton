"""
Skeleton API Server — FastAPI application factory and state management

Provides:
- create_app: FastAPI application factory (mounts core + gameforge + cockpit routers)
- get_state: Dependency injection for server state
- ServerState: Shared runtime state container
"""

from __future__ import annotations

from typing import Any, Dict, Optional

# Lazy imports to avoid heavy dependencies at module load time
_fastapi = None
_uvicorn = None


def _get_fastapi():
    global _fastapi
    if _fastapi is None:
        import fastapi
        _fastapi = fastapi
    return _fastapi


def _get_uvicorn():
    global _uvicorn
    if _uvicorn is None:
        import uvicorn
        _uvicorn = uvicorn
    return _uvicorn


class ServerState:
    """Shared runtime state for the API server."""

    def __init__(self):
        self.genesis: Optional[Any] = None
        self.jeeves: Optional[Any] = None
        self.forge: Optional[Any] = None
        self.mesh: Optional[Any] = None
        self.registry: Optional[Any] = None
        self.ledger: Optional[Any] = None
        self.scheduler: Optional[Any] = None
        self.health: Optional[Any] = None
        self.metrics: Optional[Any] = None
        self.cockpit: Optional[Any] = None
        self.npc_pipeline: Optional[Any] = None
        self.game_logic_pipeline: Optional[Any] = None
        self.animation_pipeline: Optional[Any] = None
        self.gameforge: Optional[Any] = None
        self.memory_trinity: Optional[Any] = None
        self.resilience: Optional[Any] = None
        self.intelligence: Optional[Any] = None
        self.jeeves_sam: Optional[Any] = None
        self.jeeves_clom: Optional[Any] = None
        self.jeeves_krem: Optional[Any] = None
        self.jeeves_memory: Optional[Any] = None

    def is_healthy(self) -> Dict[str, Any]:
        """Run health checks on all subsystems."""
        checks = {}
        for attr in dir(self):
            if not attr.startswith("_") and not callable(getattr(self, attr)):
                val = getattr(self, attr)
                if val is not None and hasattr(val, "stats"):
                    try:
                        checks[attr] = val.stats()
                    except Exception:
                        checks[attr] = {"error": "stats failed"}

        overall = all(
            not isinstance(c, dict) or not c.get("error")
            for c in checks.values()
        )
        return {"overall": overall, "checks": checks}

    def wire_from_genesis(self, genesis: Any) -> None:
        """Populate state handles from a booted genesis."""
        self.genesis = genesis
        self.forge = genesis.handles.get("forge")
        self.mesh = genesis.handles.get("mesh")
        self.memory_trinity = genesis.handles.get("trinity")
        self.intelligence = genesis.handles.get("orchestrator")
        self.resilience = genesis.handles.get("fortress")

        # Pipelines
        from skeleton.pipelines import AnimationPipeline, GameForge, GameLogicPipeline, NPCPipeline
        self.npc_pipeline = NPCPipeline()
        self.game_logic_pipeline = GameLogicPipeline()
        self.animation_pipeline = AnimationPipeline()
        self.gameforge = GameForge(genesis=genesis, bus=genesis.bus)

        # Jeeves with provider-backed responses, quad retriever context,
        # and the genesis-wired ResponseCycle driving the context fabric
        from skeleton.jeeves import JeevesCore
        self.jeeves = JeevesCore(
            bus=genesis.bus,
            retriever=genesis.handles.get("quad"),
            cycle=genesis.handles.get("cycle"),
        )

        # Jeeves memory matrices (served at /jeeves/matrices/{session_id})
        self.jeeves_sam = self.jeeves.sam
        self.jeeves_clom = self.jeeves.clom
        self.jeeves_krem = self.jeeves.krem
        self.jeeves_memory = self.jeeves._memory

        # Live cortex attaches to the genesis bus
        from skeleton.cortex import live
        self.cockpit = live.attach(genesis.bus)

        # Health + metrics
        from skeleton.observability import MetricsCollector
        self.metrics = MetricsCollector()
        self.health = type("Health", (), {
            "liveness": staticmethod(lambda: {"alive": True}),
            "readiness": staticmethod(lambda: {"ready": True, "subsystems": len(genesis.handles)}),
        })()
        self.ledger = genesis.handles.get("provenance")
        self.scheduler = genesis.handles.get("repetition")
        self.registry = genesis.handles.get("lattice")


# Global state instance
_state: Optional[ServerState] = None


def get_state() -> ServerState:
    """Get or create the global server state."""
    global _state
    if _state is None:
        _state = ServerState()
    return _state


def create_app() -> Any:
    """Create and configure the FastAPI application."""
    fastapi = _get_fastapi()
    app = fastapi.FastAPI(
        title="Skeleton API",
        version="16.0.0",
        description="AI game engine / agent orchestration framework",
    )

    from skeleton.api.routes import router
    from skeleton.api.gameforge_routes import router as gameforge_router
    from skeleton.api.cockpit import router as cockpit_router
    app.include_router(router, prefix="/api/v1")
    app.include_router(gameforge_router, prefix="/api/v1")
    app.include_router(cockpit_router)

    # Zaibatsu gate — sibling of gameforge-middleware / gf-server.
    # Live app previously left install_gate test-only; wire it here.
    from skeleton.api.middleware import DEFAULT_OPEN_PREFIXES, GatePolicy, install_gate

    gate_policy = GatePolicy(
        open_prefixes=DEFAULT_OPEN_PREFIXES
        + (
            "/",
            "/cortex/status",
            "/cockpit",
            "/docs",
            "/openapi.json",
            "/redoc",
        )
    )
    install_gate(app, policy=gate_policy)

    @app.on_event("startup")
    async def startup():
        state = get_state()
        if state.genesis is None:
            from skeleton.genesis import Genesis
            state.wire_from_genesis(Genesis(seed=42).boot())

    @app.get("/")
    async def root():
        state = get_state()
        return {
            "name": "Skeleton",
            "version": "16.0.0",
            "status": "running",
            "jeeves_provider": state.jeeves.provider_name if state.jeeves else None,
            "cockpit": "/cockpit",
        }

    @app.get("/cortex/status")
    async def cortex_status():
        from skeleton.cortex import live
        return live.status()

    return app


def run_server(host: str = "0.0.0.0", port: int = 8000) -> None:
    """Run the API server with uvicorn."""
    uvicorn = _get_uvicorn()
    app = create_app()
    uvicorn.run(app, host=host, port=port)
