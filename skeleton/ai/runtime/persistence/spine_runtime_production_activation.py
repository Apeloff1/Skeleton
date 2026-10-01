"""One-time production activation state transition for the P2 runtime spine."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any

from skeleton.contracts.operation import OperationState
from skeleton.persistence.consistency_fence import SQLiteConsistencyFence
from skeleton.persistence.operation_runtime import DurableOperationRuntime
from skeleton.persistence.spine_runtime_transition_slot import SpineRuntimeSlot


class SpineRuntimeProductionActivationError(RuntimeError):
    """Production activation failed closed."""


def _digest(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _instant(value: object, field: str) -> datetime:
    if not isinstance(value, str):
        raise SpineRuntimeProductionActivationError(
            f"{field} must be ISO-8601 text"
        )
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise SpineRuntimeProductionActivationError(
            f"{field} is not valid ISO-8601"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise SpineRuntimeProductionActivationError(
            f"{field} must be timezone-aware"
        )
    return parsed.astimezone(timezone.utc)


class SpineRuntimeProductionActivationLedger:
    """Consume exact authorization and live health into one activation record."""

    def __init__(self, path: str | Path = ":memory:") -> None:
        self._connection = sqlite3.connect(str(path), check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS spine_runtime_production_activation (
                activation_id TEXT PRIMARY KEY,
                authorization_digest TEXT NOT NULL UNIQUE,
                authorization_id TEXT NOT NULL UNIQUE,
                health_digest TEXT NOT NULL UNIQUE,
                execution_id TEXT NOT NULL UNIQUE,
                deployment_id TEXT NOT NULL,
                operation_id TEXT NOT NULL,
                activated_at TEXT NOT NULL,
                slot_generation INTEGER NOT NULL,
                fence_epoch INTEGER NOT NULL,
                payload_digest TEXT NOT NULL
            )
            """
        )
        self._connection.commit()

    def activate(
        self,
        *,
        authorization: dict[str, Any],
        authorization_verify: dict[str, Any],
        health: dict[str, Any],
        health_verify: dict[str, Any],
        slot: SpineRuntimeSlot,
        candidate_runtime: DurableOperationRuntime,
        fence: SQLiteConsistencyFence,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        if (
            not isinstance(authorization, dict)
            or authorization.get("kind")
            != "spine_runtime_production_activation_authorization"
            or authorization.get("authorization_authenticated") is not True
            or authorization.get("activation_accepted") is not True
            or authorization.get("production_activation_authorized") is not True
            or authorization.get("rollback_available") is not True
            or authorization.get("runtime_activated") is not False
        ):
            raise SpineRuntimeProductionActivationError(
                "verified production activation authorization is required"
            )
        authorization_id = authorization.get("authorization_id")
        authorization_digest = authorization.get("digest")
        health_digest = authorization.get("health_digest")
        execution_id = authorization.get("execution_id")
        deployment_id = authorization.get("deployment_id")
        for field, value in (
            ("authorization identity", authorization_id),
            ("authorization digest", authorization_digest),
            ("health digest", health_digest),
            ("execution identity", execution_id),
        ):
            if not isinstance(value, str) or len(value) != 64:
                raise SpineRuntimeProductionActivationError(
                    f"{field} is invalid"
                )
        if not isinstance(deployment_id, str) or not deployment_id:
            raise SpineRuntimeProductionActivationError(
                "deployment identity is missing"
            )
        if authorization.get("target_driver") != "pymongo-async":
            raise SpineRuntimeProductionActivationError(
                "activation target driver changed"
            )
        if (
            not isinstance(authorization_verify, dict)
            or authorization_verify.get("kind")
            != "spine_runtime_production_activation_authorization_verify"
            or authorization_verify.get("verified") is not True
            or authorization_verify.get("authorization_id") != authorization_id
            or authorization_verify.get("authorization_digest")
            != authorization_digest
            or authorization_verify.get("health_digest") != health_digest
            or authorization_verify.get("execution_id") != execution_id
            or authorization_verify.get("production_activation_authorized")
            is not True
            or authorization_verify.get("rollback_available") is not True
            or authorization_verify.get("runtime_activated") is not False
        ):
            raise SpineRuntimeProductionActivationError(
                "independent production activation authorization verification "
                "is required"
            )

        if (
            not isinstance(health, dict)
            or health.get("kind") != "spine_runtime_transition_health"
            or health.get("digest") != health_digest
            or health.get("execution_id") != execution_id
            or health.get("deployment_id") != deployment_id
            or health.get("health_qualified") is not True
            or health.get("operation_continuity") is not True
            or health.get("dispatcher_running") is not True
            or health.get("fence_stable") is not True
            or health.get("rollback_available") is not True
            or health.get("runtime_activated") is not False
        ):
            raise SpineRuntimeProductionActivationError(
                "exact live transition health is required"
            )
        if health.get("target_driver") != "pymongo-async":
            raise SpineRuntimeProductionActivationError(
                "health target driver changed"
            )
        if (
            not isinstance(health_verify, dict)
            or health_verify.get("kind")
            != "spine_runtime_transition_health_verify"
            or health_verify.get("verified") is not True
            or health_verify.get("health_digest") != health_digest
            or health_verify.get("execution_id") != execution_id
            or health_verify.get("operation_continuity") is not True
            or health_verify.get("rollback_available") is not True
            or health_verify.get("runtime_activated") is not False
        ):
            raise SpineRuntimeProductionActivationError(
                "independent live health verification is required"
            )

        instant = now or datetime.now(timezone.utc)
        if instant.tzinfo is None or instant.utcoffset() is None:
            raise SpineRuntimeProductionActivationError(
                "now must be timezone-aware"
            )
        instant = instant.astimezone(timezone.utc)
        valid_until = _instant(
            authorization.get("valid_until"),
            "authorization valid_until",
        )
        if instant >= valid_until:
            raise SpineRuntimeProductionActivationError(
                "production activation authorization expired"
            )

        if not isinstance(slot, SpineRuntimeSlot):
            raise SpineRuntimeProductionActivationError(
                "runtime slot is required"
            )
        if not isinstance(candidate_runtime, DurableOperationRuntime):
            raise SpineRuntimeProductionActivationError(
                "candidate runtime must be durable"
            )
        if not isinstance(fence, SQLiteConsistencyFence):
            raise SpineRuntimeProductionActivationError(
                "consistency fence is required"
            )
        slot_generation = health.get("slot_generation")
        fence_epoch = health.get("fence_epoch")
        operation_id = health.get("operation_id")
        operation_version = health.get("operation_version")
        tenant_id = health.get("tenant_id")
        resource_id = health.get("resource_id")
        if (
            isinstance(slot_generation, bool)
            or not isinstance(slot_generation, int)
            or slot_generation < 1
        ):
            raise SpineRuntimeProductionActivationError(
                "health slot generation is invalid"
            )
        if (
            isinstance(fence_epoch, bool)
            or not isinstance(fence_epoch, int)
            or fence_epoch < 2
        ):
            raise SpineRuntimeProductionActivationError(
                "health fence epoch is invalid"
            )
        if not isinstance(operation_id, str) or not operation_id:
            raise SpineRuntimeProductionActivationError(
                "health operation identity is missing"
            )
        if (
            isinstance(operation_version, bool)
            or not isinstance(operation_version, int)
            or operation_version < 1
        ):
            raise SpineRuntimeProductionActivationError(
                "health operation version is invalid"
            )
        if not isinstance(tenant_id, str) or not tenant_id:
            raise SpineRuntimeProductionActivationError(
                "health tenant identity is missing"
            )
        if not isinstance(resource_id, str) or not resource_id:
            raise SpineRuntimeProductionActivationError(
                "health resource identity is missing"
            )

        if slot.runtime is not candidate_runtime:
            raise SpineRuntimeProductionActivationError(
                "runtime slot is not on authorized candidate"
            )
        if slot.generation != slot_generation:
            raise SpineRuntimeProductionActivationError(
                "runtime slot generation changed before activation"
            )
        if candidate_runtime.dispatcher_running is not True:
            raise SpineRuntimeProductionActivationError(
                "candidate dispatcher is not running before activation"
            )
        token = fence.read(tenant_id=tenant_id, resource_id=resource_id)
        if token.epoch != fence_epoch:
            raise SpineRuntimeProductionActivationError(
                "transition fence epoch changed before activation"
            )
        if token.writer_id != f"runtime-transition:{deployment_id}":
            raise SpineRuntimeProductionActivationError(
                "transition fence writer changed before activation"
            )
        stored = candidate_runtime.operations.get(operation_id)
        if (
            stored.envelope.state is not OperationState.COMPLETED
            or stored.version != operation_version
        ):
            raise SpineRuntimeProductionActivationError(
                "live health operation changed before activation"
            )
        if candidate_runtime.operations.pending_outbox_count(
            operation_id=operation_id
        ) != 0:
            raise SpineRuntimeProductionActivationError(
                "live health outbox changed before activation"
            )

        activation_id = hashlib.sha256(
            (
                f"{authorization_digest}|{authorization_id}|{health_digest}|"
                f"{execution_id}|{deployment_id}|{slot_generation}|"
                f"{fence_epoch}|{operation_id}|pymongo-async"
            ).encode("utf-8")
        ).hexdigest()
        evidence = {
            "activation_id": activation_id,
            "authorization_id": authorization_id,
            "authorization_digest": authorization_digest,
            "health_digest": health_digest,
            "execution_id": execution_id,
            "deployment_id": deployment_id,
            "target_driver": "pymongo-async",
            "tenant_id": tenant_id,
            "resource_id": resource_id,
            "operation_id": operation_id,
            "operation_version": operation_version,
            "activated_at": instant.isoformat(),
            "slot_generation": slot_generation,
            "fence_epoch": fence_epoch,
            "authorization_consumed": True,
            "activation_accepted": True,
            "production_activation_authorized": True,
            "health_qualified": True,
            "operation_continuity": True,
            "runtime_object_replaced": True,
            "dispatcher_running": True,
            "fence_stable": True,
            "fence_moved_during_activation": False,
            "rollback_available": True,
            "runtime_activated": True,
        }
        payload_digest = _digest(evidence)
        try:
            self._connection.execute(
                """
                INSERT INTO spine_runtime_production_activation(
                    activation_id,authorization_digest,authorization_id,
                    health_digest,execution_id,deployment_id,operation_id,
                    activated_at,slot_generation,fence_epoch,payload_digest
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    activation_id,
                    authorization_digest,
                    authorization_id,
                    health_digest,
                    execution_id,
                    deployment_id,
                    operation_id,
                    instant.isoformat(),
                    slot_generation,
                    fence_epoch,
                    payload_digest,
                ),
            )
            self._connection.commit()
        except sqlite3.IntegrityError as exc:
            raise SpineRuntimeProductionActivationError(
                "production activation authorization replay refused"
            ) from exc

        return {
            "kind": "spine_runtime_production_activation",
            "hit": True,
            "law": "exact-authorized-live-health-may-activate-once",
            "citation": "VOL-134",
            **evidence,
            "digest": payload_digest,
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }

    def count(self) -> int:
        row = self._connection.execute(
            "SELECT COUNT(*) AS n FROM spine_runtime_production_activation"
        ).fetchone()
        return int(row["n"])

    def close(self) -> None:
        self._connection.close()
