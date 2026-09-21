"""Native executors for canonical product actions.

Adapters target framework-free runtime primitives instead of calling HTTP routes.
Receipts capture exact input provenance and executor contracts. Transform/query
executors are deterministic and attested; effectful executors must be replay-safe.
"""
from __future__ import annotations

from typing import Any, Callable

from core.academy_product import continue_learning, practice, progress as academy_progress
from core.curiosity_engine import CuriosityEngine
from core.deployment_planner import compile_deployment_plan
from core.gameforge_artifact_builder import build_source_artifact, build_web_artifact
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
    "native.studio.build.submit": (1, "state", True),
    "native.studio.pipeline.inspect": (1, "query", True),
    "native.worldforge.world.create": (1, "state", True),
    "native.worldforge.world.systems.compose": (1, "state", True),
    "native.worldforge.asset.forge": (1, "state", True),
    "native.playables.playable.launch": (1, "state", True),
    "native.playables.runtime.sessions": (1, "query", True),
    "native.playables.progress.inspect": (1, "query", True),
    "native.jeeves.reason": (1, "state", True),
    "native.jeeves.plan": (1, "state", True),
    "native.jeeves.agents.review": (1, "state", True),
    "native.academy.continue": (1, "query", True),
    "native.academy.practice": (1, "query", True),
    "native.academy.progress": (1, "query", True),
    "native.operations.ops.agents": (1, "query", True),
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

    def submit_build(self, operation: AdmittedOperation, payload: dict[str, Any]) -> bool:
        executor = "native.studio.build.submit"
        if self._already_complete(operation, executor): return True

        game_name_raw = payload.get("game_name")
        if game_name_raw is None:
            game_name_raw = payload.get("name") or payload.get("title")
        if not isinstance(game_name_raw, str) or not game_name_raw.strip():
            raise ValueError("game_name is required")
        game_name = game_name_raw.strip()
        if len(game_name) > 200:
            raise ValueError("game_name must be at most 200 characters")

        kind_raw = payload.get("kind", "web")
        if not isinstance(kind_raw, str):
            raise ValueError("kind must be a string")
        kind = kind_raw.strip().lower()
        if kind not in {"web", "source"}:
            raise ValueError("kind must be 'web' or 'source'")

        supplied = payload.get("files")
        files = None
        if supplied is not None:
            if not isinstance(supplied, list) or not all(isinstance(item, dict) for item in supplied):
                raise ValueError("files must be an array of objects when supplied")
            files = [dict(item) for item in supplied]

        builder = build_web_artifact if kind == "web" else build_source_artifact
        artifact = builder(
            game_name,
            files=files,
            build_token=operation.id,
        )
        public = dict(artifact)
        public.pop("path", None)
        return self._write(operation, executor, {"build": public})

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

    def forge_assets(self, operation: AdmittedOperation, payload: dict[str, Any]) -> bool:
        executor = "native.worldforge.asset.forge"
        if self._already_complete(operation, executor): return True
        from core import asset_forge, vault_gdd

        build_id = str(payload.get("build_id") or "").strip()
        if not build_id or len(build_id) > 200:
            raise ValueError("build_id is required and must be at most 200 characters")

        supplied = payload.get("items")
        if supplied is None:
            items = list(vault_gdd.read_gamefiles(build_id).get("items") or ())
        else:
            if not isinstance(supplied, list) or not all(isinstance(item, dict) for item in supplied):
                raise ValueError("items must be an array of objects when supplied")
            items = [dict(item) for item in supplied]
        if not items:
            raise ValueError("asset forge requires existing or supplied gamefile items")

        seed_raw = payload.get("seed", 0)
        if isinstance(seed_raw, bool):
            raise ValueError("seed must be an integer")
        try:
            seed = int(seed_raw)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError("seed must be an integer") from exc

        persist = payload.get("persist", True)
        if not isinstance(persist, bool):
            raise ValueError("persist must be a boolean")
        era_raw = payload.get("era")
        if era_raw is not None and not isinstance(era_raw, str):
            raise ValueError("era must be a string when supplied")
        era = era_raw.strip()[:100] if isinstance(era_raw, str) else None

        summary = asset_forge.forge_build_assets(
            build_id,
            items,
            seed,
            persist,
            era=era or None,
        )
        summary = dict(summary)
        summary.pop("assets", None)
        return self._write(operation, executor, {"asset_forge": summary})

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

    async def academy_continue(self, operation: AdmittedOperation, payload: dict[str, Any]) -> bool:
        executor = "native.academy.continue"
        if self._already_complete(operation, executor): return True
        return self._write(operation, executor, {"academy": await continue_learning(payload)})

    async def academy_practice(self, operation: AdmittedOperation, payload: dict[str, Any]) -> bool:
        executor = "native.academy.practice"
        if self._already_complete(operation, executor): return True
        return self._write(operation, executor, {"academy": await practice(payload)})

    async def academy_progress(self, operation: AdmittedOperation, payload: dict[str, Any]) -> bool:
        executor = "native.academy.progress"
        if self._already_complete(operation, executor): return True
        return self._write(operation, executor, {"academy": await academy_progress(payload)})

    def ops_agents(self, operation: AdmittedOperation, payload: dict[str, Any]) -> bool:
        executor = "native.operations.ops.agents"
        if self._already_complete(operation, executor): return True
        from core.swarm_agents import SWARM_DOMAINS

        category_raw = payload.get("category")
        query_raw = payload.get("query") or payload.get("q")
        if category_raw is not None and not isinstance(category_raw, str):
            raise ValueError("category must be a string when supplied")
        if query_raw is not None and not isinstance(query_raw, str):
            raise ValueError("query must be a string when supplied")
        category = category_raw.strip().lower() if isinstance(category_raw, str) else ""
        query = query_raw.strip().lower() if isinstance(query_raw, str) else ""

        limit_raw = payload.get("limit", 50)
        if isinstance(limit_raw, bool):
            raise ValueError("limit must be an integer")
        try:
            limit = int(limit_raw)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError("limit must be an integer") from exc
        if limit < 1 or limit > 200:
            raise ValueError("limit must be between 1 and 200")

        agents = list(SWARM_DOMAINS)
        if category:
            agents = [item for item in agents if str(item.get("category", "")).lower() == category]
        if query:
            agents = [
                item for item in agents
                if query in str(item.get("id", "")).lower()
                or query in str(item.get("domain", "")).lower()
                or query in str(item.get("agent", "")).lower()
                or any(query in str(keyword).lower() for keyword in item.get("expertise", ()))
            ]
        return self._write(
            operation,
            executor,
            {"agents": {"total": len(agents), "returned": min(len(agents), limit), "items": agents[:limit]}},
        )

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
        registry.register("studio", "build.submit", self.submit_build, name="native.studio.build.submit", version=1, effect_class="state", replay_safe=True)
        if self.operations_provider is not None: registry.register("studio", "pipeline.inspect", self.pipeline_inspect, name="native.studio.pipeline.inspect", version=1, effect_class="query", replay_safe=True)
        registry.register("world-forge", "world.create", self.create_world, name="native.worldforge.world.create", version=1, effect_class="state", replay_safe=True)
        registry.register("world-forge", "world.systems.compose", self.compose_world_systems, name="native.worldforge.world.systems.compose", version=1, effect_class="state", replay_safe=True)
        registry.register("world-forge", "asset.forge", self.forge_assets, name="native.worldforge.asset.forge", version=1, effect_class="state", replay_safe=True)
        registry.register("playables", "playable.launch", self.launch_playable, name="native.playables.playable.launch", version=1, effect_class="state", replay_safe=True)
        registry.register("playables", "runtime.sessions", self.runtime_sessions, name="native.playables.runtime.sessions", version=1, effect_class="query", replay_safe=True)
        registry.register("playables", "progress.inspect", self.progress_inspect, name="native.playables.progress.inspect", version=1, effect_class="query", replay_safe=True)
        if self.jeeves is not None:
            registry.register("jeeves", "jeeves.reason", self.jeeves_reason, name="native.jeeves.reason", version=1, effect_class="state", replay_safe=True)
            registry.register("jeeves", "jeeves.plan", self.jeeves_plan, name="native.jeeves.plan", version=1, effect_class="state", replay_safe=True)
            registry.register("jeeves", "agents.review", self.agents_review, name="native.jeeves.agents.review", version=1, effect_class="state", replay_safe=True)
        registry.register("academy", "academy.continue", self.academy_continue, name="native.academy.continue", version=1, effect_class="query", replay_safe=True)
        registry.register("academy", "academy.practice", self.academy_practice, name="native.academy.practice", version=1, effect_class="query", replay_safe=True)
        registry.register("academy", "academy.progress", self.academy_progress, name="native.academy.progress", version=1, effect_class="query", replay_safe=True)
        registry.register("operations", "ops.agents", self.ops_agents, name="native.operations.ops.agents", version=1, effect_class="query", replay_safe=True)
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
