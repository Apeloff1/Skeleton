"""Native executors for the first canonical product actions.

These adapters deliberately target framework-free runtime primitives instead of
calling HTTP routes. Every successful adapter writes a durable execution receipt
before returning True; failures raise and therefore leave the outbox intent
pending for retry.
"""
from __future__ import annotations

from typing import Any

from core.execution_receipts import ExecutionReceiptStore
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
        return self._write(operation, "native.studio.project.create", descriptor)

    def create_world(self, operation: AdmittedOperation, payload: dict[str, Any]) -> bool:
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
        return self._write(operation, "native.worldforge.world.create", result)

    def launch_playable(self, operation: AdmittedOperation, payload: dict[str, Any]) -> bool:
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
        return self._write(operation, "native.playables.playable.launch", result)

    def runtime_sessions(self, operation: AdmittedOperation, payload: dict[str, Any]) -> bool:
        return self._write(
            operation,
            "native.playables.runtime.sessions",
            {"runtime": self.sessions.snapshot()},
        )

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
