"""Externally authenticated post-transition acceptance for the P2 runtime spine."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any, Callable


class SpineRuntimeTransitionAcceptanceError(RuntimeError):
    """Post-transition acceptance failed closed."""


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
        raise SpineRuntimeTransitionAcceptanceError(
            f"{field} must be ISO-8601 text"
        )
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise SpineRuntimeTransitionAcceptanceError(
            f"{field} is not valid ISO-8601"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise SpineRuntimeTransitionAcceptanceError(
            f"{field} must be timezone-aware"
        )
    return parsed.astimezone(timezone.utc)


class SpineRuntimeTransitionAcceptanceLedger:
    """Persist one external acceptance receipt per verified live health proof."""

    def __init__(self, path: str | Path = ":memory:") -> None:
        self._connection = sqlite3.connect(str(path), check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS spine_runtime_transition_acceptance (
                acceptance_id TEXT PRIMARY KEY,
                health_digest TEXT NOT NULL UNIQUE,
                execution_id TEXT NOT NULL UNIQUE,
                acceptance_nonce TEXT NOT NULL UNIQUE,
                deployment_id TEXT NOT NULL,
                issued_at TEXT NOT NULL,
                valid_until TEXT NOT NULL,
                payload_digest TEXT NOT NULL
            )
            """
        )
        self._connection.commit()

    def accept(
        self,
        *,
        health: dict[str, Any],
        health_verify: dict[str, Any],
        receipt: dict[str, Any],
        authenticate: Callable[[dict[str, Any]], bool],
        now: datetime | None = None,
    ) -> dict[str, Any]:
        if (
            not isinstance(health, dict)
            or health.get("kind") != "spine_runtime_transition_health"
            or health.get("health_qualified") is not True
            or health.get("operation_continuity") is not True
            or health.get("dispatcher_running") is not True
            or health.get("fence_stable") is not True
            or health.get("runtime_activated") is not False
        ):
            raise SpineRuntimeTransitionAcceptanceError(
                "verified live transition health is required"
            )
        health_digest = health.get("digest")
        execution_id = health.get("execution_id")
        deployment_id = health.get("deployment_id")
        for field, value in (
            ("health digest", health_digest),
            ("execution identity", execution_id),
        ):
            if not isinstance(value, str) or len(value) != 64:
                raise SpineRuntimeTransitionAcceptanceError(
                    f"{field} is invalid"
                )
        if not isinstance(deployment_id, str) or not deployment_id:
            raise SpineRuntimeTransitionAcceptanceError(
                "deployment identity is missing"
            )
        if (
            not isinstance(health_verify, dict)
            or health_verify.get("kind") != "spine_runtime_transition_health_verify"
            or health_verify.get("verified") is not True
            or health_verify.get("health_digest") != health_digest
            or health_verify.get("execution_id") != execution_id
            or health_verify.get("operation_continuity") is not True
            or health_verify.get("runtime_activated") is not False
        ):
            raise SpineRuntimeTransitionAcceptanceError(
                "independent live health verification is required"
            )

        if not callable(authenticate):
            raise SpineRuntimeTransitionAcceptanceError(
                "acceptance authenticator must be callable"
            )
        if (
            not isinstance(receipt, dict)
            or receipt.get("kind") != "spine_runtime_transition_acceptance_receipt"
        ):
            raise SpineRuntimeTransitionAcceptanceError(
                "transition acceptance receipt is missing"
            )
        if receipt.get("authority_domain") != "runtime-transition-acceptance":
            raise SpineRuntimeTransitionAcceptanceError(
                "acceptance authority domain changed"
            )
        if receipt.get("decision") != "accept-transition-health":
            raise SpineRuntimeTransitionAcceptanceError(
                "acceptance decision is invalid"
            )
        if receipt.get("health_digest") != health_digest:
            raise SpineRuntimeTransitionAcceptanceError(
                "acceptance health scope mismatch"
            )
        if receipt.get("execution_id") != execution_id:
            raise SpineRuntimeTransitionAcceptanceError(
                "acceptance execution scope mismatch"
            )
        if receipt.get("deployment_id") != deployment_id:
            raise SpineRuntimeTransitionAcceptanceError(
                "acceptance deployment scope mismatch"
            )
        if receipt.get("target_driver") != "pymongo-async":
            raise SpineRuntimeTransitionAcceptanceError(
                "acceptance target driver changed"
            )
        nonce = receipt.get("acceptance_nonce")
        attestation = receipt.get("attestation_digest")
        if not isinstance(nonce, str) or len(nonce) != 64:
            raise SpineRuntimeTransitionAcceptanceError(
                "acceptance nonce is invalid"
            )
        if not isinstance(attestation, str) or len(attestation) != 64:
            raise SpineRuntimeTransitionAcceptanceError(
                "acceptance attestation digest is invalid"
            )

        instant = now or datetime.now(timezone.utc)
        if instant.tzinfo is None or instant.utcoffset() is None:
            raise SpineRuntimeTransitionAcceptanceError(
                "now must be timezone-aware"
            )
        instant = instant.astimezone(timezone.utc)
        issued_at = _instant(receipt.get("issued_at"), "issued_at")
        expires_at = _instant(receipt.get("expires_at"), "expires_at")
        if issued_at > instant:
            raise SpineRuntimeTransitionAcceptanceError(
                "acceptance receipt is not yet valid"
            )
        if expires_at <= instant or expires_at <= issued_at:
            raise SpineRuntimeTransitionAcceptanceError(
                "acceptance receipt is expired or invalid"
            )
        if (expires_at - issued_at).total_seconds() > 180:
            raise SpineRuntimeTransitionAcceptanceError(
                "acceptance receipt lifetime exceeds three minutes"
            )
        try:
            authenticated = authenticate(dict(receipt))
        except Exception as exc:
            raise SpineRuntimeTransitionAcceptanceError(
                "acceptance authentication failed closed"
            ) from exc
        if authenticated is not True:
            raise SpineRuntimeTransitionAcceptanceError(
                "acceptance receipt was not externally authenticated"
            )

        acceptance_id = hashlib.sha256(
            (
                f"{health_digest}|{execution_id}|{deployment_id}|"
                f"{nonce}|pymongo-async"
            ).encode("utf-8")
        ).hexdigest()
        evidence = {
            "acceptance_id": acceptance_id,
            "health_digest": health_digest,
            "execution_id": execution_id,
            "deployment_id": deployment_id,
            "acceptance_nonce": nonce,
            "target_driver": "pymongo-async",
            "accepted_at": instant.isoformat(),
            "valid_until": expires_at.isoformat(),
            "acceptance_authenticated": True,
            "health_qualified": True,
            "operation_continuity": True,
            "activation_accepted": True,
            "production_activation_authorized": False,
            "rollback_available": True,
            "runtime_activated": False,
        }
        payload_digest = _digest(evidence)
        try:
            self._connection.execute(
                """
                INSERT INTO spine_runtime_transition_acceptance(
                    acceptance_id,health_digest,execution_id,acceptance_nonce,
                    deployment_id,issued_at,valid_until,payload_digest
                ) VALUES (?,?,?,?,?,?,?,?)
                """,
                (
                    acceptance_id,
                    health_digest,
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
            raise SpineRuntimeTransitionAcceptanceError(
                "transition acceptance replay or nonce reuse"
            ) from exc

        return {
            "kind": "spine_runtime_transition_acceptance",
            "hit": True,
            "law": "external-health-acceptance-does-not-self-authorize-activation",
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
            "SELECT COUNT(*) AS n FROM spine_runtime_transition_acceptance"
        ).fetchone()
        return int(row["n"])

    def close(self) -> None:
        self._connection.close()
