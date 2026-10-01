"""Externally authenticated production-activation authorization for P2."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any, Callable


class SpineRuntimeProductionActivationAuthorizationError(RuntimeError):
    """Production activation authorization failed closed."""


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
        raise SpineRuntimeProductionActivationAuthorizationError(
            f"{field} must be ISO-8601 text"
        )
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise SpineRuntimeProductionActivationAuthorizationError(
            f"{field} is not valid ISO-8601"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise SpineRuntimeProductionActivationAuthorizationError(
            f"{field} must be timezone-aware"
        )
    return parsed.astimezone(timezone.utc)


class SpineRuntimeProductionActivationAuthorizationLedger:
    """Persist one external activation authorization per accepted transition."""

    def __init__(self, path: str | Path = ":memory:") -> None:
        self._connection = sqlite3.connect(str(path), check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS spine_runtime_production_activation_authorization (
                authorization_id TEXT PRIMARY KEY,
                acceptance_digest TEXT NOT NULL UNIQUE,
                acceptance_id TEXT NOT NULL UNIQUE,
                execution_id TEXT NOT NULL UNIQUE,
                authorization_nonce TEXT NOT NULL UNIQUE,
                deployment_id TEXT NOT NULL,
                issued_at TEXT NOT NULL,
                valid_until TEXT NOT NULL,
                payload_digest TEXT NOT NULL
            )
            """
        )
        self._connection.commit()

    def authorize(
        self,
        *,
        acceptance: dict[str, Any],
        acceptance_verify: dict[str, Any],
        receipt: dict[str, Any],
        authenticate: Callable[[dict[str, Any]], bool],
        now: datetime | None = None,
    ) -> dict[str, Any]:
        if (
            not isinstance(acceptance, dict)
            or acceptance.get("kind") != "spine_runtime_transition_acceptance"
            or acceptance.get("acceptance_authenticated") is not True
            or acceptance.get("activation_accepted") is not True
            or acceptance.get("production_activation_authorized") is not False
            or acceptance.get("runtime_activated") is not False
        ):
            raise SpineRuntimeProductionActivationAuthorizationError(
                "verified transition acceptance is required"
            )
        acceptance_digest = acceptance.get("digest")
        acceptance_id = acceptance.get("acceptance_id")
        execution_id = acceptance.get("execution_id")
        deployment_id = acceptance.get("deployment_id")
        for field, value in (
            ("acceptance digest", acceptance_digest),
            ("acceptance identity", acceptance_id),
            ("execution identity", execution_id),
        ):
            if not isinstance(value, str) or len(value) != 64:
                raise SpineRuntimeProductionActivationAuthorizationError(
                    f"{field} is invalid"
                )
        if not isinstance(deployment_id, str) or not deployment_id:
            raise SpineRuntimeProductionActivationAuthorizationError(
                "deployment identity is missing"
            )
        if (
            not isinstance(acceptance_verify, dict)
            or acceptance_verify.get("kind") != "spine_runtime_transition_acceptance_verify"
            or acceptance_verify.get("verified") is not True
            or acceptance_verify.get("acceptance_id") != acceptance_id
            or acceptance_verify.get("acceptance_digest") != acceptance_digest
            or acceptance_verify.get("execution_id") != execution_id
            or acceptance_verify.get("production_activation_authorized") is not False
            or acceptance_verify.get("runtime_activated") is not False
        ):
            raise SpineRuntimeProductionActivationAuthorizationError(
                "independent acceptance verification is required"
            )

        if not callable(authenticate):
            raise SpineRuntimeProductionActivationAuthorizationError(
                "activation authorization authenticator must be callable"
            )
        if (
            not isinstance(receipt, dict)
            or receipt.get("kind") != "spine_runtime_production_activation_receipt"
        ):
            raise SpineRuntimeProductionActivationAuthorizationError(
                "production activation receipt is missing"
            )
        if receipt.get("authority_domain") != "runtime-production-activation":
            raise SpineRuntimeProductionActivationAuthorizationError(
                "production activation authority domain changed"
            )
        if receipt.get("decision") != "authorize-production-activation":
            raise SpineRuntimeProductionActivationAuthorizationError(
                "production activation decision is invalid"
            )
        if receipt.get("acceptance_digest") != acceptance_digest:
            raise SpineRuntimeProductionActivationAuthorizationError(
                "activation acceptance scope mismatch"
            )
        if receipt.get("acceptance_id") != acceptance_id:
            raise SpineRuntimeProductionActivationAuthorizationError(
                "activation acceptance identity mismatch"
            )
        if receipt.get("execution_id") != execution_id:
            raise SpineRuntimeProductionActivationAuthorizationError(
                "activation execution scope mismatch"
            )
        if receipt.get("deployment_id") != deployment_id:
            raise SpineRuntimeProductionActivationAuthorizationError(
                "activation deployment scope mismatch"
            )
        if receipt.get("target_driver") != "pymongo-async":
            raise SpineRuntimeProductionActivationAuthorizationError(
                "activation target driver changed"
            )
        nonce = receipt.get("authorization_nonce")
        attestation = receipt.get("attestation_digest")
        if not isinstance(nonce, str) or len(nonce) != 64:
            raise SpineRuntimeProductionActivationAuthorizationError(
                "authorization nonce is invalid"
            )
        if not isinstance(attestation, str) or len(attestation) != 64:
            raise SpineRuntimeProductionActivationAuthorizationError(
                "authorization attestation digest is invalid"
            )

        instant = now or datetime.now(timezone.utc)
        if instant.tzinfo is None or instant.utcoffset() is None:
            raise SpineRuntimeProductionActivationAuthorizationError(
                "now must be timezone-aware"
            )
        instant = instant.astimezone(timezone.utc)
        issued_at = _instant(receipt.get("issued_at"), "issued_at")
        expires_at = _instant(receipt.get("expires_at"), "expires_at")
        if issued_at > instant:
            raise SpineRuntimeProductionActivationAuthorizationError(
                "activation receipt is not yet valid"
            )
        if expires_at <= instant or expires_at <= issued_at:
            raise SpineRuntimeProductionActivationAuthorizationError(
                "activation receipt is expired or invalid"
            )
        if (expires_at - issued_at).total_seconds() > 120:
            raise SpineRuntimeProductionActivationAuthorizationError(
                "activation receipt lifetime exceeds two minutes"
            )
        try:
            authenticated = authenticate(dict(receipt))
        except Exception as exc:
            raise SpineRuntimeProductionActivationAuthorizationError(
                "activation authorization authentication failed closed"
            ) from exc
        if authenticated is not True:
            raise SpineRuntimeProductionActivationAuthorizationError(
                "activation receipt was not externally authenticated"
            )

        authorization_id = hashlib.sha256(
            (
                f"{acceptance_digest}|{acceptance_id}|{execution_id}|"
                f"{deployment_id}|{nonce}|pymongo-async"
            ).encode("utf-8")
        ).hexdigest()
        evidence = {
            "authorization_id": authorization_id,
            "acceptance_digest": acceptance_digest,
            "acceptance_id": acceptance_id,
            "execution_id": execution_id,
            "deployment_id": deployment_id,
            "authorization_nonce": nonce,
            "target_driver": "pymongo-async",
            "authorized_at": instant.isoformat(),
            "valid_until": expires_at.isoformat(),
            "authorization_authenticated": True,
            "activation_accepted": True,
            "production_activation_authorized": True,
            "rollback_available": True,
            "runtime_activated": False,
        }
        payload_digest = _digest(evidence)
        try:
            self._connection.execute(
                """
                INSERT INTO spine_runtime_production_activation_authorization(
                    authorization_id,acceptance_digest,acceptance_id,execution_id,
                    authorization_nonce,deployment_id,issued_at,valid_until,
                    payload_digest
                ) VALUES (?,?,?,?,?,?,?,?,?)
                """,
                (
                    authorization_id,
                    acceptance_digest,
                    acceptance_id,
                    execution_id,
                    nonce,
                    deployment_id,
                    instant.isoformat(),
                    expires_at.isoformat(),
                    payload_digest,
                ),
            )
            self._connection.commit()
        except sqlite3.IntegrityError as exc:
            raise SpineRuntimeProductionActivationAuthorizationError(
                "production activation authorization replay or nonce reuse"
            ) from exc

        return {
            "kind": "spine_runtime_production_activation_authorization",
            "hit": True,
            "law": "external-authorization-does-not-itself-activate-runtime",
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
            """
            SELECT COUNT(*) AS n
            FROM spine_runtime_production_activation_authorization
            """
        ).fetchone()
        return int(row["n"])

    def close(self) -> None:
        self._connection.close()
