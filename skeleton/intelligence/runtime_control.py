"""Operator control over existing serving, outcome learning and idle owners.

This is a coordinator helper, not a service, model executor or state store.
Desired host policy and tenant learning policy commit in the execution SQLite
transaction; disposable process state is reconciled from that authority.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from collections.abc import Mapping
from collections import OrderedDict
from dataclasses import replace
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "skeleton.ai.runtime_control.v1"
ACTIONS = frozenset({"trim_cache", "clear_cache", "drain", "resume"})


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def _identity(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or value != value.strip()
        or len(value) > 512
        or any(ord(char) < 32 for char in value)
    ):
        raise ValueError(f"{label} must be a canonical identity")
    return value


class RuntimeOptimizationControl:
    """Bounded host optimization with tenant-isolated learning projections."""

    def __init__(self, repository: Any, providers: Any) -> None:
        self.repository = repository
        self.providers = providers
        self._lock = threading.RLock()
        self._activity_lock = threading.Lock()
        self._foreground = 0
        self._enqueued_buckets: OrderedDict[str, int] = OrderedDict()
        self._last_activity_ns = time.time_ns()
        self._applied_version = 0
        self._applied_action_version = 0
        self._applied_host_policy: dict[str, Any] = {}
        self._last_error: str | None = None
        self._closed = False
        self._maintenance = None
        self._maintenance_unavailable = "durable_execution_store_required"
        try:
            self._initialize_maintenance()
        except Exception as exc:
            # Optional upkeep must not prevent the configured AI from starting.
            self._maintenance_unavailable = "maintenance_initialization_" + type(exc).__name__
        self.reconcile()

    def _engines(self) -> tuple[Any, ...]:
        selector = getattr(self.providers, "runtime_serving_engines", None)
        return tuple(selector()) if callable(selector) else ()

    def _initialize_maintenance(self) -> None:
        raw_path = getattr(self.repository, "path", ":memory:")
        if raw_path == ":memory:":
            return
        from skeleton.jeeves.ai.idle_learning_scheduler import IdleWorkKind
        from skeleton.jeeves.ai.studio_maintenance import (
            MaintenanceHandler,
            create_studio_maintenance,
        )

        callbacks = {
            IdleWorkKind.CACHE_CLEANUP: MaintenanceHandler(self._trim_idle_cache, retry_safe=True),
            IdleWorkKind.CHECKPOINT_COMPACTION: MaintenanceHandler(self._checkpoint_storage, retry_safe=True),
            IdleWorkKind.LEARNER_SNAPSHOT: MaintenanceHandler(self._maintain_learning, retry_safe=True),
            IdleWorkKind.REPLAY_DEDUP: MaintenanceHandler(self._maintain_learning, retry_safe=True),
            IdleWorkKind.ELIGIBLE_AUGMENTATION: MaintenanceHandler(self._maintain_learning, retry_safe=True),
        }
        # Separate connections share the declared execution database. No
        # process-wide agent, shadow database or autonomous provider is made.
        self._maintenance = create_studio_maintenance(
            store_path=Path(raw_path).expanduser().resolve(),
            telemetry_probe=self._telemetry,
            host_authorize=self._authorize_maintenance,
            callbacks=callbacks,
            maximum_history_events=2_000_000,
        )
        self._maintenance_unavailable = ""

    def _authorize_maintenance(self, assignment: Any, intent: Any, task: Any) -> bool:
        del intent
        tenant = task.payload.get("tenant_id")
        if not isinstance(tenant, str) or not tenant or self._closed:
            return False
        return (
            assignment.scope_id == self._maintenance_scope(tenant)
            and assignment.source_digest == task.source_digest
            and assignment.kind == task.kind
        )

    @staticmethod
    def _maintenance_scope(tenant_id: str) -> str:
        return "runtime-tenant-" + _digest(tenant_id)[:32]

    def _trim_idle_cache(self, task: Any, checkpoint: Any) -> dict[str, Any]:
        del task
        results = []
        for engine in self._engines():
            checkpoint()
            results.append(engine.maintain("trim_cache"))
        checkpoint()
        return {"engines": len(results), "action": "trim_cache"}

    def _maintain_learning(self, task: Any, checkpoint: Any) -> dict[str, Any]:
        checkpoint()
        result = self.repository.runtime_learning_maintenance(
            tenant_id=task.payload["tenant_id"],
            max_partitions=1,
        )
        checkpoint()
        return result

    def _checkpoint_storage(self, task: Any, checkpoint: Any) -> dict[str, Any]:
        del task
        checkpoint()
        result = self.repository.runtime_storage_maintenance()
        checkpoint()
        return result

    def _telemetry(self):
        from skeleton.ai.runtime.inference.local import sample_serving_resources
        from skeleton.jeeves.ai.idle_learning_scheduler import HostIdleTelemetry

        now = time.time_ns()
        resources = sample_serving_resources()
        active = queued = configured = 0
        for engine in self._engines():
            state = engine.snapshot()
            active += int(state.get("active", 0))
            queued += int(state.get("queued", 0))
            configured += int(getattr(engine, "max_concurrency", 1))
        with self._activity_lock:
            foreground = self._foreground
            last_activity = self._last_activity_ns
        cpu, memory = resources.cpu_load_fraction, resources.memory_used_fraction
        # Missing resource observations deny idle work rather than assuming
        # spare CPU/memory. Network/accelerator work is never registered here.
        cpu_free = 0 if cpu is None else int(max(0, min(1, 1 - cpu)) * 1_000_000)
        memory_free = 0 if memory is None else int(max(0, min(1, 1 - memory)) * 1_000_000)
        pressure = min(1_000_000, int((active + queued) / max(1, configured) * 1_000_000))
        observation = {
            "observed_at_ns": now,
            "active": active,
            "queued": queued,
            "foreground": foreground,
            "resources": resources.as_dict(),
        }
        return (
            HostIdleTelemetry(
                observed_at_ns=now,
                last_user_activity_ns=min(now, last_activity),
                serving_pressure_ppm=pressure,
                cpu_free_ppm=cpu_free,
                memory_free_ppm=memory_free,
                gpu_free_ppm=0,
                active_background_workers=0,
                pending_interactive_requests=min(10_000, foreground),
                power_saving=False,
                online=False,
                host_observation_digest=_digest(observation),
            ),
            now,
        )

    def foreground_started(self) -> None:
        with self._activity_lock:
            self._foreground += 1
            self._last_activity_ns = time.time_ns()
        if self._maintenance is not None:
            self._maintenance.foreground_started()

    def pressure(self) -> float:
        active = queued = capacity = 0
        for engine in self._engines():
            snapshot = engine.snapshot()
            active += int(snapshot.get("active", 0))
            queued += int(snapshot.get("queued", 0))
            capacity += int(getattr(engine, "max_concurrency", 1))
        with self._activity_lock:
            foreground = self._foreground
        return min(1.0, (active + queued + max(0, foreground - 1)) / max(1, capacity))

    def foreground_finished(self, request: Any) -> None:
        with self._activity_lock:
            self._foreground = max(0, self._foreground - 1)
            self._last_activity_ns = time.time_ns()
        if self._maintenance is not None:
            self._maintenance.foreground_finished()
        if self._maintenance is None or self._closed:
            return
        if not self._maintenance.policy.enabled:
            return
        # Only terminal canonical outcomes may schedule local upkeep. Queue
        # identity coalesces per tenant/minute instead of growing per token.
        if self.repository.result(request.execution_id) is None:
            return
        checkpoint = self.repository.latest_checkpoint(request.execution_id)
        advice = {} if checkpoint is None else checkpoint.payload.get("runtime_learning", {})
        priority = 10 if isinstance(advice, Mapping) and advice.get("defer_background") is True else 50
        tenant = request.context_policy.get("tenant_id") or request.tool_policy.get("tenant_id")
        if not isinstance(tenant, str) or not tenant:
            return
        from skeleton.jeeves.ai.idle_learning_scheduler import IdleWorkKind

        bucket = int(time.time()) // 60
        with self._activity_lock:
            if self._enqueued_buckets.get(tenant) == bucket:
                return
        kinds = [
            IdleWorkKind.CACHE_CLEANUP,
            IdleWorkKind.LEARNER_SNAPSHOT,
            IdleWorkKind.CHECKPOINT_COMPACTION,
            IdleWorkKind.REPLAY_DEDUP,
        ]
        if self._maintenance.policy.augmentation_enabled:
            kinds.append(IdleWorkKind.ELIGIBLE_AUGMENTATION)
        for kind in kinds:
            material = {"tenant": tenant, "kind": kind.value, "bucket": bucket}
            self._maintenance.enqueue(
                kind=kind,
                scope_id=self._maintenance_scope(tenant),
                source_digest=_digest(material),
                idempotency_key=_digest(material),
                payload={"tenant_id": tenant},
                priority=priority,
            )
        with self._activity_lock:
            self._enqueued_buckets[tenant] = bucket
            self._enqueued_buckets.move_to_end(tenant)
            while len(self._enqueued_buckets) > 256:
                self._enqueued_buckets.popitem(last=False)

    def reconcile(self) -> None:
        """Apply durable desired state, including updates from another worker."""
        with self._lock:
            if self._closed:
                return
            try:
                state = self.repository.runtime_control_policy()
                version, policy = state["version"], state["policy"]
                if version == self._applied_version:
                    return
                for engine in self._engines():
                    if not self._applied_version or policy.get(
                        "serving", {}
                    ) != self._applied_host_policy.get("serving", {}):
                        engine.configure_serving(policy.get("serving", {}))
                    if not self._applied_version or policy.get(
                        "draining", False
                    ) != self._applied_host_policy.get("draining", False):
                        engine.maintain("drain" if policy.get("draining", False) else "resume")
                if self._maintenance is not None and (
                    not self._applied_version
                    or policy.get("maintenance", {}) != self._applied_host_policy.get("maintenance", {})
                ):
                    from skeleton.jeeves.ai.studio_maintenance import StudioMaintenancePolicy

                    self._maintenance.configure(
                        replace(StudioMaintenancePolicy(), **policy.get("maintenance", {}))
                    )
                action = policy.get("last_action")
                action_version = action.get("version", 0) if isinstance(action, Mapping) else 0
                if isinstance(action, Mapping) and action_version != self._applied_action_version:
                    if action.get("action") in {"trim_cache", "clear_cache"}:
                        for engine in self._engines():
                            engine.maintain(action["action"])
                    self._applied_action_version = action_version
                self._applied_version = version
                self._applied_host_policy = dict(policy)
                self._last_error = None
            except Exception as exc:
                # Desired state remains durable and will be retried; errors
                # reveal a type, never paths, credentials, prompts or payloads.
                self._last_error = type(exc).__name__

    def snapshot(self, *, actor_id: str, tenant_id: str) -> dict[str, Any]:
        actor_id, tenant_id = _identity(actor_id, "actor_id"), _identity(tenant_id, "tenant_id")
        self.reconcile()
        state = self.repository.runtime_control_policy()
        engines = self._engines()
        if engines:
            serving = dict(engines[0].snapshot().get("serving", {}))
            serving["available"] = True
            serving["engine_count"] = len(engines)
        else:
            serving = {
                "available": False,
                "policy": {},
                "reason": "local_serving_not_configured",
                "capacity": {},
                "pressure": {},
                "cache": {},
                "draining": False,
            }
        serving["desired_policy"] = state["policy"].get("serving", {})
        learning = self.repository.runtime_learning_snapshot(tenant_id=tenant_id, limit=10)
        learning["available"] = True
        maintenance = (
            self._maintenance.snapshot(scope_id=self._maintenance_scope(tenant_id))
            if self._maintenance is not None
            else {
                "available": False,
                "policy": {"enabled": False},
                "status": {"state": "unavailable", "reason": self._maintenance_unavailable},
                "recent_tasks": [],
            }
        )
        maintenance.setdefault("available", self._maintenance is not None)
        return {
            "schema_version": SCHEMA_VERSION,
            "actor_id": actor_id,
            "tenant_id": tenant_id,
            "policy_version": state["version"],
            "applied_policy_version": self._applied_version,
            "control_scope": {"serving": "host", "maintenance": "host", "learning": "tenant"},
            "reconciliation": {
                "state": "pending" if self._last_error else "applied",
                "error_code": self._last_error,
            },
            "control_history": self.repository.runtime_control_history(tenant_id=tenant_id, limit=10),
            "serving": serving,
            "learning": learning,
            "maintenance": maintenance,
            "ratchet": {
                "available": False,
                "reason": "campaign_owned_observatory",
                "policy": {"automatic_promotion": False},
            },
        }

    def configure(
        self,
        *,
        actor_id: str,
        tenant_id: str,
        expected_version: int,
        serving: Mapping[str, Any] | None = None,
        learning: Mapping[str, Any] | None = None,
        maintenance: Mapping[str, Any] | None = None,
        action: str | None = None,
    ) -> dict[str, Any]:
        _identity(actor_id, "actor_id")
        _identity(tenant_id, "tenant_id")
        if type(expected_version) is not int or expected_version < 1:
            raise ValueError("expected_version must be positive")
        if all(value is None for value in (serving, learning, maintenance, action)):
            raise ValueError("runtime control patch is empty")
        for label, values, fields in (
            ("serving", serving, {"enabled", "max_effective_concurrency"}),
            ("learning", learning, {"enabled"}),
            ("maintenance", maintenance, {"enabled", "augmentation_enabled"}),
        ):
            if values is None:
                continue
            if not isinstance(values, Mapping) or not values or set(values) - fields:
                raise ValueError(f"invalid {label} policy fields")
            for flag in {"enabled", "augmentation_enabled"}.intersection(values):
                if type(values[flag]) is not bool:
                    raise ValueError(f"{label} {flag} must be boolean")
        if action is not None and action not in ACTIONS:
            raise ValueError("unsupported runtime maintenance action")
        engines = self._engines()
        if (serving is not None or action is not None) and not engines:
            raise ValueError("local serving is not configured")
        if maintenance is not None and self._maintenance is None:
            raise ValueError("maintenance requires durable execution storage")
        with self._lock:
            current = self.repository.runtime_control_policy()
            policy = dict(current["policy"])
            if serving is not None:
                desired = {**policy.get("serving", {}), **dict(serving)}
                from skeleton.ai.runtime.inference.adaptive_serving import AdaptiveServingPolicy

                for engine in engines:
                    cap = int(engine.max_concurrency)
                    AdaptiveServingPolicy.defaults(cap).updated(desired, cap)
                policy["serving"] = desired
            if maintenance is not None:
                policy["maintenance"] = {**policy.get("maintenance", {}), **dict(maintenance)}
            if action is not None:
                if action in {"drain", "resume"}:
                    policy["draining"] = action == "drain"
                policy["last_action"] = {
                    "action": action,
                    "actor_digest": _digest(actor_id),
                    "version": expected_version + 1,
                }
            self.repository.set_runtime_control_policy(
                policy,
                expected_version,
                actor_id=actor_id,
                tenant_id=tenant_id,
                learning_policy=None if learning is None else dict(learning),
            )
            self.reconcile()
        return self.snapshot(actor_id=actor_id, tenant_id=tenant_id)

    def tick(self) -> None:
        self.reconcile()
        if self._maintenance is not None and not self._closed:
            self._maintenance.tick()

    def close(self) -> None:
        with self._lock:
            self._closed = True
        if self._maintenance is not None:
            self._maintenance.close()
