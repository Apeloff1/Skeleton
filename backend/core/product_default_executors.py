"""Native executors for canonical product actions.

Adapters target framework-free runtime primitives instead of calling HTTP routes.
Receipts capture exact input provenance and executor contracts. Transform/query
executors are deterministic and attested; effectful executors must be replay-safe.
"""
from __future__ import annotations

from typing import Any, Callable

from core.curiosity_engine import CuriosityEngine
from core.deployment_planner import compile_deployment_plan
from core.execution_receipts import ExecutionReceiptStore, ReceiptIntegrityError
from core.knowledge_augmented_jeeves import KnowledgeAugmentedJeeves
from core.product_executor_registry import ProductExecutorRegistry
from core.product_operations import AdmittedOperation
from core.progression_intelligence import inspect_progression
from core.runtime_sessions import RuntimeSessionManager
from core.world_system_composer import blueprint_dict, compose_world_systems

Provider = Callable[[], dict[str, Any] | list[dict[str, Any]]]

_CONTRACTS = {
    "native.studio.project.create": (1, "state", True),
    "native.studio.pipeline.inspect": (1, "query", True),
    "native.worldforge.world.create": (1, "state", True),
    "native.worldforge.world.systems.compose": (1, "state", True),
    "native.playables.playable.launch": (1, "state", True),
    "native.playables.runtime.sessions": (1, "query", True),
    "native.playables.progress.inspect": (1, "query", True),
    "native.jeeves.reason": (1, "state", True),
    "native.jeeves.plan": (1, "state", True),
    "native.jeeves.agents.review": (1, "state", True),
    "native.operations.ops.runtime": (1, "query", True),
    "native.operations.ops.deployments": (1, "query", True),
    "native.governance.policy": (1, "query", True),
    "native.governance.audit": (1, "query", True),
    "native.governance.safety": (1, "query", True),
}


class NativeProductExecutors:
    def __init__(self, receipt_store: ExecutionReceiptStore, *, sessions: RuntimeSessionManager | None = None,
                 curiosity: CuriosityEngine | None = None, operations_provider: Provider | None = None,
                 policy_provider: Provider | None = None, audit_provider: Provider | None = None,
                 safety_provider: Provider | None = None) -> None:
        self.receipts = receipt_store
        self.sessions = sessions or RuntimeSessionManager()
        self.curiosity = curiosity
        self.jeeves = KnowledgeAugmentedJeeves(curiosity) if curiosity is not None else None
        self.operations_provider = operations_provider; self.policy_provider = policy_provider
        self.audit_provider = audit_provider; self.safety_provider = safety_provider

    def _already_complete(self, operation: AdmittedOperation, executor: str) -> bool:
        existing = self.receipts.read(operation.id)
        if existing is None: return False
        version, effect_class, replay_safe = _CONTRACTS[executor]
        if (existing.capability_id != operation.capability_id or existing.action != operation.action or
            existing.executor != executor or existing.executor_version != version or
            existing.effect_class != effect_class or existing.replay_safe != replay_safe or
            existing.input_artifact_manifest_id != operation.artifact_manifest_id):
            raise ReceiptIntegrityError("existing receipt does not match executor contract")
        return True

    def _write(self, operation: AdmittedOperation, executor: str, result: dict[str, Any]) -> bool:
        version, effect_class, replay_safe = _CONTRACTS[executor]
        self.receipts.write(operation_id=operation.id, capability_id=operation.capability_id, action=operation.action,
                            executor=executor, executor_version=version, effect_class=effect_class,
                            replay_safe=replay_safe, input_artifact_manifest_id=operation.artifact_manifest_id,
                            result=result)
        return True

    @staticmethod
    def _provider_result(provider: Provider | None, name: str) -> dict[str, Any]:
        if provider is None: raise RuntimeError(f"{name} provider unavailable")
        return {name: provider()}

    @staticmethod
    def _jeeves_payload(operation: AdmittedOperation, payload: dict[str, Any]) -> dict[str, Any]:
        enriched = dict(payload)
        # Stable operation identity makes prompt observation idempotent if a worker
        # crashes after Curiosity mutation but before the execution receipt lands.
        enriched["_curiosity_signal_key"] = f"operation:{operation.id}"
        enriched["_curiosity_observed_at"] = operation.admitted_at
        return enriched

    def create_project(self, operation: AdmittedOperation, payload: dict[str, Any]) -> bool:
        executor = "native.studio.project.create"
        if self._already_complete(operation, executor): return True
        title = str(payload.get("title") or payload.get("name") or "Untitled project").strip()
        if not title: raise ValueError("project title cannot be blank")
        return self._write(operation, executor, {"project_id": operation.id, "title": title[:200],
            "genre": str(payload.get("genre") or "unspecified")[:80], "brief": str(payload.get("brief") or payload.get("prompt") or "")[:20_000],
            "template": str(payload.get("template") or "blank")[:120], "owner": operation.principal, "state": "created"})

    def pipeline_inspect(self, operation: AdmittedOperation, payload: dict[str, Any]) -> bool:
        executor = "native.studio.pipeline.inspect"
        if self._already_complete(operation, executor): return True
        return self._write(operation, executor, self._provider_result(self.operations_provider, "pipeline"))

    @staticmethod
    def _generate_world(payload: dict[str, Any]) -> dict[str, Any]:
        from routes.worldforge_core import WorldConfig, build_world
        return build_world(WorldConfig(**dict(payload.get("config") or payload)))

    def create_world(self, operation: AdmittedOperation, payload: dict[str, Any]) -> bool:
        executor = "native.worldforge.world.create"
        if self._already_complete(operation, executor): return True
        return self._write(operation, executor, {"world": self._generate_world(payload)})

    def compose_world_systems(self, operation: AdmittedOperation, payload: dict[str, Any]) -> bool:
        executor = "native.worldforge.world.systems.compose"
        if self._already_complete(operation, executor): return True
        supplied = payload.get("world")
        if supplied is not None and not isinstance(supplied, dict): raise ValueError("world must be an object when supplied")
        world = dict(supplied) if isinstance(supplied, dict) else self._generate_world(payload)
        blueprint = compose_world_systems(world)
        return self._write(operation, executor, {"blueprint": blueprint_dict(blueprint), "world_signature": blueprint.world_signature})

    def launch_playable(self, operation: AdmittedOperation, payload: dict[str, Any]) -> bool:
        executor = "native.playables.playable.launch"
        if self._already_complete(operation, executor): return True
        seed = int(payload.get("seed", 1))
        session = self.sessions.create(seed=seed, terrain_size=float(payload.get("terrain_size", 720.0)),
                                       resolution=int(payload.get("resolution", 96)), thermal_count=int(payload.get("thermal_count", 8)))
        return self._write(operation, executor, {"session_id": session.id, "created_at": session.created_at,
            "closed": session.closed, "runtime": self.sessions.snapshot(), "seed": seed})

    def runtime_sessions(self, operation: AdmittedOperation, payload: dict[str, Any]) -> bool:
        executor = "native.playables.runtime.sessions"
        if self._already_complete(operation, executor): return True
        return self._write(operation, executor, {"runtime": self.sessions.snapshot()})

    def progress_inspect(self, operation: AdmittedOperation, payload: dict[str, Any]) -> bool:
        executor = "native.playables.progress.inspect"
        if self._already_complete(operation, executor): return True
        raw = payload.get("progression") or payload.get("state") or {}
        if not isinstance(raw, dict): raise ValueError("progression must be an object")
        stages = payload.get("known_stages") or ()
        if not isinstance(stages, (list, tuple)): raise ValueError("known_stages must be an array")
        return self._write(operation, executor, {"progression": inspect_progression(raw, known_stages=stages)})

    def _require_jeeves(self) -> KnowledgeAugmentedJeeves:
        if self.jeeves is None: raise RuntimeError("curiosity knowledge fabric unavailable")
        return self.jeeves

    def jeeves_reason(self, operation: AdmittedOperation, payload: dict[str, Any]) -> bool:
        executor = "native.jeeves.reason"
        if self._already_complete(operation, executor): return True
        return self._write(operation, executor, {"reasoning_frame": self._require_jeeves().reason(self._jeeves_payload(operation, payload))})

    def jeeves_plan(self, operation: AdmittedOperation, payload: dict[str, Any]) -> bool:
        executor = "native.jeeves.plan"
        if self._already_complete(operation, executor): return True
        return self._write(operation, executor, {"plan": self._require_jeeves().plan(self._jeeves_payload(operation, payload))})

    def agents_review(self, operation: AdmittedOperation, payload: dict[str, Any]) -> bool:
        executor = "native.jeeves.agents.review"
        if self._already_complete(operation, executor): return True
        return self._write(operation, executor, {"review": self._require_jeeves().review(self._jeeves_payload(operation, payload))})

    def ops_runtime(self, operation: AdmittedOperation, payload: dict[str, Any]) -> bool:
        executor = "native.operations.ops.runtime"
        if self._already_complete(operation, executor): return True
        result = self._provider_result(self.operations_provider, "operations"); result["sessions"] = self.sessions.snapshot(); result["receipts"] = self.receipts.stats()
        if self.curiosity is not None: result["curiosity"] = self.curiosity.stats()
        return self._write(operation, executor, result)

    def ops_deployments(self, operation: AdmittedOperation, payload: dict[str, Any]) -> bool:
        executor = "native.operations.ops.deployments"
        if self._already_complete(operation, executor): return True
        return self._write(operation, executor, {"deployment_plan": compile_deployment_plan(payload)})

    def governance_policy(self, operation: AdmittedOperation, payload: dict[str, Any]) -> bool:
        executor = "native.governance.policy"
        if self._already_complete(operation, executor): return True
        return self._write(operation, executor, self._provider_result(self.policy_provider, "policy"))

    def governance_audit(self, operation: AdmittedOperation, payload: dict[str, Any]) -> bool:
        executor = "native.governance.audit"
        if self._already_complete(operation, executor): return True
        return self._write(operation, executor, self._provider_result(self.audit_provider, "audit"))

    def governance_safety(self, operation: AdmittedOperation, payload: dict[str, Any]) -> bool:
        executor = "native.governance.safety"
        if self._already_complete(operation, executor): return True
        return self._write(operation, executor, self._provider_result(self.safety_provider, "safety"))

    def register_into(self, registry: ProductExecutorRegistry) -> ProductExecutorRegistry:
        registry.register("studio", "project.create", self.create_project, name="native.studio.project.create", version=1, effect_class="state", replay_safe=True)
        if self.operations_provider is not None: registry.register("studio", "pipeline.inspect", self.pipeline_inspect, name="native.studio.pipeline.inspect", version=1, effect_class="query", replay_safe=True)
        registry.register("world-forge", "world.create", self.create_world, name="native.worldforge.world.create", version=1, effect_class="state", replay_safe=True)
        registry.register("world-forge", "world.systems.compose", self.compose_world_systems, name="native.worldforge.world.systems.compose", version=1, effect_class="state", replay_safe=True)
        registry.register("playables", "playable.launch", self.launch_playable, name="native.playables.playable.launch", version=1, effect_class="state", replay_safe=True)
        registry.register("playables", "runtime.sessions", self.runtime_sessions, name="native.playables.runtime.sessions", version=1, effect_class="query", replay_safe=True)
        registry.register("playables", "progress.inspect", self.progress_inspect, name="native.playables.progress.inspect", version=1, effect_class="query", replay_safe=True)
        if self.jeeves is not None:
            registry.register("jeeves", "jeeves.reason", self.jeeves_reason, name="native.jeeves.reason", version=1, effect_class="state", replay_safe=True)
            registry.register("jeeves", "jeeves.plan", self.jeeves_plan, name="native.jeeves.plan", version=1, effect_class="state", replay_safe=True)
            registry.register("jeeves", "agents.review", self.agents_review, name="native.jeeves.agents.review", version=1, effect_class="state", replay_safe=True)
        if self.operations_provider is not None: registry.register("operations", "ops.runtime", self.ops_runtime, name="native.operations.ops.runtime", version=1, effect_class="query", replay_safe=True)
        registry.register("operations", "ops.deployments", self.ops_deployments, name="native.operations.ops.deployments", version=1, effect_class="query", replay_safe=True)
        if self.policy_provider is not None: registry.register("governance", "governance.policy", self.governance_policy, name="native.governance.policy", version=1, effect_class="query", replay_safe=True)
        if self.audit_provider is not None: registry.register("governance", "governance.audit", self.governance_audit, name="native.governance.audit", version=1, effect_class="query", replay_safe=True)
        if self.safety_provider is not None: registry.register("governance", "governance.safety", self.governance_safety, name="native.governance.safety", version=1, effect_class="query", replay_safe=True)
        return registry


def build_default_executor_registry(receipt_store: ExecutionReceiptStore, *, sessions: RuntimeSessionManager | None = None,
                                    curiosity: CuriosityEngine | None = None, operations_provider: Provider | None = None,
                                    policy_provider: Provider | None = None, audit_provider: Provider | None = None,
                                    safety_provider: Provider | None = None) -> tuple[ProductExecutorRegistry, NativeProductExecutors]:
    registry = ProductExecutorRegistry()
    adapters = NativeProductExecutors(receipt_store, sessions=sessions, curiosity=curiosity,
                                      operations_provider=operations_provider, policy_provider=policy_provider,
                                      audit_provider=audit_provider, safety_provider=safety_provider)
    adapters.register_into(registry); return registry, adapters
