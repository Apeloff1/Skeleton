"""Epoch watch around a reaccept.

Records the epoch before and after. Raises if the fence moved.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from skeleton.persistence.inbox_ledger import InboxDelivery
from skeleton.persistence.spine_reaccept import SpineReaccept


class SpineWatchError(RuntimeError):
    """Watch rejected its inputs. Not a maturity signal."""


class SpineWatch:
    """Read epochs around one reaccept."""

    def __init__(self, reaccept: SpineReaccept) -> None:
        if not isinstance(reaccept, SpineReaccept):
            raise SpineWatchError("reaccept must be a SpineReaccept")
        self.reaccept = reaccept

    def watch(
        self,
        delivery: InboxDelivery,
        *,
        tenant_id: str,
        expected_digest: str,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        card = self.reaccept.reaccept(
            delivery,
            tenant_id=tenant_id,
            expected_digest=expected_digest,
            now=now,
        )
        if card["epoch_before"] != card["epoch_after"]:
            raise SpineWatchError("reaccept moved the fence")
        card["kind"] = "spine_watch"
        card["moved"] = False
        return card
