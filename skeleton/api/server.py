"""
Skeleton API Server — FastAPI application factory and state management

Provides:
- create_app: FastAPI application factory
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
    
    # Import and include routers
    from skeleton.api.routes import router
    app.include_router(router, prefix="/api/v1")

    # Gate gauntlet (outer→inner): RequestSeal → BodyBound → WORM → Auth → PolicyGate
    from skeleton.api.middleware import install_gate
    install_gate(app)
    
    @app.on_event("startup")
    async def startup():
        state = get_state()
        if state.genesis is None:
            from skeleton.genesis import Genesis
            state.genesis = Genesis(seed=42).boot()
            state.forge = state.genesis.handles.get("forge")
            state.mesh = state.genesis.handles.get("mesh")
            state.memory_trinity = state.genesis.handles.get("trinity")
            state.intelligence = state.genesis.handles.get("orchestrator")
            state.resilience = state.genesis.handles.get("fortress")
    
    @app.get("/")
    async def root():
        return {"name": "Skeleton", "version": "16.0.0", "status": "running"}
    
    return app


def run_server(host: str = "0.0.0.0", port: int = 8000) -> None:
    """Run the API server with uvicorn."""
    uvicorn = _get_uvicorn()
    app = create_app()
    uvicorn.run(app, host=host, port=port)
