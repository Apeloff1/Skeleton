"""
Skeleton API Server — FastAPI application factory and state management.
"""

from __future__ import annotations

import os
from dataclasses import asdict, is_dataclass
from threading import RLock
from typing import Any, Dict, Optional

from skeleton.api.errors import (
    install_error_handlers,
    skeleton_error_handler,
    unhandled_error_handler,
)

__all__ = [
    "ServerState",
    "create_app",
    "get_state",
    "install_error_handlers",
    "run_server",
    "skeleton_error_handler",
    "unhandled_error_handler",
]

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
        self.intelligence_core: Optional[Any] = None
        self.operation_runtime: Optional[Any] = None
        self.engine_execution_service: Optional[Any] = None
        self.engine_execution_coordinator: Optional[Any] = None
        self.engine_tool_receipt_store: Optional[Any] = None
        self.jeeves_sam: Optional[Any] = None
        self.jeeves_clom: Optional[Any] = None
        self.jeeves_krem: Optional[Any] = None
        self.jeeves_memory: Optional[Any] = None
        self._swarm_bind_lock = RLock()

    def bind_swarm_runtime(self, runtime: Any) -> Any:
        """Replace the live swarm runtime and atomically rebind dependent control planes."""
        from skeleton.agents.swarm_broker import SwarmBroker
        from skeleton.agents.swarm_supervisor import SwarmSupervisor

        with self._swarm_bind_lock:
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

        with self._swarm_bind_lock:
            self.swarm_ingress = ingress
            if self.swarm_broker is not None:
                if self.swarm_tenant_broker is None:
                    self.swarm_tenant_broker = TenantSwarmBroker(self.swarm_broker, ingress)
                else:
                    self.swarm_tenant_broker.ingress = ingress
                    self.swarm_tenant_broker.rebind(self.swarm_broker)
            return ingress

    def commit_swarm_bundle(self, runtime: Any, broker: Any, ingress: Any, tenant_broker: Any) -> Any:
        """Publish a fully staged swarm recovery bundle under one server-state lock."""
        if getattr(broker, "runtime", None) is not runtime:
            raise ValueError("staged broker runtime mismatch")
        if getattr(tenant_broker, "broker", None) is not broker:
            raise ValueError("staged tenant broker mismatch")
        if getattr(tenant_broker, "ingress", None) is not ingress:
            raise ValueError("staged tenant ingress mismatch")
        if self.swarm_supervisor is not None and getattr(broker, "supervisor", None) is not self.swarm_supervisor:
            raise ValueError("staged broker supervisor mismatch")
        reconcile = tenant_broker.reconcile()
        if any(bool(values) for values in reconcile.values()):
            raise ValueError("staged tenant bundle is not reconciled")
        with self._swarm_bind_lock:
            previous_tenant = self.swarm_tenant_broker
            if previous_tenant is not None and previous_tenant is not tenant_broker:
                previous_tenant.retire()
            self.swarm = runtime
            self.swarm_broker = broker
            self.swarm_ingress = ingress
            self.swarm_tenant_broker = tenant_broker
            return runtime

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

        with self._swarm_bind_lock:
            swarm = self.swarm
            recovery = self.swarm_recovery
            supervisor = self.swarm_supervisor
            ingress = self.swarm_ingress
            tenant_broker = self.swarm_tenant_broker

        if swarm is not None and hasattr(swarm, "health"):
            try:
                checks["swarm"] = swarm.health()
            except Exception:
                checks["swarm"] = {"error": "health failed"}
        if recovery is not None:
            try:
                recovery_status = recovery.status()
                checks["swarm_recovery"] = asdict(recovery_status) if is_dataclass(recovery_status) else recovery_status
            except Exception:
                checks["swarm_recovery"] = {"error": "recovery status failed"}
        if supervisor is not None:
            try:
                checks["swarm_supervisor"] = supervisor.status()
            except Exception:
                checks["swarm_supervisor"] = {"error": "supervisor status failed"}
        if ingress is not None:
            try:
                checks["swarm_ingress"] = ingress.status()
            except Exception:
                checks["swarm_ingress"] = {"error": "ingress status failed"}
        if tenant_broker is not None:
            try:
                checks["swarm_tenant_broker"] = tenant_broker.status()
            except Exception:
                checks["swarm_tenant_broker"] = {"error": "tenant broker status failed"}
        has_error = any(isinstance(check, dict) and check.get("error") for check in checks.values())
        swarm_critical = isinstance(checks.get("swarm"), dict) and checks["swarm"].get("status") == "critical"
        recovery_mismatch = False
        recovery_check = checks.get("swarm_recovery")
        if isinstance(recovery_check, dict) and recovery_check.get("tenant_aligned") is False:
            recovery_mismatch = True
        tenant_mismatch = False
        tenant_check = checks.get("swarm_tenant_broker")
        if isinstance(tenant_check, dict):
            if tenant_check.get("retired") is True:
                tenant_mismatch = True
            reconcile = tenant_check.get("reconcile")
            if isinstance(reconcile, dict):
                tenant_mismatch = tenant_mismatch or any(
                    bool(reconcile.get(field))
                    for field in ("missing_active", "terminal_not_terminal", "active_terminal", "phase_mismatch")
                )
        overall = not has_error and not swarm_critical and not recovery_mismatch and not tenant_mismatch
        return {"overall": overall, "checks": checks}

    def bind_operation_runtime(self) -> Any:
        """Bind the live intelligence surface to durable operation state."""
        if self.intelligence_core is None:
            if self.genesis is None:
                raise RuntimeError("genesis must be wired before operation runtime")
            self.intelligence_core = self.genesis.handles.get("orchestrator")
        if self.intelligence_core is None:
            raise RuntimeError("intelligence orchestrator is unavailable")
        if self.operation_runtime is not None and not getattr(
            self.operation_runtime, "_closed", False
        ):
            self.intelligence = self.operation_runtime
            return self.operation_runtime

        from skeleton.config.settings import get_settings
        from skeleton.persistence.operation_runtime import DurableOperationRuntime

        runtime = DurableOperationRuntime.from_settings(
            self.intelligence_core,
            get_settings().operation,
        )
        runtime.dispatch_outbox()
        runtime.start_dispatcher()
        self.operation_runtime = runtime
        self.intelligence = runtime
        return runtime

    def close_operation_runtime(self) -> None:
        runtime = self.operation_runtime
        if runtime is not None:
            runtime.close()
        self.operation_runtime = None
        self.intelligence = self.intelligence_core

    def bind_engine_execution_service(self) -> Any:
        """Bind durable engine API authority and local execution coordinator."""

        if self.engine_execution_service is not None:
            return self.engine_execution_service

        from pathlib import Path

        from skeleton.api.engine_authority import (
            EngineAuthorityRegistry,
            EngineServiceGrant,
        )
        from skeleton.api.engine_runtime import EngineExecutionCoordinator
        from skeleton.api.engine_service import (
            EngineExecutionService,
            SQLiteEngineSubmissionStore,
        )
        from skeleton.config.settings import get_settings
        from skeleton.persistence.execution_repository import (
            SQLiteExecutionRepository,
        )
        from skeleton.skills.tool_receipt_store import SQLiteToolReceiptStore
        from skeleton.skills.tool_runtime import AsyncToolRuntime

        settings = get_settings().engine
        for raw_path in (
            settings.execution_state_path,
            settings.submission_state_path,
            settings.tool_receipt_path,
        ):
            if raw_path != ":memory:":
                Path(raw_path).expanduser().parent.mkdir(
                    parents=True,
                    exist_ok=True,
                )

        repository = SQLiteExecutionRepository(
            settings.execution_state_path
        )
        submissions = SQLiteEngineSubmissionStore(
            settings.submission_state_path
        )
        authorities = EngineAuthorityRegistry(
            [
                EngineServiceGrant(
                    service_principal=settings.service_principal,
                    scopes=frozenset(
                        {
                            "engine:submit",
                            "engine:read",
                            "engine:cancel",
                            "engine:events",
                            "engine:approve",
                            "engine:media",
                        }
                    ),
                    tenant_ids=settings.allowed_tenants,
                    capabilities=settings.allowed_capabilities,
                )
            ]
        )
        service = EngineExecutionService(
            repository,
            submissions,
            authorities,
        )
        receipt_store = SQLiteToolReceiptStore(
            settings.tool_receipt_path
        )
        coordinator = EngineExecutionCoordinator(
            service,
            tool_runtime=AsyncToolRuntime(
                receipt_store=receipt_store,
            ),
        )
        self.engine_execution_service = service
        self.engine_execution_coordinator = coordinator
        self.engine_tool_receipt_store = receipt_store
        return service

    async def recover_engine_executions(self) -> tuple[str, ...]:
        coordinator = self.engine_execution_coordinator
        if coordinator is None:
            return ()
        return await coordinator.recover()

    async def close_engine_execution_service(self) -> None:
        coordinator = self.engine_execution_coordinator
        if coordinator is not None:
            await coordinator.shutdown()
        service = self.engine_execution_service
        if service is not None:
            service.repository.close()
            service.submissions.close()
        receipt_store = self.engine_tool_receipt_store
        if receipt_store is not None:
            receipt_store.close()
        self.engine_execution_coordinator = None
        self.engine_execution_service = None
        self.engine_tool_receipt_store = None

    def wire_from_genesis(self, genesis: Any) -> None:
        self.genesis = genesis
        self.forge = genesis.handles.get("forge")
        self.mesh = genesis.handles.get("mesh")
        self.memory_trinity = genesis.handles.get("trinity")
        self.intelligence_core = genesis.handles.get("orchestrator")
        self.intelligence = self.intelligence_core
        self.bind_operation_runtime()
        self.resilience = genesis.handles.get("fortress")

        from skeleton.pipelines import AnimationPipeline, GameForge, GameLogicPipeline, NPCPipeline
        self.npc_pipeline = NPCPipeline(genesis=genesis)
        self.game_logic_pipeline = GameLogicPipeline(genesis=genesis)
        self.animation_pipeline = AnimationPipeline(genesis=genesis)
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


_DEV_OPEN_PREFIXES = (
    "/cortex/status",
    "/cockpit",
    "/docs",
    "/openapi.json",
    "/redoc",
    "/api/v1/health",
    "/api/v1/metrics",
    "/api/v1/genesis",
)


def _public_dev_surfaces_enabled() -> bool:
    return os.environ.get("SKELETON_PUBLIC_DEV_SURFACES", "").strip().lower() in {
        "1", "true", "yes", "on",
    }


def _gate_open_prefixes() -> tuple[str, ...]:
    from skeleton.api.middleware import DEFAULT_OPEN_PREFIXES

    # The engine API has its own fail-closed service-to-service bearer token
    # and principal validation. Exempt only this exact route prefix from the
    # generic user/API HMAC gate so the backend EngineClient can reach it.
    # Segment-aware prefix matching keeps /api/v1/engineer sealed.
    prefixes = DEFAULT_OPEN_PREFIXES + ("/", "/api/v1/engine")
    if _public_dev_surfaces_enabled():
        prefixes += _DEV_OPEN_PREFIXES
    return prefixes


def _gate_body_limits() -> tuple[tuple[str, int], ...]:
    """Route-scoped ceilings for authenticated engine transport envelopes."""

    mib = 1024 * 1024
    return (
        # Edit can carry a source image and mask, each bounded to 32 MiB
        # base64 text by the engine request model.
        ("/api/v1/engine/media/images/edit", 70 * mib),
        ("/api/v1/engine/media/images/variation", 34 * mib),
        # Canonical text commands may include bounded instructions + prompt +
        # compiled context metadata above the generic 1 MiB API ceiling.
        ("/api/v1/engine/executions", 4 * mib),
    )


def create_app() -> Any:
    fastapi = _get_fastapi()
    app = fastapi.FastAPI(title="Skeleton API", version="16.0.0", description="AI game engine / agent orchestration framework")
    install_error_handlers(app)

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
    from skeleton.api.swarm_recovery_archive_routes import router as swarm_recovery_archive_router
    from skeleton.api.engine_routes import router as engine_router
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
    app.include_router(swarm_recovery_archive_router, prefix="/api/v1")
    app.include_router(engine_router, prefix="/api/v1")
    app.include_router(cockpit_router)

    from skeleton.api.middleware import GatePolicy, install_gate
    gate_policy = GatePolicy(
        open_prefixes=_gate_open_prefixes(),
        body_limits=_gate_body_limits(),
    )
    install_gate(app, policy=gate_policy)

    @app.on_event("startup")
    async def startup():
        state = get_state()
        if state.genesis is None:
            from skeleton.genesis import Genesis
            state.wire_from_genesis(Genesis(seed=42).boot())
        state.bind_engine_execution_service()
        await state.recover_engine_executions()

    @app.on_event("shutdown")
    async def shutdown():
        state = get_state()
        await state.close_engine_execution_service()
        state.close_operation_runtime()

    @app.get("/")
    async def root():
        body = {"name": "Skeleton", "version": "16.0.0", "status": "running"}
        if _public_dev_surfaces_enabled():
            state = get_state()
            body.update({
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
                "swarm_recovery_archive": "/api/v1/swarm/recovery/archive",
            })
        return body

    @app.get("/cortex/status")
    async def cortex_status():
        from skeleton.cortex import live
        return live.status()

    return app


def run_server(host: str = "0.0.0.0", port: int = 8000) -> None:
    uvicorn = _get_uvicorn(); app = create_app(); uvicorn.run(app, host=host, port=port)
