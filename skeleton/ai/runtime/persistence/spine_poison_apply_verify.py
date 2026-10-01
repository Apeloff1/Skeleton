"""Independent durable verification for one P2 poison apply.

The verifier is read-only. It reconciles a successful poison-apply card against
the durable apply journal and the one-time ticket row. It never accepts a
delivery, consumes a ticket, advances a fence, or grants general apply authority.
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Any

from skeleton.persistence.spine_poison_ticket import SpinePoisonTicket


class SpinePoisonApplyVerifyError(RuntimeError):
    """Durable poison-apply verification failed closed."""


_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")


class SpinePoisonApplyVerify:
    """Cross-check poison-apply card, journal row, and consumed ticket."""

    def __init__(self, journal_path: str | Path, ticket: SpinePoisonTicket) -> None:
        if not isinstance(ticket, SpinePoisonTicket):
            raise SpinePoisonApplyVerifyError("ticket must be a SpinePoisonTicket")
        self.ticket = ticket
        self._connection = sqlite3.connect(str(journal_path), check_same_thread=False)
        self._connection.row_factory = sqlite3.Row

    def verify(self, card: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(card, dict) or card.get("kind") != "spine_poison_apply":
            raise SpinePoisonApplyVerifyError("poison apply card kind mismatch")
        tenant_id = card.get("tenant_id")
        outbox_id = card.get("outbox_id")
        ticket_id = card.get("ticket_id")
        for field, value in (("tenant_id", tenant_id), ("outbox_id", outbox_id), ("ticket_id", ticket_id)):
            if not isinstance(value, str) or not value.strip():
                raise SpinePoisonApplyVerifyError(f"{field} must be non-empty text")
        delivery_digest = card.get("delivery_digest")
        if not isinstance(delivery_digest, str) or _DIGEST_RE.fullmatch(delivery_digest) is None:
            raise SpinePoisonApplyVerifyError("delivery_digest must be lowercase SHA-256 hex")
        reason = card.get("reason")
        if reason not in {"accepted", "duplicate"}:
            raise SpinePoisonApplyVerifyError("poison apply card is not a successful apply")
        if card.get("applied") != 1 or card.get("hit") is not True:
            raise SpinePoisonApplyVerifyError("poison apply success invariant is missing")
        duplicate = card.get("duplicate")
        if not isinstance(duplicate, bool):
            raise SpinePoisonApplyVerifyError("poison apply duplicate invariant is invalid")
        if (reason == "duplicate") is not duplicate:
            raise SpinePoisonApplyVerifyError("poison apply reason and duplicate state disagree")
        before = card.get("epoch_before")
        after = card.get("epoch_after")
        if (
            isinstance(before, bool) or not isinstance(before, int) or before < 0
            or isinstance(after, bool) or not isinstance(after, int) or after < 0
        ):
            raise SpinePoisonApplyVerifyError("poison apply epoch evidence is invalid")
        if before != after:
            raise SpinePoisonApplyVerifyError("poison apply moved the fence")
        if card.get("applied_fence") is not False:
            raise SpinePoisonApplyVerifyError("poison apply overclaimed fence application")
        if card.get("law") != "hold-digest-stable-epoch-unchanged":
            raise SpinePoisonApplyVerifyError("poison apply law changed")
        if card.get("citation") != "VOL-134":
            raise SpinePoisonApplyVerifyError("poison apply citation changed")
        if card.get("stored_prose") != 0:
            raise SpinePoisonApplyVerifyError("poison apply stored prose changed")
        for field in (
            "completion_checkbox",
            "implementation_signature",
            "verification_signature",
        ):
            if card.get(field) is not False:
                raise SpinePoisonApplyVerifyError(
                    f"poison apply overclaimed authority: {field}"
                )

        rows = self._connection.execute(
            """
            SELECT tenant_id, outbox_id, digest, reason, epoch_before,
                   epoch_after, applied, ticket_id
            FROM spine_poison_apply
            WHERE ticket_id = ? AND applied = 1
            ORDER BY apply_id
            """,
            (ticket_id,),
        ).fetchall()
        if len(rows) != 1:
            raise SpinePoisonApplyVerifyError(
                "poison apply journal must contain exactly one applied row"
            )
        row = rows[0]
        expected = {
            "tenant_id": tenant_id,
            "outbox_id": outbox_id,
            "digest": delivery_digest,
            "reason": reason,
            "epoch_before": before,
            "epoch_after": after,
            "applied": 1,
            "ticket_id": ticket_id,
        }
        actual = {name: row[name] for name in expected}
        if actual != expected:
            raise SpinePoisonApplyVerifyError("poison apply journal evidence mismatch")

        ticket = self.ticket.read(ticket_id)
        if ticket is None:
            raise SpinePoisonApplyVerifyError("poison apply ticket is missing")
        if (
            ticket["tenant_id"] != tenant_id
            or ticket["outbox_id"] != outbox_id
            or ticket["digest"] != delivery_digest
        ):
            raise SpinePoisonApplyVerifyError("poison apply ticket scope mismatch")
        if ticket["consumed"] != 1:
            raise SpinePoisonApplyVerifyError(
                "poison apply ticket is not consumed exactly once"
            )

        return {
            "kind": "spine_poison_apply_verify",
            "hit": True,
            "law": "poison-apply-verification-does-not-grant-apply-authority",
            "citation": "VOL-134",
            "tenant_id": tenant_id,
            "outbox_id": outbox_id,
            "delivery_digest": delivery_digest,
            "ticket_id": ticket_id,
            "reason": reason,
            "epoch_before": before,
            "epoch_after": after,
            "journal_rows": 1,
            "ticket_consumed": True,
            "verified": True,
            "applied_fence": False,
            "apply_authority": False,
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }

    def close(self) -> None:
        self._connection.close()
