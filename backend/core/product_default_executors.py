"""Native executors for canonical product actions.

Adapters target framework-free runtime primitives instead of calling HTTP routes.
Receipts capture exact input provenance and executor contracts. Introspection
adapters receive narrow providers from the control plane, avoiding circular
imports while turning product status/policy/audit into governed query actions.
"""
from __future__ import annotations

from typing import Any, Callable

from core.execution_receipts import ExecutionReceiptStore, ReceiptIntegrityError
from core.product_executor_registry import ProductExecutorRegistry
from core.product_operations import AdmittedOperation
from core.runtime_sessions import RuntimeSessionManager

Provider = Callable[[], dict[str, Any] | list[dict[str, Any]]]

_CONTRACTS = {
    "native.studio.project.create": (1, "state", True),
    "native.studio.pipeline.inspect": (1, "query", True),
    "native.worldforge.world.create": (1, "state", True),
    "native.playables.playable.launch": (1, "state", True),
    "native.playables.runtime.sessions": (1, "query", True),
    "native.operations.ops.runtime": (1, "query", True),
    "native.governance.policy": (1, "query", True),
    "native.governance.audit": (1, "query", True),
}


class NativeProductExecutors:
    def __init__(
        self,
        receipt_store: ExecutionReceiptStore,
        *,
        sessions: RuntimeSessionManager | None = None,
        operations_provider: Provider | None = None,
        policy_provider: Provider | None = None,
        audit_provider: Provider | None = None,
    ) -> None:
        self.receipts = receipt_store
        self.sessions = sessions or RuntimeSessionManager()
        self.operations_provider = operations_provider
        self.policy_provider = policy_provider
        self.audit_provider = audit_provider

    def _already_complete(self, operation: AdmittedOperation, executor: str) -> bool:
        existing = self.receipts.read(operation.id)
        if existing is None:
            return False
        version, effect_class, replay_safe = _CONTRACTS[executor]
        if (
            existing.capability_id != operation.capability_id
            or existing.action != operation.action
            or existing.executor != executor
            or existing.executor_version != version
            or existing.effect_class != effect_class
            or existing.replay_safe != replay_safe
            or existing.input_artifact_manifest_id != operation.artifact_manifest_id
        ):
            raise ReceiptIntegrityError("existing receipt does not match executor contract")
        return True

    def _write(self, operation: AdmittedOperation, executor: str, result: dict[str, Any]) -> bool:
        version, effect_class, replay_safe = _CONTRACTS[executor]
        self.receipts.write(
            operation_id=operation.id,
            capability_id=operation.capability_id,
            action=operation.action,
            executor=executor,
            executor_version=version,
            effect_class=effect_class,
            replay_safe=replay_safe,
            input_artifact_manifest_id=operation.artifact_manifest_id,
            result=result,
        )
        return True

    @staticmethod
    def _provider_result(provider: Provider | None, name: str) -> dict[str, Any]:
        if provider is None:
            raise RuntimeError(f"{name} provider unavailable")
        value = provider()
        return {name: value}

    def create_project(self, operation: AdmittedOperation, payload: dict[str, Any]) -> bool:
        executor = "native.studio.project.create"
        if self._already_complete(operation, executor):
            return True
        title = str(payload.get("title") or payload.get("name") or "Untitled project").strip()
        if not title:
            raise ValueError("project title cannot be blank")
        return self._write(operation, executor, {
            "project_id": operation.id,
            "title": title[:200],
            "genre": str(payload.get("genre") or "unspecified")[:80],
            "brief": str(payload.get("brief") or payload.get("prompt") or "")[:20_000],
            "template": str(payload.get("template") or "blank")[:120],
            "owner": operation.principal,
            "state": "created",
        })

    def pipeline_inspect(self, operation: AdmittedOperation, payload: dict[str, Any]) -> bool:
        executor = "native.studio.pipeline.inspect"
        if self._already_complete(operation, executor):
            return True
        return self._write(operation, executor, self._provider_result(self.operations_provider, "pipeline"))

    def create_world(self, operation: AdmittedOperation, payload: dict[str, Any]) -> bool:
        executor = "native.worldforge.world.create"
        if self._already_complete(operation, executor):
            return True
        from routes.worldforge_core import WorldConfig, build_world
        cfg = WorldConfig(**dict(payload.get("config") or payload))
        world = build_world(cfg)
        return self._write(operation, executor, {
            "world": world,
            "seed": getattr(cfg, "seed", None),
            "scale": getattr(cfg, "scale", None),
        })

    def launch_playable(self, operation: AdmittedOperation, payload: dict[str, Any]) -> bool:
        executor = "native.playables.playable.launch"
        if self._already_complete(operation, executor):
            return True
        seed = int(payload.get("seed", 1))
        session = self.sessions.create(
            seed=seed,
            terrain_size=float(payload.get("terrain_size", 720.0)),
            resolution=int(payload.get("resolution", 96)),
            thermal_count=int(payload.get("thermal_count", 8)),
        )
        return self._write(operation, executor, {
            "session_id": session.id,
            "created_at": session.created_at,
            "closed": session.closed,
            "runtime": self.sessions.snapshot(),
            "seed": seed,
        })

    def runtime_sessions(self, operation: AdmittedOperation, payload: dict[str, Any]) -> bool:
        executor = "native.playables.runtime.sessions"
        if self._already_complete(operation, executor):
            return True
        return self._write(operation, executor, {"runtime": self.sessions.snapshot()})

    def ops_runtime(self, operation: AdmittedOperation, payload: dict[str, Any]) -> bool:
        executor = "native.operations.ops.runtime"
        if self._already_complete(operation, executor):
            return True
        result = self._provider_result(self.operations_provider, "operations")
        result["sessions"] = self.sessions.snapshot()
        result["receipts"] = self.receipts.stats()
        return self._write(operation, executor, result)

    def governance_policy(self, operation: AdmittedOperation, payload: dict[str, Any]) -> bool:
        executor = "native.governance.policy"
        if self._already_complete(operation, executor):
            return True
        return self._write(operation, executor, self._provider_result(self.policy_provider, "policy"))

    def governance_audit(self, operation: AdmittedOperation, payload: dict[str, Any]) -> bool:
        executor = "native.governance.audit"
        if self._already_complete(operation, executor):
            return True
        return self._write(operation, executor, self._provider_result(self.audit_provider, "audit"))

    def register_into(self, registry: ProductExecutorRegistry) -> ProductExecutorRegistry:
        registry.register("studio", "project.create", self.create_project, name="native.studio.project.create", version=1, effect_class="state", replay_safe=True)
        if self.operations_provider is not None:
            registry.register("studio", "pipeline.inspect", self.pipeline_inspect, name="native.studio.pipeline.inspect", version=1, effect_class="query", replay_safe=True)
        registry.register("world-forge", "world.create", self.create_world, name="native.worldforge.world.create", version=1, effect_class="state", replay_safe=True)
        registry.register("playables", "playable.launch", self.launch_playable, name="native.playables.playable.launch", version=1, effect_class="state", replay_safe=True)
        registry.register("playables", "runtime.sessions", self.runtime_sessions, name="native.playables.runtime.sessions", version=1, effect_class="query", replay_safe=True)
        if self.operations_provider is not None:
            registry.register("operations", "ops.runtime", self.ops_runtime, name="native.operations.ops.runtime", version=1, effect_class="query", replay_safe=True)
        if self.policy_provider is not None:
            registry.register("governance", "governance.policy", self.governance_policy, name="native.governance.policy", version=1, effect_class="query", replay_safe=True)
        if self.audit_provider is not None:
            registry.register("governance", "governance.audit", self.governance_audit, name="native.governance.audit", version=1, effect_class="query", replay_safe=True)
        return registry


def build_default_executor_registry(
    receipt_store: ExecutionReceiptStore,
    *,
    sessions: RuntimeSessionManager | None = None,
    operations_provider: Provider | None = None,
    policy_provider: Provider | None = None,
    audit_provider: Provider | None = None,
) -> tuple[ProductExecutorRegistry, NativeProductExecutors]:
    registry = ProductExecutorRegistry()
    adapters = NativeProductExecutors(
        receipt_store,
        sessions=sessions,
        operations_provider=operations_provider,
        policy_provider=policy_provider,
        audit_provider=audit_provider,
    )
    adapters.register_into(registry)
    return registry, adapters
