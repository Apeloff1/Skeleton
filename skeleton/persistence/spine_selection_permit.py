"""Durable single-use selection permit ledger for P2 cutover.

An effective, independently verified authorization may issue exactly one
selection permit. The permit authorizes a later driver-selection action but
does not select the driver, start a dispatcher, advance a fence, or activate
runtime.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any


class SpineSelectionPermitError(RuntimeError):
    """Selection permit issuance or persisted state failed closed."""


def _digest(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class SpineSelectionPermitLedger:
    """Persist replay-resistant authorization to attempt runtime selection later."""

    def __init__(self, path: str | Path = ":memory:") -> None:
        self._connection = sqlite3.connect(str(path), check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS spine_selection_permit (
                permit_id TEXT PRIMARY KEY,
                effectiveness_digest TEXT NOT NULL UNIQUE,
                authorization_digest TEXT NOT NULL,
                one_time_nonce TEXT NOT NULL UNIQUE,
                target_driver TEXT NOT NULL,
                issued_at TEXT NOT NULL,
                payload_digest TEXT NOT NULL,
                consumed INTEGER NOT NULL DEFAULT 0 CHECK(consumed IN (0, 1))
            )
            """
        )
        self._connection.commit()

    def issue(
        self,
        *,
        effectiveness: dict[str, Any],
        effectiveness_verify: dict[str, Any],
        target_driver: str = "pymongo-async",
        now: datetime | None = None,
    ) -> dict[str, Any]:
        if (
            not isinstance(effectiveness, dict)
            or effectiveness.get("kind") != "spine_cutover_effectiveness"
            or effectiveness.get("authorization_effective") is not True
            or effectiveness.get("external_change_control_authenticated") is not True
        ):
            raise SpineSelectionPermitError("effective external authorization is required")
        if effectiveness.get("selection_authorized") is not False:
            raise SpineSelectionPermitError("selection was already authorized")
        if effectiveness.get("runtime_driver_selected") is not False:
            raise SpineSelectionPermitError("runtime driver was already selected")
        if effectiveness.get("runtime_activated") is not False:
            raise SpineSelectionPermitError("runtime was already activated")

        effectiveness_digest = effectiveness.get("digest")
        authorization_digest = effectiveness.get("authorization_digest")
        if not isinstance(effectiveness_digest, str) or len(effectiveness_digest) != 64:
            raise SpineSelectionPermitError("effectiveness digest is invalid")
        if not isinstance(authorization_digest, str) or len(authorization_digest) != 64:
            raise SpineSelectionPermitError("authorization digest is invalid")

        if (
            not isinstance(effectiveness_verify, dict)
            or effectiveness_verify.get("kind") != "spine_cutover_effectiveness_verify"
            or effectiveness_verify.get("verified") is not True
            or effectiveness_verify.get("effectiveness_digest") != effectiveness_digest
            or effectiveness_verify.get("authorization_digest") != authorization_digest
            or effectiveness_verify.get("authorization_effective") is not True
        ):
            raise SpineSelectionPermitError("independent effectiveness verification is required")
        if effectiveness_verify.get("selection_authorized") is not False:
            raise SpineSelectionPermitError("effectiveness verifier already authorized selection")

        receipt = effectiveness.get("effectiveness_receipt")
        if not isinstance(receipt, dict):
            raise SpineSelectionPermitError("effectiveness receipt is missing")
        nonce = receipt.get("one_time_nonce")
        if not isinstance(nonce, str) or len(nonce) != 64:
            raise SpineSelectionPermitError("one-time nonce is invalid")
        if effectiveness_verify.get("one_time_nonce") != nonce:
            raise SpineSelectionPermitError("one-time nonce verification mismatch")

        expires_raw = receipt.get("expires_at")
        if not isinstance(expires_raw, str):
            raise SpineSelectionPermitError("effectiveness expiry is missing")
        try:
            expires_at = datetime.fromisoformat(expires_raw)
        except ValueError as exc:
            raise SpineSelectionPermitError("effectiveness expiry is invalid") from exc
        if expires_at.tzinfo is None or expires_at.utcoffset() is None:
            raise SpineSelectionPermitError("effectiveness expiry must be timezone-aware")
        expires_at = expires_at.astimezone(timezone.utc)

        if target_driver != "pymongo-async":
            raise SpineSelectionPermitError("selection target driver is unsupported")
        instant = now or datetime.now(timezone.utc)
        if instant.tzinfo is None or instant.utcoffset() is None:
            raise SpineSelectionPermitError("now must be timezone-aware")
        instant = instant.astimezone(timezone.utc)
        if instant >= expires_at:
            raise SpineSelectionPermitError("effectiveness window expired before permit issuance")

        evidence = {
            "effectiveness_digest": effectiveness_digest,
            "authorization_digest": authorization_digest,
            "one_time_nonce": nonce,
            "target_driver": target_driver,
            "issued_at": instant.isoformat(),
            "permit_valid_until": expires_at.isoformat(),
            "selection_authorized": True,
            "permit_consumed": False,
            "runtime_driver_selected": False,
            "runtime_activated": False,
        }
        payload_digest = _digest(evidence)
        permit_id = hashlib.sha256(
            f"{effectiveness_digest}|{nonce}|{target_driver}".encode("utf-8")
        ).hexdigest()

        try:
            self._connection.execute(
                """
                INSERT INTO spine_selection_permit(
                    permit_id, effectiveness_digest, authorization_digest,
                    one_time_nonce, target_driver, issued_at, payload_digest, consumed
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 0)
                """,
                (
                    permit_id,
                    effectiveness_digest,
                    authorization_digest,
                    nonce,
                    target_driver,
                    instant.isoformat(),
                    payload_digest,
                ),
            )
            self._connection.commit()
        except sqlite3.IntegrityError as exc:
            raise SpineSelectionPermitError("selection permit replay or nonce reuse") from exc

        return {
            "kind": "spine_selection_permit",
            "hit": False,
            "law": "effective-authorization-issues-one-non-activating-selection-permit",
            "citation": "VOL-134",
            "permit_id": permit_id,
            **evidence,
            "digest": payload_digest,
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }

    def count(self) -> int:
        row = self._connection.execute(
            "SELECT COUNT(*) AS n FROM spine_selection_permit"
        ).fetchone()
        return int(row["n"])

    def close(self) -> None:
        self._connection.close()
