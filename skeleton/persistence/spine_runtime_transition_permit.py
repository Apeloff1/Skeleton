"""Short-lived deployment execution permit for the P2 runtime transition."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any, Callable


class SpineRuntimeTransitionPermitError(RuntimeError):
    """Transition execution permit evidence failed closed."""


def _digest(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _instant(value: object, field: str) -> datetime:
    if not isinstance(value, str):
        raise SpineRuntimeTransitionPermitError(f"{field} must be ISO-8601 text")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise SpineRuntimeTransitionPermitError(f"{field} is not valid ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise SpineRuntimeTransitionPermitError(f"{field} must be timezone-aware")
    return parsed.astimezone(timezone.utc)


class SpineRuntimeTransitionPermitLedger:
    """Persist one externally authenticated transition permit per rehearsal."""

    def __init__(self, path: str | Path = ":memory:") -> None:
        self._connection = sqlite3.connect(str(path), check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS spine_runtime_transition_permit (
                permit_id TEXT PRIMARY KEY,
                rehearsal_digest TEXT NOT NULL UNIQUE,
                transition_id TEXT NOT NULL UNIQUE,
                execution_nonce TEXT NOT NULL UNIQUE,
                deployment_id TEXT NOT NULL,
                target_driver TEXT NOT NULL,
                issued_at TEXT NOT NULL,
                valid_until TEXT NOT NULL,
                payload_digest TEXT NOT NULL,
                consumed INTEGER NOT NULL DEFAULT 0 CHECK(consumed IN (0, 1))
            )
            """
        )
        self._connection.commit()

    def issue(
        self,
        *,
        rehearsal: dict[str, Any],
        rehearsal_verify: dict[str, Any],
        receipt: dict[str, Any],
        authenticate: Callable[[dict[str, Any]], bool],
        now: datetime | None = None,
    ) -> dict[str, Any]:
        if (
            not isinstance(rehearsal, dict)
            or rehearsal.get("kind") != "spine_runtime_transition_rehearsal"
            or rehearsal.get("transition_rehearsed") is not True
            or rehearsal.get("transition_attempted") is not False
            or rehearsal.get("transition_executed") is not False
            or rehearsal.get("runtime_activated") is not False
        ):
            raise SpineRuntimeTransitionPermitError("verified transition rehearsal is required")
        if rehearsal.get("runtime_driver_selected") is not True:
            raise SpineRuntimeTransitionPermitError("runtime driver selection is missing")
        for field in ("runtime_object_replaced", "dispatcher_called", "dispatcher_running", "fence_moved"):
            if rehearsal.get(field) is not False:
                raise SpineRuntimeTransitionPermitError(f"rehearsal invariant changed: {field}")
        if rehearsal.get("target_driver") != "pymongo-async":
            raise SpineRuntimeTransitionPermitError("transition target driver changed")

        rehearsal_digest = rehearsal.get("digest")
        transition_id = rehearsal.get("transition_id")
        deployment_id = rehearsal.get("deployment_id")
        if not isinstance(rehearsal_digest, str) or len(rehearsal_digest) != 64:
            raise SpineRuntimeTransitionPermitError("rehearsal digest is invalid")
        if not isinstance(transition_id, str) or len(transition_id) != 64:
            raise SpineRuntimeTransitionPermitError("transition identity is invalid")
        if not isinstance(deployment_id, str) or not deployment_id:
            raise SpineRuntimeTransitionPermitError("deployment identity is missing")

        if (
            not isinstance(rehearsal_verify, dict)
            or rehearsal_verify.get("kind") != "spine_runtime_transition_rehearsal_verify"
            or rehearsal_verify.get("verified") is not True
            or rehearsal_verify.get("rehearsal_digest") != rehearsal_digest
            or rehearsal_verify.get("transition_id") != transition_id
            or rehearsal_verify.get("transition_attempted") is not False
            or rehearsal_verify.get("transition_executed") is not False
            or rehearsal_verify.get("runtime_activated") is not False
        ):
            raise SpineRuntimeTransitionPermitError("independent rehearsal verification is required")

        if not callable(authenticate):
            raise SpineRuntimeTransitionPermitError("runtime-transition authenticator must be callable")
        if not isinstance(receipt, dict) or receipt.get("kind") != "spine_runtime_transition_execution_receipt":
            raise SpineRuntimeTransitionPermitError("transition execution receipt is missing")
        if receipt.get("authority_domain") != "runtime-transition-execution":
            raise SpineRuntimeTransitionPermitError("transition authority must be runtime-transition-execution")
        if receipt.get("decision") != "permit-transition":
            raise SpineRuntimeTransitionPermitError("transition decision must be permit-transition")
        if receipt.get("rehearsal_digest") != rehearsal_digest:
            raise SpineRuntimeTransitionPermitError("transition rehearsal scope mismatch")
        if receipt.get("transition_id") != transition_id:
            raise SpineRuntimeTransitionPermitError("transition identity scope mismatch")
        if receipt.get("deployment_id") != deployment_id:
            raise SpineRuntimeTransitionPermitError("deployment scope mismatch")
        if receipt.get("target_driver") != "pymongo-async":
            raise SpineRuntimeTransitionPermitError("transition target driver changed")

        nonce = receipt.get("execution_nonce")
        attestation = receipt.get("attestation_digest")
        if not isinstance(nonce, str) or len(nonce) != 64:
            raise SpineRuntimeTransitionPermitError("execution nonce is invalid")
        if not isinstance(attestation, str) or len(attestation) != 64:
            raise SpineRuntimeTransitionPermitError("execution attestation digest is invalid")

        instant = now or datetime.now(timezone.utc)
        if instant.tzinfo is None or instant.utcoffset() is None:
            raise SpineRuntimeTransitionPermitError("now must be timezone-aware")
        instant = instant.astimezone(timezone.utc)
        issued_at = _instant(receipt.get("issued_at"), "issued_at")
        expires_at = _instant(receipt.get("expires_at"), "expires_at")
        if issued_at > instant:
            raise SpineRuntimeTransitionPermitError("transition receipt is not yet valid")
        if expires_at <= instant or expires_at <= issued_at:
            raise SpineRuntimeTransitionPermitError("transition receipt is expired or invalid")
        if (expires_at - issued_at).total_seconds() > 120:
            raise SpineRuntimeTransitionPermitError("transition receipt lifetime exceeds two minutes")

        try:
            authenticated = authenticate(dict(receipt))
        except Exception as exc:
            raise SpineRuntimeTransitionPermitError("transition authentication failed closed") from exc
        if authenticated is not True:
            raise SpineRuntimeTransitionPermitError("transition receipt was not externally authenticated")

        permit_id = hashlib.sha256(
            f"{rehearsal_digest}|{transition_id}|{deployment_id}|{nonce}|pymongo-async".encode("utf-8")
        ).hexdigest()
        evidence = {
            "permit_id": permit_id,
            "rehearsal_digest": rehearsal_digest,
            "transition_id": transition_id,
            "deployment_id": deployment_id,
            "execution_nonce": nonce,
            "target_driver": "pymongo-async",
            "issued_at": instant.isoformat(),
            "valid_until": expires_at.isoformat(),
            "transition_authorized": True,
            "permit_consumed": False,
            "transition_attempted": False,
            "transition_executed": False,
            "runtime_driver_selected": True,
            "runtime_object_replaced": False,
            "dispatcher_started": False,
            "runtime_activated": False,
        }
        payload_digest = _digest(evidence)
        try:
            self._connection.execute(
                """
                INSERT INTO spine_runtime_transition_permit(
                    permit_id,rehearsal_digest,transition_id,execution_nonce,deployment_id,
                    target_driver,issued_at,valid_until,payload_digest,consumed
                ) VALUES (?,?,?,?,?,?,?,?,?,0)
                """,
                (
                    permit_id,rehearsal_digest,transition_id,nonce,deployment_id,
                    "pymongo-async",instant.isoformat(),expires_at.isoformat(),payload_digest,
                ),
            )
            self._connection.commit()
        except sqlite3.IntegrityError as exc:
            raise SpineRuntimeTransitionPermitError("transition permit replay or nonce reuse") from exc

        return {
            "kind": "spine_runtime_transition_permit",
            "hit": False,
            "law": "transition-rehearsal-requires-external-short-lived-execution-permit",
            "citation": "VOL-134",
            **evidence,
            "digest": payload_digest,
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }

    def consume(
        self,
        *,
        permit: dict[str, Any],
        permit_verify: dict[str, Any],
        now: datetime | None = None,
    ) -> dict[str, Any]:
        if not isinstance(permit, dict) or permit.get("kind") != "spine_runtime_transition_permit":
            raise SpineRuntimeTransitionPermitError("transition permit card is required")
        if permit.get("transition_authorized") is not True:
            raise SpineRuntimeTransitionPermitError("transition is not authorized")
        if permit.get("permit_consumed") is not False:
            raise SpineRuntimeTransitionPermitError("transition permit was already consumed")
        for field in ("transition_attempted", "transition_executed", "runtime_object_replaced", "dispatcher_started", "runtime_activated"):
            if permit.get(field) is not False:
                raise SpineRuntimeTransitionPermitError(f"transition permit changed invariant: {field}")
        if permit.get("runtime_driver_selected") is not True:
            raise SpineRuntimeTransitionPermitError("runtime driver selection disappeared")
        if permit.get("target_driver") != "pymongo-async":
            raise SpineRuntimeTransitionPermitError("transition target driver changed")

        permit_id = permit.get("permit_id")
        permit_digest = permit.get("digest")
        if not isinstance(permit_id, str) or len(permit_id) != 64:
            raise SpineRuntimeTransitionPermitError("transition permit identity is invalid")
        if not isinstance(permit_digest, str) or len(permit_digest) != 64:
            raise SpineRuntimeTransitionPermitError("transition permit digest is invalid")
        if (
            not isinstance(permit_verify, dict)
            or permit_verify.get("kind") != "spine_runtime_transition_permit_verify"
            or permit_verify.get("verified") is not True
            or permit_verify.get("permit_id") != permit_id
            or permit_verify.get("permit_digest") != permit_digest
            or permit_verify.get("transition_authorized") is not True
            or permit_verify.get("permit_consumed") is not False
            or permit_verify.get("transition_attempted") is not False
            or permit_verify.get("transition_executed") is not False
            or permit_verify.get("runtime_activated") is not False
        ):
            raise SpineRuntimeTransitionPermitError("independent transition-permit verification is required")

        valid_until = _instant(permit.get("valid_until"), "valid_until")
        instant = now or datetime.now(timezone.utc)
        if instant.tzinfo is None or instant.utcoffset() is None:
            raise SpineRuntimeTransitionPermitError("now must be timezone-aware")
        instant = instant.astimezone(timezone.utc)
        if instant >= valid_until:
            raise SpineRuntimeTransitionPermitError("transition permit expired before consumption")

        row = self._connection.execute(
            """
            SELECT rehearsal_digest,transition_id,execution_nonce,deployment_id,
                   target_driver,payload_digest,consumed
            FROM spine_runtime_transition_permit
            WHERE permit_id = ?
            """,
            (permit_id,),
        ).fetchone()
        if row is None:
            raise SpineRuntimeTransitionPermitError("transition permit is not durably recorded")
        checks = {
            "rehearsal_digest": permit.get("rehearsal_digest"),
            "transition_id": permit.get("transition_id"),
            "execution_nonce": permit.get("execution_nonce"),
            "deployment_id": permit.get("deployment_id"),
            "target_driver": permit.get("target_driver"),
            "payload_digest": permit_digest,
        }
        for field, expected in checks.items():
            if row[field] != expected:
                raise SpineRuntimeTransitionPermitError(f"persisted transition permit mismatch: {field}")
        if int(row["consumed"]) != 0:
            raise SpineRuntimeTransitionPermitError("transition permit replay refused")

        cursor = self._connection.execute(
            "UPDATE spine_runtime_transition_permit SET consumed = 1 WHERE permit_id = ? AND consumed = 0",
            (permit_id,),
        )
        if cursor.rowcount != 1:
            self._connection.rollback()
            raise SpineRuntimeTransitionPermitError("transition permit replay refused")
        self._connection.commit()

        evidence = {
            "permit_id": permit_id,
            "permit_digest": permit_digest,
            "rehearsal_digest": permit.get("rehearsal_digest"),
            "transition_id": permit.get("transition_id"),
            "deployment_id": permit.get("deployment_id"),
            "target_driver": "pymongo-async",
            "consumed_at": instant.isoformat(),
            "transition_authorized": True,
            "permit_consumed": True,
            "transition_attempted": False,
            "transition_executed": False,
            "runtime_driver_selected": True,
            "runtime_object_replaced": False,
            "dispatcher_started": False,
            "runtime_activated": False,
        }
        return {
            "kind": "spine_runtime_transition_consumption",
            "hit": False,
            "law": "transition-execution-permit-consumed-once-before-any-attempt",
            "citation": "VOL-134",
            **evidence,
            "digest": _digest(evidence),
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }

    def count(self) -> int:
        row = self._connection.execute("SELECT COUNT(*) AS n FROM spine_runtime_transition_permit").fetchone()
        return int(row["n"])

    def consumed_count(self) -> int:
        row = self._connection.execute(
            "SELECT COUNT(*) AS n FROM spine_runtime_transition_permit WHERE consumed = 1"
        ).fetchone()
        return int(row["n"])

    def close(self) -> None:
        self._connection.close()
