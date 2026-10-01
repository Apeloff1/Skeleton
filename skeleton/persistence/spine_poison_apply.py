"""Poison apply on a held outbox id.

The hold row is the only input. A changed digest is a conflict and is refused
before accept. A matching digest is reaccepted. The fence epoch is not
advanced. SpineApplyGate still refuses every intent; this seam does not
replace it and does not sign work off.
"""

from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from skeleton.persistence.inbox_ledger import InboxDelivery
from skeleton.persistence.spine_hold import (
    _active_spine_hold,
    _ensure_spine_hold_schema,
    _release_spine_hold,
)
from skeleton.persistence.spine_reaccept import SpineReaccept
from skeleton.persistence.spine_poison_ticket import SpinePoisonTicket


_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")


class SpinePoisonApplyError(RuntimeError):
    """Poison apply rejected its inputs. Not a maturity signal."""


class SpinePoisonApply:
    """Apply one held id when the ticket digest matches. Epoch stays put."""

    def __init__(
        self,
        hold_path: str | Path,
        reaccept: SpineReaccept,
        ticket: SpinePoisonTicket,
        journal_path: str | Path,
    ) -> None:
        if not isinstance(reaccept, SpineReaccept):
            raise SpinePoisonApplyError("reaccept must be a SpineReaccept")
        if not isinstance(ticket, SpinePoisonTicket):
            raise SpinePoisonApplyError("ticket must be a SpinePoisonTicket")
        self.reaccept = reaccept
        self.ticket = ticket
        self._hold = sqlite3.connect(str(hold_path), check_same_thread=False)
        self._hold.row_factory = sqlite3.Row
        _ensure_spine_hold_schema(self._hold)
        self._journal = sqlite3.connect(str(journal_path), check_same_thread=False)
        self._journal.row_factory = sqlite3.Row
        self._journal.execute(
            """
            CREATE TABLE IF NOT EXISTS spine_poison_apply (
                apply_id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id TEXT NOT NULL,
                outbox_id TEXT NOT NULL,
                hold_id INTEGER NOT NULL DEFAULT 0,
                digest TEXT NOT NULL,
                reason TEXT NOT NULL,
                epoch_before INTEGER NOT NULL,
                epoch_after INTEGER NOT NULL,
                applied INTEGER NOT NULL,
                ticket_id TEXT NOT NULL,
                applied_at TEXT NOT NULL
            )
            """
        )
        journal_columns = {
            str(row["name"])
            for row in self._journal.execute(
                "PRAGMA table_info(spine_poison_apply)"
            )
        }
        if "hold_id" not in journal_columns:
            self._journal.execute(
                """
                ALTER TABLE spine_poison_apply
                ADD COLUMN hold_id INTEGER NOT NULL DEFAULT 0
                """
            )
        self._journal.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS
                spine_poison_apply_one_success_per_ticket
            ON spine_poison_apply(ticket_id)
            WHERE applied = 1
            """
        )
        self._journal.commit()

    def apply(
        self,
        delivery: InboxDelivery,
        *,
        tenant_id: str,
        outbox_id: str,
        expected_digest: str,
        ticket_id: str,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        if not isinstance(delivery, InboxDelivery):
            raise SpinePoisonApplyError("delivery must be an InboxDelivery")
        if not all(isinstance(value, str) and value.strip() for value in (tenant_id, outbox_id, ticket_id)):
            raise SpinePoisonApplyError("tenant_id, outbox_id, and ticket_id must be non-empty text")
        if (
            not isinstance(expected_digest, str)
            or _DIGEST_RE.fullmatch(expected_digest) is None
        ):
            raise SpinePoisonApplyError(
                "expected_digest must be lowercase SHA-256 hex"
            )
        instant = now or datetime.now(timezone.utc)
        if instant.tzinfo is None or instant.utcoffset() is None:
            raise SpinePoisonApplyError("now must be timezone-aware")
        if delivery.tenant_id != tenant_id:
            return self._refuse(tenant_id, outbox_id, expected_digest, ticket_id, "tenant-drift", instant)
        if delivery.event_id != outbox_id:
            return self._refuse(tenant_id, outbox_id, expected_digest, ticket_id, "identity-mismatch", instant)
        hold = _active_spine_hold(
            self._hold,
            tenant_id=tenant_id,
            outbox_id=outbox_id,
        )
        if hold is None:
            return self._refuse(tenant_id, outbox_id, expected_digest, ticket_id, "unheld", instant)
        ticket = self.ticket.read(ticket_id)
        if (
            ticket is None
            or ticket["tenant_id"] != tenant_id
            or ticket["outbox_id"] != outbox_id
        ):
            return self._refuse(
                tenant_id,
                outbox_id,
                expected_digest,
                ticket_id,
                "ticket-mismatch",
                instant,
            )
        ticket_hold_id = ticket["hold_id"]
        if (
            isinstance(ticket_hold_id, bool)
            or not isinstance(ticket_hold_id, int)
            or ticket_hold_id < 1
        ):
            return self._refuse(
                tenant_id,
                outbox_id,
                expected_digest,
                ticket_id,
                "ticket-hold-missing",
                instant,
            )
        if int(hold["hold_id"]) != ticket_hold_id:
            return self._refuse(
                tenant_id,
                outbox_id,
                expected_digest,
                ticket_id,
                "hold-drift",
                instant,
                hold_id=ticket_hold_id,
            )
        if ticket["consumed"] != 0:
            return self._refuse(
                tenant_id,
                outbox_id,
                expected_digest,
                ticket_id,
                "ticket-consumed",
                instant,
            )
        if ticket["digest"] != expected_digest or delivery.digest() != expected_digest:
            return self._refuse(
                tenant_id,
                outbox_id,
                expected_digest,
                ticket_id,
                "digest-mismatch",
                instant,
            )
        if not self.ticket.consume(ticket_id, now=instant):
            return self._refuse(
                tenant_id,
                outbox_id,
                expected_digest,
                ticket_id,
                "ticket-consumed",
                instant,
            )
        try:
            card = self.reaccept.reaccept(
                delivery,
                tenant_id=tenant_id,
                expected_digest=expected_digest,
                now=instant,
            )
        except Exception as exc:
            self._refuse(
                tenant_id,
                outbox_id,
                expected_digest,
                ticket_id,
                "reaccept-error",
                instant,
            )
            raise SpinePoisonApplyError(
                "reaccept failed after one-time ticket claim"
            ) from exc
        if card["epoch_before"] != card["epoch_after"]:
            raise SpinePoisonApplyError("poison apply moved the fence")
        if card["reason"] not in {"accepted", "duplicate"}:
            return self._refuse(tenant_id, outbox_id, expected_digest, ticket_id, card["reason"], instant)
        self._journal.execute(
            """
            INSERT INTO spine_poison_apply(
                tenant_id, outbox_id, hold_id, digest, reason,
                epoch_before, epoch_after, applied, ticket_id, applied_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
            """,
            (
                tenant_id,
                outbox_id,
                ticket_hold_id,
                expected_digest,
                card["reason"],
                card["epoch_before"],
                card["epoch_after"],
                ticket_id,
                instant.isoformat(),
            ),
        )
        self._journal.commit()
        released_rows = _release_spine_hold(
            self._hold,
            hold_id=ticket_hold_id,
            tenant_id=tenant_id,
            outbox_id=outbox_id,
            ticket_id=ticket_id,
            released_at=instant.isoformat(),
        )
        if released_rows < 1:
            self._refuse(
                tenant_id,
                outbox_id,
                expected_digest,
                ticket_id,
                "hold-release-error",
                instant,
            )
            raise SpinePoisonApplyError(
                "poison apply could not release active hold"
            )
        return self._card(
            tenant_id,
            outbox_id,
            card["reason"],
            card["epoch_before"],
            card["epoch_after"],
            1,
            card["duplicate"],
            expected_digest,
            ticket_id,
            ticket_hold_id,
            True,
            released_rows,
        )

    def applied_count(self, tenant_id: str) -> int:
        row = self._journal.execute(
            "SELECT COUNT(*) AS n FROM spine_poison_apply WHERE tenant_id = ? AND applied = 1",
            (tenant_id,),
        ).fetchone()
        return int(row["n"])

    def _refuse(
        self,
        tenant_id: str,
        outbox_id: str,
        digest: str,
        ticket_id: str,
        reason: str,
        instant: datetime,
        *,
        hold_id: int = 0,
    ) -> dict[str, Any]:
        self._journal.execute(
            """
            INSERT INTO spine_poison_apply(
                tenant_id, outbox_id, hold_id, digest, reason,
                epoch_before, epoch_after, applied, ticket_id, applied_at
            ) VALUES (?, ?, ?, ?, ?, 0, 0, 0, ?, ?)
            """,
            (
                tenant_id,
                outbox_id,
                hold_id,
                digest,
                reason,
                ticket_id,
                instant.isoformat(),
            ),
        )
        self._journal.commit()
        return self._card(
            tenant_id,
            outbox_id,
            reason,
            0,
            0,
            0,
            False,
            digest,
            ticket_id,
            hold_id,
            False,
            0,
        )

    @staticmethod
    def _card(
        tenant_id: str,
        outbox_id: str,
        reason: str,
        before: int,
        after: int,
        applied: int,
        duplicate: bool,
        delivery_digest: str,
        ticket_id: str,
        hold_id: int,
        hold_released: bool,
        released_hold_rows: int,
    ) -> dict[str, Any]:
        return {
            "kind": "spine_poison_apply",
            "hit": applied == 1 and before == after,
            "law": "hold-digest-stable-epoch-unchanged",
            "citation": "VOL-134",
            "tenant_id": tenant_id,
            "outbox_id": outbox_id,
            "delivery_digest": delivery_digest,
            "ticket_id": ticket_id,
            "hold_id": hold_id,
            "hold_released": hold_released,
            "released_hold_rows": released_hold_rows,
            "reason": reason,
            "epoch_before": before,
            "epoch_after": after,
            "applied": applied,
            "duplicate": duplicate,
            "applied_fence": False,
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }

    def close(self) -> None:
        self._hold.close()
        self._journal.close()
