"""Read and independently digest-check one refused bind seal.

A foreign tenant/outbox is empty. Durable identity, hold, digest, epoch, or
applied-state tampering fails closed. The reader never accepts a delivery.
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Any

from skeleton.persistence.spine_bind_hold_journal import (
    _bind_hold_identity_digest,
    _bind_hold_refusal_digest,
)


class SpineBindHoldReadError(RuntimeError):
    """Bind hold read rejected its inputs. Not a maturity signal."""


_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")


class SpineBindHoldRead:
    """Read one durable refusal and reconstruct its evidence digest."""

    def __init__(self, journal_path: str | Path) -> None:
        self._connection = sqlite3.connect(
            str(journal_path),
            check_same_thread=False,
        )
        self._connection.row_factory = sqlite3.Row

    def card(self, tenant_id: str, outbox_id: str) -> dict[str, Any]:
        if not isinstance(tenant_id, str) or not tenant_id.strip():
            raise SpineBindHoldReadError("tenant_id must be non-empty text")
        if not isinstance(outbox_id, str) or not outbox_id.strip():
            raise SpineBindHoldReadError("outbox_id must be non-empty text")
        try:
            row = self._connection.execute(
                """
                SELECT refusal_id, hold_id, hold_reason, bind_digest, digest,
                       identity_digest, held, applied, epoch
                FROM spine_bind_hold
                WHERE tenant_id = ? AND outbox_id = ?
                ORDER BY refusal_id DESC
                LIMIT 1
                """,
                (tenant_id, outbox_id),
            ).fetchone()
        except sqlite3.OperationalError as exc:
            raise SpineBindHoldReadError("bind hold journal missing") from exc

        if row is None:
            return {
                "kind": "spine_bind_hold_read",
                "hit": False,
                "law": "bind-hold-stays-unapplied",
                "citation": "VOL-134",
                "tenant_id": tenant_id,
                "outbox_id": outbox_id,
                "seen": False,
                "refusal_id": None,
                "hold_id": None,
                "hold_reason": None,
                "bind_digest": None,
                "digest": None,
                "identity_digest": None,
                "epoch": None,
                "applied": 0,
                "sealed": False,
                "stored_prose": 0,
                "completion_checkbox": False,
                "implementation_signature": False,
                "verification_signature": False,
            }

        refusal_id = int(row["refusal_id"])
        hold_id = int(row["hold_id"])
        hold_reason = str(row["hold_reason"])
        bind_digest = str(row["bind_digest"])
        digest = str(row["digest"])
        identity_digest = str(row["identity_digest"])
        held = int(row["held"])
        applied = int(row["applied"])
        epoch = int(row["epoch"])
        if refusal_id < 1:
            raise SpineBindHoldReadError("refusal row id is invalid")
        if hold_id < 1:
            raise SpineBindHoldReadError(
                "refusal row is missing bound hold identity"
            )
        if not hold_reason.strip():
            raise SpineBindHoldReadError("refusal row hold reason is invalid")
        if _DIGEST_RE.fullmatch(bind_digest) is None:
            raise SpineBindHoldReadError("refusal row bind digest is invalid")
        if _DIGEST_RE.fullmatch(digest) is None:
            raise SpineBindHoldReadError("refusal row digest is invalid")
        if _DIGEST_RE.fullmatch(identity_digest) is None:
            raise SpineBindHoldReadError(
                "refusal row identity digest is invalid"
            )
        if held != 1 or applied != 0 or epoch < 0:
            raise SpineBindHoldReadError("refusal row is not dark")

        expected = _bind_hold_refusal_digest(
            tenant_id=tenant_id,
            outbox_id=outbox_id,
            hold_id=hold_id,
            hold_reason=hold_reason,
            bind_digest=bind_digest,
            epoch=epoch,
        )
        if digest != expected:
            raise SpineBindHoldReadError(
                "refusal row digest does not match durable evidence"
            )
        expected_identity = _bind_hold_identity_digest(
            refusal_id=refusal_id,
            refusal_digest=digest,
        )
        if identity_digest != expected_identity:
            raise SpineBindHoldReadError(
                "refusal row identity digest does not match durable evidence"
            )

        return {
            "kind": "spine_bind_hold_read",
            "hit": False,
            "law": "bind-hold-stays-unapplied",
            "citation": "VOL-134",
            "tenant_id": tenant_id,
            "outbox_id": outbox_id,
            "seen": True,
            "refusal_id": refusal_id,
            "hold_id": hold_id,
            "hold_reason": hold_reason,
            "bind_digest": bind_digest,
            "digest": digest,
            "identity_digest": identity_digest,
            "epoch": epoch,
            "applied": 0,
            "sealed": False,
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }

    def close(self) -> None:
        self._connection.close()
