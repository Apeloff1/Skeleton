"""Independent durable verification for one refused bind seal.

The verifier reconstructs the refusal digest from the durable journal and the
candidate refusal card. It never accepts a delivery, advances a fence, applies
poison recovery, starts a dispatcher, or grants merge authority.
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


class SpineBindHoldVerifyError(RuntimeError):
    """Bind-hold verification failed closed."""


_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")


class SpineBindHoldVerify:
    """Reconcile one refusal card to one reconstructable durable row."""

    def __init__(self, journal_path: str | Path) -> None:
        self._connection = sqlite3.connect(
            str(journal_path),
            check_same_thread=False,
        )
        self._connection.row_factory = sqlite3.Row

    def verify(self, card: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(card, dict) or card.get("kind") != "spine_bind_hold":
            raise SpineBindHoldVerifyError("bind hold card kind mismatch")
        if (
            card.get("law") != "held-id-refuses-bind"
            or card.get("citation") != "VOL-134"
        ):
            raise SpineBindHoldVerifyError("bind hold authority identity changed")
        if card.get("held") is not True or card.get("sealed") is not False:
            raise SpineBindHoldVerifyError("bind hold refusal is not held")
        if (
            card.get("moved") is not False
            or card.get("applied") != 0
            or card.get("apply_landed") is not False
        ):
            raise SpineBindHoldVerifyError("bind hold refusal is not dark")
        if card.get("stored_prose") != 0:
            raise SpineBindHoldVerifyError("bind hold stored prose changed")
        for field in (
            "completion_checkbox",
            "implementation_signature",
            "verification_signature",
        ):
            if card.get(field) is not False:
                raise SpineBindHoldVerifyError(
                    f"bind hold overclaimed authority: {field}"
                )

        tenant_id = card.get("tenant_id")
        outbox_id = card.get("outbox_id")
        hold_reason = card.get("reason")
        bind_digest = card.get("bind_digest")
        hold_id = card.get("hold_id")
        epoch_before = card.get("epoch_before")
        epoch_after = card.get("epoch_after")
        if not isinstance(tenant_id, str) or not tenant_id.strip():
            raise SpineBindHoldVerifyError("tenant_id is invalid")
        if not isinstance(outbox_id, str) or not outbox_id.strip():
            raise SpineBindHoldVerifyError("outbox_id is invalid")
        if not isinstance(hold_reason, str) or not hold_reason.strip():
            raise SpineBindHoldVerifyError("hold reason is invalid")
        if (
            not isinstance(bind_digest, str)
            or _DIGEST_RE.fullmatch(bind_digest) is None
        ):
            raise SpineBindHoldVerifyError("bind digest is invalid")
        if (
            isinstance(hold_id, bool)
            or not isinstance(hold_id, int)
            or hold_id < 1
        ):
            raise SpineBindHoldVerifyError("hold_id is invalid")
        if (
            isinstance(epoch_before, bool)
            or not isinstance(epoch_before, int)
            or epoch_before < 0
            or epoch_before != epoch_after
        ):
            raise SpineBindHoldVerifyError("bind hold epoch evidence moved")

        try:
            row = self._connection.execute(
                """
                SELECT refusal_id, hold_id, hold_reason, bind_digest, digest,
                       identity_digest, held, applied, epoch
                FROM spine_bind_hold
                WHERE tenant_id = ?
                  AND outbox_id = ?
                  AND hold_id = ?
                  AND bind_digest = ?
                  AND epoch = ?
                """,
                (
                    tenant_id,
                    outbox_id,
                    hold_id,
                    bind_digest,
                    epoch_before,
                ),
            ).fetchone()
        except sqlite3.OperationalError as exc:
            raise SpineBindHoldVerifyError(
                "bind hold journal is missing"
            ) from exc
        if row is None:
            raise SpineBindHoldVerifyError(
                "bind hold durable refusal is missing"
            )

        refusal_id = int(row["refusal_id"])
        if refusal_id < 1:
            raise SpineBindHoldVerifyError(
                "bind hold durable refusal id is invalid"
            )
        durable = {
            "hold_id": int(row["hold_id"]),
            "hold_reason": str(row["hold_reason"]),
            "bind_digest": str(row["bind_digest"]),
            "held": int(row["held"]),
            "applied": int(row["applied"]),
            "epoch": int(row["epoch"]),
        }
        expected = {
            "hold_id": hold_id,
            "hold_reason": hold_reason,
            "bind_digest": bind_digest,
            "held": 1,
            "applied": 0,
            "epoch": epoch_before,
        }
        if durable != expected:
            raise SpineBindHoldVerifyError(
                "bind hold durable refusal identity mismatch"
            )

        refusal_digest = _bind_hold_refusal_digest(
            tenant_id=tenant_id,
            outbox_id=outbox_id,
            hold_id=hold_id,
            hold_reason=hold_reason,
            bind_digest=bind_digest,
            epoch=epoch_before,
        )
        if row["digest"] != refusal_digest:
            raise SpineBindHoldVerifyError(
                "bind hold durable refusal digest mismatch"
            )
        identity_digest = str(row["identity_digest"])
        expected_identity = _bind_hold_identity_digest(
            refusal_id=refusal_id,
            refusal_digest=refusal_digest,
        )
        if identity_digest != expected_identity:
            raise SpineBindHoldVerifyError(
                "bind hold durable refusal identity digest mismatch"
            )

        return {
            "kind": "spine_bind_hold_verify",
            "hit": True,
            "law": (
                "bind-hold-verification-does-not-grant-apply-authority"
            ),
            "citation": "VOL-134",
            "tenant_id": tenant_id,
            "outbox_id": outbox_id,
            "refusal_id": refusal_id,
            "hold_id": hold_id,
            "hold_reason": hold_reason,
            "bind_digest": bind_digest,
            "refusal_digest": refusal_digest,
            "identity_digest": identity_digest,
            "epoch": epoch_before,
            "verified": True,
            "held": True,
            "sealed": False,
            "moved": False,
            "applied": 0,
            "apply_authority": False,
            "merge_authority": False,
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }

    def close(self) -> None:
        self._connection.close()
