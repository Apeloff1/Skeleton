"""Deployment-owned refused transition attempt for the P2 runtime spine."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any, Callable

from skeleton.persistence.spine_dispatch_guard import SpineDispatchGuard
from skeleton.persistence.spine_epoch_witness import SpineEpochWitness


class SpineRuntimeTransitionAttemptError(RuntimeError):
    """Runtime transition attempt evidence failed closed."""


def _digest(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class SpineRuntimeTransitionAttemptLedger:
    """Persist one deployment-owned refused attempt per consumed execution permit."""

    def __init__(self, path: str | Path = ":memory:") -> None:
        self._connection = sqlite3.connect(str(path), check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS spine_runtime_transition_attempt (
                attempt_id TEXT PRIMARY KEY,
                consumption_digest TEXT NOT NULL UNIQUE,
                permit_id TEXT NOT NULL UNIQUE,
                transition_id TEXT NOT NULL UNIQUE,
                attempt_nonce TEXT NOT NULL UNIQUE,
                deployment_id TEXT NOT NULL,
                target_driver TEXT NOT NULL,
                attempted_at TEXT NOT NULL,
                result_digest TEXT NOT NULL,
                payload_digest TEXT NOT NULL
            )
            """
        )
        self._connection.commit()

    def attempt(
        self,
        *,
        consumption: dict[str, Any],
        consumption_verify: dict[str, Any],
        runtime: Any,
        epoch_before: int,
        epoch_after: int,
        execute_attempt: Callable[[dict[str, Any]], dict[str, Any]],
        now: datetime | None = None,
    ) -> dict[str, Any]:
        if (
            not isinstance(consumption, dict)
            or consumption.get("kind") != "spine_runtime_transition_consumption"
            or consumption.get("transition_authorized") is not True
            or consumption.get("permit_consumed") is not True
        ):
            raise SpineRuntimeTransitionAttemptError("verified consumed transition permit is required")
        if consumption.get("transition_attempted") is not False:
            raise SpineRuntimeTransitionAttemptError("transition was already attempted")
        if consumption.get("transition_executed") is not False:
            raise SpineRuntimeTransitionAttemptError("transition was already executed")
        if consumption.get("runtime_driver_selected") is not True:
            raise SpineRuntimeTransitionAttemptError("runtime driver selection is missing")
        for field in ("runtime_object_replaced", "dispatcher_started", "runtime_activated"):
            if consumption.get(field) is not False:
                raise SpineRuntimeTransitionAttemptError(f"consumption invariant changed: {field}")
        if consumption.get("target_driver") != "pymongo-async":
            raise SpineRuntimeTransitionAttemptError("transition target driver changed")

        consumption_digest = consumption.get("digest")
        permit_id = consumption.get("permit_id")
        transition_id = consumption.get("transition_id")
        deployment_id = consumption.get("deployment_id")
        for field, value in (
            ("consumption digest", consumption_digest),
            ("permit identity", permit_id),
            ("transition identity", transition_id),
        ):
            if not isinstance(value, str) or len(value) != 64:
                raise SpineRuntimeTransitionAttemptError(f"{field} is invalid")
        if not isinstance(deployment_id, str) or not deployment_id:
            raise SpineRuntimeTransitionAttemptError("deployment identity is missing")

        if (
            not isinstance(consumption_verify, dict)
            or consumption_verify.get("kind") != "spine_runtime_transition_consumption_verify"
            or consumption_verify.get("verified") is not True
            or consumption_verify.get("consumption_digest") != consumption_digest
            or consumption_verify.get("permit_id") != permit_id
            or consumption_verify.get("transition_id") != transition_id
            or consumption_verify.get("transition_authorized") is not True
            or consumption_verify.get("permit_consumed") is not True
            or consumption_verify.get("transition_attempted") is not False
            or consumption_verify.get("transition_executed") is not False
            or consumption_verify.get("runtime_activated") is not False
        ):
            raise SpineRuntimeTransitionAttemptError("independent consumption verification is required")

        if not callable(execute_attempt):
            raise SpineRuntimeTransitionAttemptError("deployment attempt executor must be callable")

        instant = now or datetime.now(timezone.utc)
        if instant.tzinfo is None or instant.utcoffset() is None:
            raise SpineRuntimeTransitionAttemptError("now must be timezone-aware")
        instant = instant.astimezone(timezone.utc)

        guard = SpineDispatchGuard()
        before = guard.snapshot(runtime)
        if getattr(runtime, "dispatcher_running", False) is not False:
            raise SpineRuntimeTransitionAttemptError("dispatcher is already running before transition attempt")

        command = {
            "kind": "spine_runtime_transition_attempt_command",
            "consumption_digest": consumption_digest,
            "permit_id": permit_id,
            "transition_id": transition_id,
            "deployment_id": deployment_id,
            "target_driver": "pymongo-async",
            "attempted_at": instant.isoformat(),
            "transition_authorized": True,
            "permit_consumed": True,
        }
        try:
            result = execute_attempt(dict(command))
        except Exception as exc:
            raise SpineRuntimeTransitionAttemptError("deployment transition attempt failed closed") from exc

        dispatch = guard.compare(before, runtime)
        if dispatch.get("same") is not True or dispatch.get("called") is not False:
            raise SpineRuntimeTransitionAttemptError("dispatcher identity changed during transition attempt")
        if getattr(runtime, "dispatcher_running", False) is not False:
            raise SpineRuntimeTransitionAttemptError("dispatcher started during refused transition attempt")

        epoch = SpineEpochWitness().card(
            epoch_before=epoch_before,
            epoch_after=epoch_after,
            side=consumption,
        )
        if epoch.get("moved") is not False:
            raise SpineRuntimeTransitionAttemptError("transition attempt moved fence")

        if not isinstance(result, dict) or result.get("kind") != "spine_runtime_transition_attempt_result":
            raise SpineRuntimeTransitionAttemptError("deployment transition attempt result is missing")
        if result.get("decision") != "refuse-transition":
            raise SpineRuntimeTransitionAttemptError("deployment transition attempt must fail closed")
        if result.get("transition_id") != transition_id:
            raise SpineRuntimeTransitionAttemptError("transition attempt identity scope mismatch")
        if result.get("deployment_id") != deployment_id:
            raise SpineRuntimeTransitionAttemptError("transition attempt deployment scope mismatch")
        if result.get("target_driver") != "pymongo-async":
            raise SpineRuntimeTransitionAttemptError("transition attempt target driver changed")
        if result.get("transition_executed") is not False:
            raise SpineRuntimeTransitionAttemptError("transition attempt reported execution")
        if result.get("runtime_activated") is not False:
            raise SpineRuntimeTransitionAttemptError("transition attempt reported activation")
        attempt_nonce = result.get("attempt_nonce")
        reason = result.get("reason")
        if not isinstance(attempt_nonce, str) or len(attempt_nonce) != 64:
            raise SpineRuntimeTransitionAttemptError("transition attempt nonce is invalid")
        if not isinstance(reason, str) or not reason:
            raise SpineRuntimeTransitionAttemptError("transition attempt refusal reason is missing")

        normalized_result = {
            "kind": "spine_runtime_transition_attempt_result",
            "decision": "refuse-transition",
            "transition_id": transition_id,
            "deployment_id": deployment_id,
            "target_driver": "pymongo-async",
            "attempt_nonce": attempt_nonce,
            "reason": reason,
            "transition_executed": False,
            "runtime_activated": False,
        }
        result_digest = _digest(normalized_result)
        attempt_id = hashlib.sha256(
            f"{consumption_digest}|{transition_id}|{deployment_id}|{attempt_nonce}|pymongo-async".encode("utf-8")
        ).hexdigest()
        evidence = {
            "attempt_id": attempt_id,
            "consumption_digest": consumption_digest,
            "permit_id": permit_id,
            "transition_id": transition_id,
            "deployment_id": deployment_id,
            "target_driver": "pymongo-async",
            "attempt_nonce": attempt_nonce,
            "attempted_at": instant.isoformat(),
            "result_digest": result_digest,
            "refusal_reason": reason,
            "transition_authorized": True,
            "permit_consumed": True,
            "transition_attempted": True,
            "transition_executed": False,
            "runtime_driver_selected": True,
            "runtime_object_replaced": False,
            "dispatcher_identity_stable": True,
            "dispatcher_started": False,
            "fence_moved": False,
            "runtime_activated": False,
        }
        payload_digest = _digest(evidence)
        try:
            self._connection.execute(
                """
                INSERT INTO spine_runtime_transition_attempt(
                    attempt_id,consumption_digest,permit_id,transition_id,attempt_nonce,
                    deployment_id,target_driver,attempted_at,result_digest,payload_digest
                ) VALUES (?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    attempt_id,
                    consumption_digest,
                    permit_id,
                    transition_id,
                    attempt_nonce,
                    deployment_id,
                    "pymongo-async",
                    instant.isoformat(),
                    result_digest,
                    payload_digest,
                ),
            )
            self._connection.commit()
        except sqlite3.IntegrityError as exc:
            raise SpineRuntimeTransitionAttemptError("transition attempt replay refused") from exc

        return {
            "kind": "spine_runtime_transition_attempt",
            "hit": False,
            "law": "consumed-transition-permit-allows-one-fail-closed-deployment-attempt",
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
            "SELECT COUNT(*) AS n FROM spine_runtime_transition_attempt"
        ).fetchone()
        return int(row["n"])

    def close(self) -> None:
        self._connection.close()
