"""Short-lived externally authorized activation permits for P2."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any, Callable


class SpineActivationPermitError(RuntimeError):
    """Activation permit evidence failed closed."""


def _digest(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    ).hexdigest()


def _instant(value: object, field: str) -> datetime:
    if not isinstance(value, str):
        raise SpineActivationPermitError(f"{field} must be ISO-8601 text")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise SpineActivationPermitError(f"{field} is not valid ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise SpineActivationPermitError(f"{field} must be timezone-aware")
    return parsed.astimezone(timezone.utc)


class SpineActivationPermitLedger:
    """Persist one external activation permit per gate digest and nonce."""

    def __init__(self, path: str | Path = ":memory:") -> None:
        self._connection = sqlite3.connect(str(path), check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS spine_activation_permit (
                permit_id TEXT PRIMARY KEY,
                activation_gate_digest TEXT NOT NULL UNIQUE,
                activation_nonce TEXT NOT NULL UNIQUE,
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
        activation_gate: dict[str, Any],
        activation_gate_verify: dict[str, Any],
        receipt: dict[str, Any],
        authenticate: Callable[[dict[str, Any]], bool],
        now: datetime | None = None,
    ) -> dict[str, Any]:
        if (
            not isinstance(activation_gate, dict)
            or activation_gate.get("kind") != "spine_runtime_activation_gate"
            or activation_gate.get("activation_eligible") is not True
            or activation_gate.get("runtime_driver_selected") is not True
            or activation_gate.get("runtime_activated") is not False
            or activation_gate.get("runtime_object_replaced") is not False
            or activation_gate.get("dispatcher_started") is not False
        ):
            raise SpineActivationPermitError("verified activation eligibility is required")
        gate_digest = activation_gate.get("digest")
        if not isinstance(gate_digest, str) or len(gate_digest) != 64:
            raise SpineActivationPermitError("activation gate digest is invalid")
        if (
            not isinstance(activation_gate_verify, dict)
            or activation_gate_verify.get("kind") != "spine_runtime_activation_gate_verify"
            or activation_gate_verify.get("verified") is not True
            or activation_gate_verify.get("activation_gate_digest") != gate_digest
            or activation_gate_verify.get("activation_eligible") is not True
            or activation_gate_verify.get("runtime_activated") is not False
        ):
            raise SpineActivationPermitError("independent activation-gate verification is required")
        if not callable(authenticate):
            raise SpineActivationPermitError("activation-control authenticator must be callable")
        if not isinstance(receipt, dict) or receipt.get("kind") != "spine_activation_control_receipt":
            raise SpineActivationPermitError("activation-control receipt is missing")
        if receipt.get("authority_domain") != "activation-control":
            raise SpineActivationPermitError("activation authority must be activation-control")
        if receipt.get("decision") != "permit-activation":
            raise SpineActivationPermitError("activation decision must be permit-activation")
        if receipt.get("activation_gate_digest") != gate_digest:
            raise SpineActivationPermitError("activation-control scope mismatch")
        if receipt.get("target_driver") != "pymongo-async":
            raise SpineActivationPermitError("activation target driver changed")
        nonce, attestation = receipt.get("activation_nonce"), receipt.get("attestation_digest")
        if not isinstance(nonce, str) or len(nonce) != 64:
            raise SpineActivationPermitError("activation nonce is invalid")
        if not isinstance(attestation, str) or len(attestation) != 64:
            raise SpineActivationPermitError("activation attestation digest is invalid")

        instant = now or datetime.now(timezone.utc)
        if instant.tzinfo is None or instant.utcoffset() is None:
            raise SpineActivationPermitError("now must be timezone-aware")
        instant = instant.astimezone(timezone.utc)
        issued_at = _instant(receipt.get("issued_at"), "issued_at")
        expires_at = _instant(receipt.get("expires_at"), "expires_at")
        if issued_at > instant:
            raise SpineActivationPermitError("activation receipt is not yet valid")
        if expires_at <= instant or expires_at <= issued_at:
            raise SpineActivationPermitError("activation receipt is expired or invalid")
        if (expires_at - issued_at).total_seconds() > 300:
            raise SpineActivationPermitError("activation receipt lifetime exceeds five minutes")
        try:
            authenticated = authenticate(dict(receipt))
        except Exception as exc:
            raise SpineActivationPermitError("activation-control authentication failed closed") from exc
        if authenticated is not True:
            raise SpineActivationPermitError("activation-control receipt was not externally authenticated")

        permit_id = hashlib.sha256(f"{gate_digest}|{nonce}|pymongo-async".encode("utf-8")).hexdigest()
        evidence = {
            "permit_id": permit_id,
            "activation_gate_digest": gate_digest,
            "activation_nonce": nonce,
            "target_driver": "pymongo-async",
            "issued_at": instant.isoformat(),
            "valid_until": expires_at.isoformat(),
            "activation_authorized": True,
            "permit_consumed": False,
            "runtime_driver_selected": True,
            "runtime_object_replaced": False,
            "dispatcher_started": False,
            "runtime_activated": False,
        }
        payload_digest = _digest(evidence)
        try:
            self._connection.execute(
                """INSERT INTO spine_activation_permit(
                    permit_id, activation_gate_digest, activation_nonce, target_driver,
                    issued_at, valid_until, payload_digest, consumed
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 0)""",
                (permit_id, gate_digest, nonce, "pymongo-async", instant.isoformat(), expires_at.isoformat(), payload_digest),
            )
            self._connection.commit()
        except sqlite3.IntegrityError as exc:
            raise SpineActivationPermitError("activation permit replay or nonce reuse") from exc
        return {
            "kind": "spine_activation_permit",
            "hit": False,
            "law": "activation-eligibility-requires-external-short-lived-permit",
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
        if not isinstance(permit, dict) or permit.get("kind") != "spine_activation_permit":
            raise SpineActivationPermitError("activation permit card is required")
        if permit.get("activation_authorized") is not True or permit.get("permit_consumed") is not False:
            raise SpineActivationPermitError("activation permit is not consumable")
        if permit.get("runtime_driver_selected") is not True or permit.get("runtime_activated") is not False:
            raise SpineActivationPermitError("activation permit runtime state is invalid")
        if permit.get("runtime_object_replaced") is not False or permit.get("dispatcher_started") is not False:
            raise SpineActivationPermitError("activation permit already changed runtime")
        permit_id, permit_digest = permit.get("permit_id"), permit.get("digest")
        if not isinstance(permit_id, str) or len(permit_id) != 64:
            raise SpineActivationPermitError("activation permit identity is invalid")
        if not isinstance(permit_digest, str) or len(permit_digest) != 64:
            raise SpineActivationPermitError("activation permit digest is invalid")
        if (
            not isinstance(permit_verify, dict)
            or permit_verify.get("kind") != "spine_activation_permit_verify"
            or permit_verify.get("verified") is not True
            or permit_verify.get("permit_id") != permit_id
            or permit_verify.get("permit_digest") != permit_digest
            or permit_verify.get("activation_authorized") is not True
            or permit_verify.get("permit_consumed") is not False
            or permit_verify.get("runtime_activated") is not False
        ):
            raise SpineActivationPermitError("independent activation permit verification is required")

        valid_until = _instant(permit.get("valid_until"), "valid_until")
        instant = now or datetime.now(timezone.utc)
        if instant.tzinfo is None or instant.utcoffset() is None:
            raise SpineActivationPermitError("now must be timezone-aware")
        instant = instant.astimezone(timezone.utc)
        if instant >= valid_until:
            raise SpineActivationPermitError("activation permit expired before consumption")

        row = self._connection.execute(
            """SELECT activation_gate_digest, activation_nonce, target_driver,
                      payload_digest, consumed
               FROM spine_activation_permit WHERE permit_id = ?""",
            (permit_id,),
        ).fetchone()
        if row is None:
            raise SpineActivationPermitError("activation permit is not durably recorded")
        if row["payload_digest"] != permit_digest:
            raise SpineActivationPermitError("persisted activation permit digest mismatch")
        if row["activation_gate_digest"] != permit.get("activation_gate_digest"):
            raise SpineActivationPermitError("persisted activation gate scope mismatch")
        if row["activation_nonce"] != permit.get("activation_nonce"):
            raise SpineActivationPermitError("persisted activation nonce mismatch")
        if row["target_driver"] != "pymongo-async":
            raise SpineActivationPermitError("persisted activation target changed")
        if int(row["consumed"]) != 0:
            raise SpineActivationPermitError("activation permit replay refused")

        cursor = self._connection.execute(
            "UPDATE spine_activation_permit SET consumed = 1 WHERE permit_id = ? AND consumed = 0",
            (permit_id,),
        )
        if cursor.rowcount != 1:
            self._connection.rollback()
            raise SpineActivationPermitError("activation permit replay refused")
        self._connection.commit()

        evidence = {
            "permit_id": permit_id,
            "permit_digest": permit_digest,
            "activation_gate_digest": permit.get("activation_gate_digest"),
            "target_driver": "pymongo-async",
            "consumed_at": instant.isoformat(),
            "activation_authorized": True,
            "permit_consumed": True,
            "runtime_driver_selected": True,
            "runtime_object_replaced": False,
            "dispatcher_started": False,
            "runtime_activated": False,
        }
        return {
            "kind": "spine_activation_consumption",
            "hit": False,
            "law": "activation-permit-consumed-once-before-runtime-transition",
            "citation": "VOL-134",
            **evidence,
            "digest": _digest(evidence),
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }

    def count(self) -> int:
        return int(self._connection.execute("SELECT COUNT(*) FROM spine_activation_permit").fetchone()[0])

    def consumed_count(self) -> int:
        return int(self._connection.execute(
            "SELECT COUNT(*) FROM spine_activation_permit WHERE consumed = 1"
        ).fetchone()[0])

    def close(self) -> None:
        self._connection.close()
