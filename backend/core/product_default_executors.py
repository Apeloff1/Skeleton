"""Native executors for the first canonical product actions.

Adapters target framework-free runtime primitives instead of calling HTTP routes.
A matching existing receipt is treated as already complete, preventing duplicate
side effects when execution is retried after a later audit/confirmation failure.
"""
from __future__ import annotations

from typing import Any

from core.execution_receipts import ExecutionReceiptStore, ReceiptIntegrityError
from core.product_executor_registry import ProductExecutorRegistry
from core.product_operations import AdmittedOperation
from core.runtime_sessions import RuntimeSessionManager


class NativeProductExecutors:
    def __init__(
        self,
        receipt_store: ExecutionReceiptStore,
        *,
        sessions: RuntimeSessionManager | None = None,
    ) -> None:
        self.receipts = receipt_store
        self.sessions = sessions or RuntimeSessionManager()

    def _already_complete(self, operation: AdmittedOperation, executor: str) -> bool:
        existing = self.receipts.read(operation.id)
        if existing is None:
            return False
        if (
            existing.capability_id != operation.capability_id
            or existing.action != operation.action
            or existing.executor != executor
        ):
            raise ReceiptIntegrityError("existing receipt does not match executor contract")
        return True

    def _write(self, operation: AdmittedOperation, executor: str, result: dict[str, Any]) -> bool:
        self.receipts.write(
            operation_id=operation.id,
            capability_id=operation.capability_id,
            action=operation.action,
            executor=executor,
            result=result,
        )
        return True

    def create_project(self, operation: AdmittedOperation, payload: dict[str, Any]) -> bool:
        executor = "native.studio.project.create"
        if self._already_complete(operation, executor):
            return True
        title = str(payload.get("title") or payload.get("name") or "Untitled project").strip()
        if not title:
            raise ValueError("project title cannot be blank")
        descriptor = {
            "project_id": operation.id,
            "title": title[:200],
            "genre": str(payload.get("genre") or "unspecified")[:80],
            "brief": str(payload.get("brief") or payload.get("prompt") or "")[:20_000],
            "template": str(payload.get("template") or "blank")[:120],
            "owner": operation.principal,
            "state": "created",
        }
        return self._write(operation, executor, descriptor)

    def create_world(self, operation: AdmittedOperation, payload: dict[str, Any]) -> bool:
        executor = "native.worldforge.world.create"
        if self._already_complete(operation, executor):
            return True
        # Import lazily so product-control boot stays independent of WorldForge's
        # optional presentation modules. worldforge_core itself is pure/seedable.
        from routes.worldforge_core import WorldConfig, build_world

        config_payload = dict(payload.get("config") or payload)
        cfg = WorldConfig(**config_payload)
        world = build_world(cfg)
        result = {
            "world": world,
            "seed": getattr(cfg, "seed", None),
            "scale": getattr(cfg, "scale", None),
        }
        return self._write(operation, executor, result)

    def launch_playable(self, operation: AdmittedOperation, payload: dict[str, Any]) -> bool:
        executor = "native.playables.playable.launch"
        if self._already_complete(operation, executor):
            return True
        seed = int(payload.get("seed", 1))
        terrain_size = float(payload.get("terrain_size", 720.0))
        resolution = int(payload.get("resolution", 96))
        thermal_count = int(payload.get("thermal_count", 8))
        session = self.sessions.create(
            seed=seed,
            terrain_size=terrain_size,
            resolution=resolution,
            thermal_count=thermal_count,
        )
        result = {
            "session_id": session.id,
            "created_at": session.created_at,
            "closed": session.closed,
            "runtime": self.sessions.snapshot(),
            "seed": seed,
        }
        return self._write(operation, executor, result)

    def runtime_sessions(self, operation: AdmittedOperation, payload: dict[str, Any]) -> bool:
        executor = "native.playables.runtime.sessions"
        if self._already_complete(operation, executor):
            return True
        return self._write(operation, executor, {"runtime": self.sessions.snapshot()})

    def register_into(self, registry: ProductExecutorRegistry) -> ProductExecutorRegistry:
        registry.register("studio", "project.create", self.create_project, name="native.studio.project.create")
        registry.register("world-forge", "world.create", self.create_world, name="native.worldforge.world.create")
        registry.register("playables", "playable.launch", self.launch_playable, name="native.playables.playable.launch")
        registry.register("playables", "runtime.sessions", self.runtime_sessions, name="native.playables.runtime.sessions")
        return registry


def build_default_executor_registry(
    receipt_store: ExecutionReceiptStore,
    *,
    sessions: RuntimeSessionManager | None = None,
) -> tuple[ProductExecutorRegistry, NativeProductExecutors]:
    registry = ProductExecutorRegistry()
    adapters = NativeProductExecutors(receipt_store, sessions=sessions)
    adapters.register_into(registry)
    return registry, adapters
