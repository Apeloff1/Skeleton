"""Typed errors for the OmniFabric hex surface.

Mirrors gameforge-rs fabric + gf-core outbox failure modes: outbox full
backpressures (never drops), chain breaks raise evidence, appends that
cannot journal never exist.
"""
from __future__ import annotations


class OmniFabricError(Exception):
    """Base error for the Ω-fabric hex surface."""


class OutboxFull(OmniFabricError):
    """Durability is backpressured, not dropped. Caller sees this."""


class OutboxJournalError(OmniFabricError):
    """Journal step failed; the event must be rolled back."""


class ChainBroken(OmniFabricError):
    """Hash chain verification failed. Carries seq + detail evidence."""

    def __init__(self, seq: int, detail: str) -> None:
        self.seq = int(seq)
        self.detail = str(detail)
        super().__init__(f"seq {self.seq}: {self.detail}")


class LedgerUnknown(OmniFabricError):
    """Requested ledger is not registered in the fabric catalog."""


class ProjectionStale(OmniFabricError):
    """Projection head lags the fabric head; rebuild required."""


class SegmentCorrupt(OmniFabricError):
    """A sealed fabric segment failed integrity checks."""


class ReplayConflict(OmniFabricError):
    """Outbox replay produced a conflicting seq or hash."""


class CapacityError(OmniFabricError):
    """A bounded structure refused growth (window, catalog, index)."""


class QueryBoundsError(OmniFabricError):
    """Query arguments are out of allowed bounds."""
