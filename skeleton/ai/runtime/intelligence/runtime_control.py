"""Operator control over existing serving, outcome learning and idle owners.

This is a coordinator helper, not a service, model executor or state store.
Desired host policy and tenant learning policy commit in the execution SQLite
transaction; disposable process state is reconciled from that authority.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import time
from collections.abc import Callable, Mapping
from collections import OrderedDict
from dataclasses import replace
from pathlib import Path
from typing import Any

from skeleton.contracts.runtime_optimization import (
    runtime_policy_controls,
    validate_runtime_policy_patch,
)

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


def _checkpoint_from_json(value: str) -> dict[str, Any]:
    """Parse the opaque checkpoint without a browser numeric rewrite."""
    if not isinstance(value, str) or len(value.encode("utf-8")) > 256 * 1024:
        raise ValueError("checkpoint exceeds the 256 KiB limit")

    def object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, item in pairs:
            if key in result:
                raise ValueError("checkpoint contains a duplicate JSON key")
            result[key] = item
        return result

    def invalid_constant(value: str) -> None:
        raise ValueError("checkpoint contains a non-finite number")

    try:
        parsed = json.loads(value, object_pairs_hook=object_pairs, parse_constant=invalid_constant)
    except (ValueError, RecursionError) as exc:
        raise ValueError("checkpoint must be an unambiguous finite JSON object") from exc
    if not isinstance(parsed, dict):
        raise ValueError("checkpoint must be a JSON object")
    return parsed


class RuntimeOptimizationControl:
    """Bounded host optimization with tenant-isolated learning projections."""

    def __init__(
        self,
        repository: Any,
        providers: Any,
        *,
        supervision_probe: Callable[[], Mapping[str, Any]] | None = None,
    ) -> None:
        self.repository = repository
        self.providers = providers
        self._supervision_probe = supervision_probe
        self._lock = threading.RLock()
        self._activity_lock = threading.Lock()
        self._foreground = 0
        self._enqueued_buckets: OrderedDict[str, int] = OrderedDict()
        self._last_activity_ns = time.time_ns()
        self._last_activity_monotonic_ns = time.monotonic_ns()
        self._applied_version = 0
        self._applied_cache_actions: dict[str, dict[str, int]] = {}
        self._applied_host_policy: dict[str, Any] = {}
        self._last_error: str | None = None
        self._closed = False
        self._maintenance = None
        self._maintenance_unavailable = "durable_execution_store_required"
        self._maintenance_retry_at = 0.0
        self._maintenance_retryable = False
        self._maintenance_coordination_error: str | None = None
        try:
            self._initialize_maintenance()
        except Exception as exc:
            # Optional upkeep must not prevent the configured AI from starting.
            self._maintenance_unavailable = "maintenance_initialization_" + type(exc).__name__
            self._maintenance_retryable = isinstance(exc, (sqlite3.OperationalError, OSError))
            self._maintenance_retry_at = time.monotonic() + 30.0
        self.reconcile()

    def _engines(self) -> tuple[Any, ...]:
        unique: dict[int, Any] = {}
        for row in self._routes():
            unique.setdefault(id(row["engine"]), row["engine"])
        return tuple(unique.values())

    def _routes(self) -> tuple[dict[str, Any], ...]:
        selector = getattr(self.providers, "runtime_serving_routes", None)
        if callable(selector):
            return tuple(selector())
        legacy = getattr(self.providers, "runtime_serving_engines", None)
        engines = tuple(legacy()) if callable(legacy) else ()
        return tuple(
            {
                "provider_id": "local",
                "model_id": getattr(engine.model, "model_id", "primary"),
                "route_id": "local:" + str(getattr(engine.model, "model_id", "primary")),
                "model_digest": getattr(engine.model, "model_digest", None),
                "engine": engine,
            }
            for engine in engines
        )

    def _selected_routes(self, route_id: str | None = None) -> tuple[dict[str, Any], ...]:
        rows = self._routes()
        if route_id is None:
            return rows
        selected = tuple(row for row in rows if row["route_id"] == route_id)
        if not selected:
            raise ValueError("selected local serving route is not configured")
        return selected

    @staticmethod
    def _serving_policy(policy: Mapping[str, Any], route_id: str) -> dict[str, Any]:
        return {**policy.get("serving", {}), **policy.get("serving_routes", {}).get(route_id, {})}

    @staticmethod
    def _route_draining(policy: Mapping[str, Any], route_id: str) -> bool:
        return policy.get("route_draining", {}).get(route_id, policy.get("draining", False))

    @staticmethod
    def _cache_action_versions(policy: Mapping[str, Any], route_id: str) -> dict[str, int]:
        epochs = policy.get("cache_actions", {})
        global_epochs = epochs.get("global", {})
        route_epochs = epochs.get("routes", {}).get(route_id, {})
        result = {
            action: max(global_epochs.get(action, 0), route_epochs.get(action, 0))
            for action in ("clear_cache", "trim_cache")
        }
        # Existing policy rows predate per-route epochs. Retain their last
        # cache action until the next operator mutation migrates the marker.
        legacy = policy.get("last_action", {})
        if legacy.get("action") in result and legacy.get("route_id") in (None, route_id):
            action = legacy["action"]
            result[action] = max(result[action], legacy.get("version", 0))
        return result

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
            IdleWorkKind.REPLAY_DEDUP: MaintenanceHandler(self._retain_learning, retry_safe=True),
            IdleWorkKind.ELIGIBLE_AUGMENTATION: MaintenanceHandler(self._maintain_learning, retry_safe=True),
        }
        # Separate connections share the declared execution database. No
        # process-wide agent, shadow database or autonomous provider is made.
        self._maintenance = create_studio_maintenance(
            store_path=Path(raw_path).expanduser().resolve(),
            telemetry_probe=self._telemetry,
            host_authorize=self._authorize_maintenance,
            callbacks=callbacks,
            after_verified_chunk=self._acknowledge_learning_chunk,
            maximum_history_events=2_000_000,
        )
        self._maintenance_unavailable = ""
        self._maintenance_retryable = False
        synchronize = getattr(self._maintenance, "synchronize_foreground", None)
        if callable(synchronize):
            with self._activity_lock:
                foreground = self._foreground
            try:
                synchronize(foreground)
            except Exception as exc:
                self._maintenance_coordination_error = type(exc).__name__

    def _recover_maintenance_initialization(self) -> None:
        if self._maintenance is not None or not self._maintenance_retryable or self._closed:
            return
        if time.monotonic() < self._maintenance_retry_at:
            return
        with self._lock:
            if self._maintenance is not None or self._closed:
                return
            self._maintenance_retry_at = time.monotonic() + 60.0
            try:
                self._initialize_maintenance()
                self._applied_version = 0
            except Exception as exc:
                self._maintenance_unavailable = "maintenance_initialization_" + type(exc).__name__
                self._maintenance_retryable = isinstance(exc, (sqlite3.OperationalError, OSError))

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
            scope_id=task.payload.get("learning_scope_id", "tenant"),
            max_partitions=1,
            idempotency_key=task.continuation_id,
        )
        checkpoint()
        return result

    def _retain_learning(self, task: Any, checkpoint: Any) -> dict[str, Any]:
        checkpoint()
        result = self.repository.runtime_learning_retention(
            tenant_id=task.payload["tenant_id"],
            scope_id=task.payload.get("learning_scope_id", "tenant"),
            max_rows=128,
        )
        checkpoint()
        return result

    def _acknowledge_learning_chunk(self, task: Any, result: Any, receipt: Any) -> None:
        """Acknowledge optimizer output only after the idle owner verifies it."""
        output = result.output
        if not isinstance(output, Mapping) or "maintenance_receipt_digest" not in output:
            return
        self.repository.acknowledge_runtime_learning_maintenance(
            tenant_id=task.payload["tenant_id"],
            scope_id=task.payload.get("learning_scope_id", "tenant"),
            idempotency_key=task.continuation_id,
            maintenance_receipt_digest=output["maintenance_receipt_digest"],
            completion_receipt_digest=receipt.digest,
        )

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
            quiet_ns = max(0, time.monotonic_ns() - self._last_activity_monotonic_ns)
            last_activity = max(0, now - quiet_ns)
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
            self._last_activity_monotonic_ns = time.monotonic_ns()
        if self._maintenance is not None:
            try:
                self._maintenance.foreground_started()
            except Exception as exc:
                self._maintenance_coordination_error = type(exc).__name__

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
            self._last_activity_monotonic_ns = time.monotonic_ns()
        if self._maintenance is not None:
            try:
                self._maintenance.foreground_finished()
            except Exception as exc:
                self._maintenance_coordination_error = type(exc).__name__
        if self._maintenance is None or self._closed:
            return
        if not self._maintenance.policy.enabled:
            return
        # Only terminal canonical outcomes may schedule local upkeep. Queue
        # identity coalesces per tenant/minute instead of growing per token.
        if self.repository.result(request.execution_id) is None:
            return
        tenant = request.context_policy.get("tenant_id") or request.tool_policy.get("tenant_id")
        if not isinstance(tenant, str) or not tenant:
            return
        learning_scope = _identity(
            request.context_policy.get("runtime_learning_scope_id", "tenant"), "learning scope"
        )
        from skeleton.jeeves.ai.idle_learning_scheduler import IdleWorkKind

        bucket = int(time.time()) // 60
        bucket_key = _digest({"tenant": tenant, "learning_scope": learning_scope})
        with self._activity_lock:
            if self._enqueued_buckets.get(bucket_key) == bucket:
                return
        checkpoint = self.repository.latest_checkpoint(request.execution_id)
        try:
            # The terminal outcome has already updated the canonical learner.
            # Recompute upkeep advice from current drift/source confidence and
            # actual serving pressure, rather than replaying request-start advice.
            advice = self.repository.runtime_learning_recommendation(
                tenant_id=tenant,
                scope_id=learning_scope,
                request=request,
                checkpoint_payload=None if checkpoint is None else dict(checkpoint.payload),
                pressure=self.pressure(),
                allowed_rounds=1,
                requested_rounds=1,
            )
        except Exception:
            advice = {"defer_background": True}
        priority = 10 if advice.get("defer_background") is True else 50
        kinds = [
            IdleWorkKind.CACHE_CLEANUP,
            IdleWorkKind.LEARNER_SNAPSHOT,
            IdleWorkKind.CHECKPOINT_COMPACTION,
            IdleWorkKind.REPLAY_DEDUP,
        ]
        if self._maintenance.policy.augmentation_enabled:
            kinds.append(IdleWorkKind.ELIGIBLE_AUGMENTATION)
        for kind in kinds:
            material = {
                "tenant": tenant,
                "learning_scope": learning_scope,
                "kind": kind.value,
                "bucket": bucket,
            }
            self._maintenance.enqueue(
                kind=kind,
                scope_id=self._maintenance_scope(tenant),
                source_digest=_digest(material),
                idempotency_key=_digest(material),
                payload={"tenant_id": tenant, "learning_scope_id": learning_scope},
                priority=priority,
            )
        with self._activity_lock:
            self._enqueued_buckets[bucket_key] = bucket
            self._enqueued_buckets.move_to_end(bucket_key)
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
                for route in self._routes():
                    engine, route_id = route["engine"], route["route_id"]
                    desired = self._serving_policy(policy, route_id)
                    previous = self._serving_policy(self._applied_host_policy, route_id)
                    if not self._applied_version or desired != previous:
                        engine.configure_serving(desired)
                    draining = self._route_draining(policy, route_id)
                    if not self._applied_version or draining != self._route_draining(
                        self._applied_host_policy, route_id
                    ):
                        engine.maintain("drain" if draining else "resume")
                if self._maintenance is not None and (
                    not self._applied_version
                    or policy.get("maintenance", {}) != self._applied_host_policy.get("maintenance", {})
                ):
                    from skeleton.jeeves.ai.studio_maintenance import StudioMaintenancePolicy

                    self._maintenance.configure(
                        replace(StudioMaintenancePolicy(), **policy.get("maintenance", {}))
                    )
                for route in self._routes():
                    route_id = route["route_id"]
                    markers = self._cache_action_versions(policy, route_id)
                    applied = self._applied_cache_actions.get(route_id, {})
                    clearing = markers["clear_cache"] > applied.get("clear_cache", 0)
                    if clearing:
                        route["engine"].maintain("clear_cache")
                    if markers["trim_cache"] > applied.get("trim_cache", 0) and (
                        not clearing or markers["trim_cache"] > markers["clear_cache"]
                    ):
                        route["engine"].maintain("trim_cache")
                    self._applied_cache_actions[route_id] = markers
                self._applied_version = version
                self._applied_host_policy = dict(policy)
                self._last_error = None
            except Exception as exc:
                # Desired state remains durable and will be retried; errors
                # reveal a type, never paths, credentials, prompts or payloads.
                self._last_error = type(exc).__name__

    def snapshot(self, *, actor_id: str, tenant_id: str, learning_offset: int = 0) -> dict[str, Any]:
        actor_id, tenant_id = _identity(actor_id, "actor_id"), _identity(tenant_id, "tenant_id")
        self.reconcile()
        state = self.repository.runtime_control_policy()
        routes = self._routes()
        primary = getattr(getattr(self.providers, "active", None), "model", None)
        models = [
            {
                **dict(row["engine"].snapshot().get("serving", {})),
                **{key: row.get(key) for key in ("provider_id", "model_id", "model_digest", "route_id")},
                "active": row["model_id"] == primary,
            }
            for row in routes
        ]
        if models:
            serving = dict(next((row for row in models if row["active"]), models[0]))
            serving["available"] = True
            serving["engine_count"] = len(models)
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
        serving["models"] = models
        learning = self.repository.runtime_learning_snapshot(
            tenant_id=tenant_id, limit=10, offset=learning_offset
        )
        learning["available"] = True
        try:
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
        except Exception as exc:
            self._maintenance_coordination_error = type(exc).__name__
            maintenance = {
                "available": False,
                "policy": {"enabled": False},
                "status": {"state": "degraded", "reason": "maintenance_observation_unavailable"},
                "recent_tasks": [],
            }
        maintenance.setdefault("available", self._maintenance is not None)
        maintenance["coordination"] = {
            "state": "degraded" if self._maintenance_coordination_error else "observed",
            "error_code": self._maintenance_coordination_error,
        }
        controls = runtime_policy_controls()
        controls["serving"].update(
            available=bool(routes),
            route_limits={
                row["route_id"]: {
                    "max_concurrency": row["engine"].max_concurrency,
                    "max_queue_size": row["engine"].max_queue_size,
                }
                for row in routes
            },
            global_limits={
                "max_concurrency": min((row["engine"].max_concurrency for row in routes), default=0),
                "max_queue_size": min((row["engine"].max_queue_size for row in routes), default=0),
            },
        )
        controls["learning"]["available"] = True
        controls["maintenance"]["available"] = (
            bool(maintenance.get("available"))
            and not self._maintenance_coordination_error
            and maintenance.get("status", {}).get("coordination_state") == "synchronized"
        )
        execution: dict[str, Any] = {"available": False}
        if self._supervision_probe is not None:
            try:
                observed = self._supervision_probe()
                execution = {
                    "available": True,
                    "active_executions": observed["active_task_count"],
                    "active_lifecycle_leases": observed["active_lease_count"],
                    "faulted": observed["faulted"],
                    "recovery": dict(observed["recovery"]),
                }
            except Exception as exc:
                execution = {"available": False, "error_code": type(exc).__name__}
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
            "execution": execution,
            "policy_controls": controls,
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
        serving_route_id: str | None = None,
    ) -> dict[str, Any]:
        _identity(actor_id, "actor_id")
        _identity(tenant_id, "tenant_id")
        if type(expected_version) is not int or expected_version < 1:
            raise ValueError("expected_version must be positive")
        if all(value is None for value in (serving, learning, maintenance, action)):
            raise ValueError("runtime control patch is empty")
        for label, values in (
            ("serving", serving),
            ("learning", learning),
            ("maintenance", maintenance),
        ):
            if values is None:
                continue
            validate_runtime_policy_patch(label, values)
        if action is not None and action not in ACTIONS:
            raise ValueError("unsupported runtime maintenance action")
        if serving_route_id is not None and serving is None and action is None:
            raise ValueError("a serving route requires a serving policy or action")
        routes = self._selected_routes(serving_route_id)
        if (serving is not None or action is not None) and not routes:
            raise ValueError("local serving is not configured")
        if maintenance is not None and self._maintenance is None:
            raise ValueError("maintenance is unavailable: " + self._maintenance_unavailable)
        with self._lock:
            current = self.repository.runtime_control_policy()
            policy = dict(current["policy"])
            if serving is not None:
                from skeleton.ai.runtime.inference.adaptive_serving import AdaptiveServingPolicy

                for route in routes:
                    engine = route["engine"]
                    desired = {**self._serving_policy(policy, route["route_id"]), **dict(serving)}
                    cap = int(engine.max_concurrency)
                    queue_cap = int(engine.max_queue_size)
                    AdaptiveServingPolicy.defaults(cap, queue_cap).updated(desired, cap, queue_cap)
                if serving_route_id is None:
                    policy["serving"] = {**policy.get("serving", {}), **dict(serving)}
                    overrides = {
                        key: {field: value for field, value in values.items() if field not in serving}
                        for key, values in policy.get("serving_routes", {}).items()
                    }
                    policy["serving_routes"] = {key: value for key, value in overrides.items() if value}
                else:
                    overrides = dict(policy.get("serving_routes", {}))
                    overrides[serving_route_id] = {**overrides.get(serving_route_id, {}), **dict(serving)}
                    policy["serving_routes"] = overrides
            if maintenance is not None:
                from skeleton.jeeves.ai.studio_maintenance import StudioMaintenancePolicy

                desired = {**policy.get("maintenance", {}), **dict(maintenance)}
                StudioMaintenancePolicy.from_mapping(desired)
                policy["maintenance"] = desired
            if action is not None:
                # Keep independent bounded epochs: an intervening command on
                # another model, or a trim after a clear, must not erase work
                # a different process has not reconciled yet.
                policy["cache_actions"] = {
                    "routes": {
                        row["route_id"]: self._cache_action_versions(policy, row["route_id"])
                        for row in self._routes()
                    },
                    "global": dict(policy.get("cache_actions", {}).get("global", {})),
                }
                if action in {"clear_cache", "trim_cache"}:
                    if serving_route_id is None:
                        policy["cache_actions"]["global"][action] = expected_version + 1
                    else:
                        policy["cache_actions"]["routes"][serving_route_id][action] = expected_version + 1
                if action in {"drain", "resume"}:
                    if serving_route_id is None:
                        policy["draining"] = action == "drain"
                        policy.pop("route_draining", None)
                    else:
                        policy["route_draining"] = {
                            **policy.get("route_draining", {}),
                            serving_route_id: action == "drain",
                        }
                policy["last_action"] = {
                    "action": action,
                    "actor_digest": _digest(actor_id),
                    "version": expected_version + 1,
                    "route_id": serving_route_id,
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
        self._recover_maintenance_initialization()
        self.reconcile()
        if self._maintenance is not None and not self._closed:
            try:
                self._maintenance.tick()
                self._maintenance_coordination_error = None
            except Exception as exc:
                self._maintenance_coordination_error = type(exc).__name__
                raise

    def retry_maintenance(
        self,
        *,
        actor_id: str,
        tenant_id: str,
        task_id: str,
        source_digest: str,
        expected_attempts: int,
    ) -> dict[str, Any]:
        _identity(actor_id, "actor_id")
        _identity(tenant_id, "tenant_id")
        self._learning_partition(task_id)
        self._learning_partition(source_digest)
        if type(expected_attempts) is not int or not 0 <= expected_attempts <= 1_000_000:
            raise ValueError("maintenance retry requires the observed attempt count")
        if self._maintenance is None or self._closed or self._maintenance_coordination_error:
            raise ValueError("maintenance coordination must be available before retry")
        result = self._maintenance.retry_failed(
            task_id=task_id,
            scope_id=self._maintenance_scope(tenant_id),
            source_digest=source_digest,
            expected_attempts=expected_attempts,
        )
        return {
            "schema_version": "skeleton.ai.runtime_maintenance_retry.v1",
            "actor_id": actor_id,
            "tenant_id": tenant_id,
            "task_id": task_id,
            "result": result,
            "runtime": self.snapshot(actor_id=actor_id, tenant_id=tenant_id),
        }

    def reset_maintenance_circuit(
        self,
        *,
        actor_id: str,
        tenant_id: str,
        kind: str,
        expected_generation: int,
        expected_failure_digest: str,
        source_digest: str,
    ) -> dict[str, Any]:
        from skeleton.jeeves.ai.idle_learning_scheduler import IdleWorkKind

        _identity(actor_id, "actor_id")
        _identity(tenant_id, "tenant_id")
        self._learning_partition(expected_failure_digest)
        self._learning_partition(source_digest)
        if type(expected_generation) is not int or not 1 <= expected_generation < 9_000_000_000_000_000:
            raise ValueError("maintenance circuit requires its observed generation")
        if self._maintenance is None or self._closed or self._maintenance_coordination_error:
            raise ValueError("maintenance coordination must be available before circuit reset")
        result = self._maintenance.reset_circuit(
            scope_id=self._maintenance_scope(tenant_id),
            kind=IdleWorkKind(kind),
            expected_generation=expected_generation,
            expected_failure_digest=expected_failure_digest,
            source_digest=source_digest,
        )
        return {
            "schema_version": "skeleton.ai.runtime_maintenance_circuit_reset.v1",
            "actor_id": actor_id,
            "tenant_id": tenant_id,
            "kind": kind,
            "result": result,
            "runtime": self.snapshot(actor_id=actor_id, tenant_id=tenant_id),
        }

    def export_learning_dataset(
        self,
        *,
        actor_id: str,
        tenant_id: str,
        limit: int = 128,
        cursor: str | None = None,
        partition_id: str | None = None,
        include_untrained: bool = False,
    ) -> dict[str, Any]:
        _identity(actor_id, "actor_id")
        _identity(tenant_id, "tenant_id")
        if partition_id is not None:
            self._learning_partition(partition_id)
        dataset = self.repository.runtime_learning_dataset_export(
            tenant_id=tenant_id,
            limit=limit,
            cursor=cursor,
            partition_id=partition_id,
            include_untrained=include_untrained,
        )
        raw = json.dumps(dataset, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
        if len(raw.encode("utf-8")) > 1024 * 1024:
            raise ValueError("learning dataset page exceeds its byte bound")
        return {
            "schema_version": "skeleton.ai.runtime_learning_dataset.v1",
            "actor_id": actor_id,
            "tenant_id": tenant_id,
            "dataset_json": raw,
        }

    @staticmethod
    def _learning_partition(partition_id: str) -> str:
        if (
            not isinstance(partition_id, str)
            or len(partition_id) != 64
            or any(char not in "0123456789abcdef" for char in partition_id)
        ):
            raise ValueError("learning partition must be a lowercase SHA-256 identity")
        return partition_id

    def export_learning_checkpoint(
        self,
        *,
        actor_id: str,
        tenant_id: str,
        partition_id: str,
        expected_state_version: int | None = None,
    ) -> dict[str, Any]:
        _identity(actor_id, "actor_id")
        _identity(tenant_id, "tenant_id")
        partition_id = self._learning_partition(partition_id)
        checkpoint = self.repository.runtime_learning_export(
            tenant_id=tenant_id,
            partition_id=partition_id,
            expected_version=expected_state_version,
        )
        return {
            "schema_version": "skeleton.ai.runtime_learning_checkpoint.v1",
            "actor_id": actor_id,
            "tenant_id": tenant_id,
            "partition_id": partition_id,
            "checkpoint_json": json.dumps(
                checkpoint, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
            ),
        }

    def configure_learning_checkpoint(
        self,
        *,
        actor_id: str,
        tenant_id: str,
        partition_id: str,
        action: str,
        expected_policy_version: int,
        expected_state_version: int,
        model_selection_digest: str,
        checkpoint: dict[str, Any] | None = None,
        checkpoint_json: str | None = None,
    ) -> dict[str, Any]:
        _identity(actor_id, "actor_id")
        _identity(tenant_id, "tenant_id")
        partition_id = self._learning_partition(partition_id)
        self._learning_partition(model_selection_digest)
        if action not in {"import", "reset", "restore_last_healthy"}:
            raise ValueError("unsupported learning checkpoint action")
        for version in (expected_policy_version, expected_state_version):
            if type(version) is not int or version < 1:
                raise ValueError("learning checkpoint versions must be positive integers")
        count = int(checkpoint is not None) + int(checkpoint_json is not None)
        if count != (1 if action == "import" else 0):
            raise ValueError(
                "import requires exactly one checkpoint representation; other actions accept neither"
            )
        if checkpoint_json is not None:
            checkpoint = _checkpoint_from_json(checkpoint_json)
        if checkpoint is not None:
            try:
                encoded = json.dumps(
                    checkpoint, separators=(",", ":"), ensure_ascii=False, allow_nan=False
                ).encode()
            except (TypeError, ValueError, RecursionError) as exc:
                raise ValueError("checkpoint must be finite JSON") from exc
            if len(encoded) > 256 * 1024:
                raise ValueError("checkpoint exceeds the 256 KiB limit")
        kwargs = {
            "tenant_id": tenant_id,
            "partition_id": partition_id,
            "expected_version": expected_state_version,
            "model_selection_digest": model_selection_digest,
            "expected_policy_version": expected_policy_version,
            "actor_id": actor_id,
        }
        if action == "import":
            mutation = self.repository.runtime_learning_import(**kwargs, checkpoint=checkpoint)
        else:
            mutation = self.repository.runtime_learning_reset(
                **kwargs,
                to_last_healthy=action == "restore_last_healthy",
            )
        return {
            "schema_version": "skeleton.ai.runtime_learning_control.v1",
            "actor_id": actor_id,
            "tenant_id": tenant_id,
            "partition_id": partition_id,
            "receipt": mutation["receipt"],
            "partition": {
                key: mutation[key] for key in ("partition_id", "model_selection_digest", "state_version")
            },
            "runtime": self.snapshot(actor_id=actor_id, tenant_id=tenant_id),
        }

    def close(self) -> None:
        with self._lock:
            self._closed = True
        if self._maintenance is not None:
            self._maintenance.close()
