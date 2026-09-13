"""
Skeleton API Server — FastAPI application factory and state management.
"""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any, Dict, Optional

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
        self.swarm: Optional[Any] = None
        self.swarm_recovery: Optional[Any] = None
        self.swarm_supervisor: Optional[Any] = None
        self.swarm_broker: Optional[Any] = None
        self.swarm_ingress: Optional[Any] = None
        self.swarm_tenant_broker: Optional[Any] = None
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

    def bind_swarm_runtime(self, runtime: Any) -> Any:
        """Replace the live swarm runtime and atomically rebind dependent control planes."""
        from skeleton.agents.swarm_broker import SwarmBroker
        from skeleton.agents.swarm_supervisor import SwarmSupervisor

        self.swarm = runtime
        if self.swarm_supervisor is None:
            self.swarm_supervisor = SwarmSupervisor()
        self.swarm_broker = SwarmBroker(runtime, supervisor=self.swarm_supervisor)
        if self.swarm_tenant_broker is not None:
            self.swarm_tenant_broker.rebind(self.swarm_broker)
        return runtime

    def bind_swarm_ingress(self, ingress: Any) -> Any:
        """Bind ingress and tenant execution control to the current runtime broker."""
        from skeleton.agents.swarm_tenant_broker import TenantSwarmBroker

        self.swarm_ingress = ingress
        if self.swarm_broker is not None:
            if self.swarm_tenant_broker is None:
                self.swarm_tenant_broker = TenantSwarmBroker(self.swarm_broker, ingress)
            else:
                self.swarm_tenant_broker.ingress = ingress
                self.swarm_tenant_broker.rebind(self.swarm_broker)
        return ingress

    def is_healthy(self) -> Dict[str, Any]:
        checks = {}
        for attr in dir(self):
            if not attr.startswith("_") and not callable(getattr(self, attr)):
                val = getattr(self, attr)
                if val is not None and hasattr(val, "stats"):
                    try:
                        checks[attr] = val.stats()
                    except Exception:
                        checks[attr] = {"error": "stats failed"}
        if self.swarm is not None and hasattr(self.swarm, "health"):
            try:
                checks["swarm"] = self.swarm.health()
            except Exception:
                checks["swarm"] = {"error": "health failed"}
        if self.swarm_recovery is not None:
            try:
                recovery_status = self.swarm_recovery.status()
                checks["swarm_recovery"] = asdict(recovery_status) if is_dataclass(recovery_status) else recovery_status
            except Exception:
                checks["swarm_recovery"] = {"error": "recovery status failed"}
        if self.swarm_supervisor is not None:
            try:
                checks["swarm_supervisor"] = self.swarm_supervisor.status()
            except Exception:
                checks["swarm_supervisor"] = {"error": "supervisor status failed"}
        if self.swarm_ingress is not None:
            try:
                checks["swarm_ingress"] = self.swarm_ingress.status()
            except Exception:
                checks["swarm_ingress"] = {"error": "ingress status failed"}
        if self.swarm_tenant_broker is not None:
            try:
                checks["swarm_tenant_broker"] = self.swarm_tenant_broker.status()
            except Exception:
                checks["swarm_tenant_broker"] = {"error": "tenant broker status failed"}
        has_error = any(isinstance(check, dict) and check.get("error") for check in checks.values())
        swarm_critical = isinstance(checks.get("swarm"), dict) and checks["swarm"].get("status") == "critical"
        tenant_mismatch = False
        tenant_check = checks.get("swarm_tenant_broker")
        if isinstance(tenant_check, dict):
            reconcile = tenant_check.get("reconcile")
            if isinstance(reconcile, dict):
                tenant_mismatch = bool(reconcile.get("missing_active") or reconcile.get("terminal_not_terminal"))
        overall = not has_error and not swarm_critical and not tenant_mismatch
        return {"overall": overall, "checks": checks}

    def wire_from_genesis(self, genesis: Any) -> None:
        self.genesis = genesis
        self.forge = genesis.handles.get("forge")
        self.mesh = genesis.handles.get("mesh")
        self.memory_trinity = genesis.handles.get("trinity")
        self.intelligence = genesis.handles.get("orchestrator")
        self.resilience = genesis.handles.get("fortress")

        from skeleton.pipelines import AnimationPipeline, GameForge, GameLogicPipeline, NPCPipeline
        self.npc_pipeline = NPCPipeline()
        self.game_logic_pipeline = GameLogicPipeline()
        self.animation_pipeline = AnimationPipeline()
        self.gameforge = GameForge(genesis=genesis, bus=genesis.bus)

        from skeleton.jeeves import JeevesCore
        self.jeeves = JeevesCore(bus=genesis.bus, retriever=genesis.handles.get("quad"), cycle=genesis.handles.get("cycle"))
        self.jeeves_sam = self.jeeves.sam
        self.jeeves_clom = self.jeeves.clom
        self.jeeves_krem = self.jeeves.krem
        self.jeeves_memory = self.jeeves._memory

        from skeleton.cortex import live
        self.cockpit = live.attach(genesis.bus)

        from skeleton.agents.swarm_hardened import HardenedSwarmRuntime
        from skeleton.agents.swarm_ingress import SwarmIngressGovernor
        from skeleton.agents.swarm_recovery import SwarmRecoveryManager
        runtime = HardenedSwarmRuntime(max_tasks=100_000, max_workers=10_000, default_lease_seconds=30.0, max_lease_seconds=86_400.0)
        self.bind_swarm_runtime(runtime)
        self.swarm_recovery = SwarmRecoveryManager(max_checkpoints=16)
        self.bind_swarm_ingress(SwarmIngressGovernor())

        from skeleton.observability import MetricsCollector
        self.metrics = MetricsCollector()
        self.health = type("Health", (), {
            "liveness": staticmethod(lambda: {"alive": True}),
            "readiness": staticmethod(lambda: {"ready": True, "subsystems": len(genesis.handles)}),
        })()
        self.ledger = genesis.handles.get("provenance")
        self.scheduler = genesis.handles.get("repetition")
        self.registry = genesis.handles.get("lattice")


_state: Optional[ServerState] = None


def get_state() -> ServerState:
    global _state
    if _state is None:
        _state = ServerState()
    return _state


def create_app() -> Any:
    fastapi = _get_fastapi()
    app = fastapi.FastAPI(title="Skeleton API", version="16.0.0", description="AI game engine / agent orchestration framework")

    from skeleton.api.routes import router
    from skeleton.api.gameforge_routes import router as gameforge_router
    from skeleton.api.cockpit import router as cockpit_router
    from skeleton.api.swarm_routes import router as swarm_router
    from skeleton.api.swarm_operator_routes import router as swarm_operator_router
    from skeleton.api.swarm_policy_routes import router as swarm_policy_router
    from skeleton.api.swarm_lifecycle_routes import router as swarm_lifecycle_router
    from skeleton.api.swarm_integrity_routes import router as swarm_integrity_router
    from skeleton.api.swarm_fence_routes import router as swarm_fence_router
    from skeleton.api.swarm_supervisor_routes import router as swarm_supervisor_router
    from skeleton.api.swarm_broker_routes import router as swarm_broker_router
    from skeleton.api.swarm_batch_routes import router as swarm_batch_router
    from skeleton.api.swarm_ingress_routes import router as swarm_ingress_router
    from skeleton.api.swarm_tenant_broker_routes import router as swarm_tenant_broker_router
    app.include_router(router, prefix="/api/v1")
    app.include_router(gameforge_router, prefix="/api/v1")
    app.include_router(swarm_router, prefix="/api/v1")
    app.include_router(swarm_operator_router, prefix="/api/v1")
    app.include_router(swarm_policy_router, prefix="/api/v1")
    app.include_router(swarm_lifecycle_router, prefix="/api/v1")
    app.include_router(swarm_integrity_router, prefix="/api/v1")
    app.include_router(swarm_fence_router, prefix="/api/v1")
    app.include_router(swarm_supervisor_router, prefix="/api/v1")
    app.include_router(swarm_broker_router, prefix="/api/v1")
    app.include_router(swarm_batch_router, prefix="/api/v1")
    app.include_router(swarm_ingress_router, prefix="/api/v1")
    app.include_router(swarm_tenant_broker_router, prefix="/api/v1")
    app.include_router(cockpit_router)

    from skeleton.api.middleware import DEFAULT_OPEN_PREFIXES, GatePolicy, install_gate
    gate_policy = GatePolicy(open_prefixes=DEFAULT_OPEN_PREFIXES + ("/", "/cortex/status", "/cockpit", "/docs", "/openapi.json", "/redoc"))
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
            "name": "Skeleton", "version": "16.0.0", "status": "running",
            "jeeves_provider": state.jeeves.provider_name if state.jeeves else None,
            "cockpit": "/cockpit", "swarm": "/api/v1/swarm/status",
            "swarm_operator": "/api/v1/swarm/operator/overview",
            "swarm_policy": "/api/v1/swarm/policy/admission-preview",
            "swarm_lifecycle": "/api/v1/swarm/lifecycle/pressure",
            "swarm_integrity": "/api/v1/swarm/integrity/audit",
            "swarm_fenced": "/api/v1/swarm/fenced/workers/{worker_id}/tasks/{task_id}/success",
            "swarm_supervisor": "/api/v1/swarm/supervisor/status",
            "swarm_broker": "/api/v1/swarm/broker/status",
            "swarm_batch": "/api/v1/swarm/batch/submit",
            "swarm_ingress": "/api/v1/swarm/ingress/status",
            "swarm_tenant_broker": "/api/v1/swarm/tenant-broker/status",
        }

    @app.get("/cortex/status")
    async def cortex_status():
        from skeleton.cortex import live
        return live.status()

    return app


def run_server(host: str = "0.0.0.0", port: int = 8000) -> None:
    uvicorn = _get_uvicorn(); app = create_app(); uvicorn.run(app, host=host, port=port)
