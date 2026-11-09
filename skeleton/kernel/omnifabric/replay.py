"""Outbox replay and crash-recovery for OmniFabric.

A crash between journal and hot-tail admit leaves intent in the outbox.
On boot, ``replay_unconfirmed`` can rebuild candidate events from journal
documents and optionally re-admit them into a fresh OmniFabric.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any, Callable

from skeleton.kernel.omnifabric.core import OmniFabric
from skeleton.kernel.omnifabric.errors import ReplayConflict
from skeleton.kernel.omnifabric.events import FabricEvent, event_from_mapping
from skeleton.kernel.omnifabric.outbox import FabricOutbox
from skeleton.kernel.omnifabric.verify import verify_events


@dataclass
class ReplayResult:
    attempted: int = 0
    admitted: int = 0
    skipped: int = 0
    conflicts: list[str] = field(default_factory=list)
    confirmed: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "attempted": self.attempted,
            "admitted": self.admitted,
            "skipped": self.skipped,
            "conflicts": list(self.conflicts),
            "confirmed": self.confirmed,
        }


class FabricReplayer:
    """Reconcile outbox + optionally rebuild fabric from journaled docs."""

    def __init__(self, outbox: FabricOutbox) -> None:
        self._outbox = outbox
        self._lock = threading.RLock()

    def confirm_pending(self) -> int:
        return self._outbox.reconcile()

    def load_unconfirmed_events(self) -> list[FabricEvent]:
        docs = self._outbox.unconfirmed_documents()
        events = [event_from_mapping(d) for d in docs]
        events.sort(key=lambda e: e.seq)
        return events

    def replay_into(
        self,
        fabric: OmniFabric,
        *,
        strict: bool = True,
        confirm: bool = True,
    ) -> ReplayResult:
        """Admit unconfirmed journal events into ``fabric`` if missing.

        When ``strict``, a seq/hash conflict raises ``ReplayConflict``.
        Journaled events already present (same seq+hash) are skipped.
        """
        result = ReplayResult()
        events = self.load_unconfirmed_events()
        result.attempted = len(events)
        report = verify_events(events)
        if strict and events and not report.ok:
            raise ReplayConflict(f"unconfirmed journal chain broken: {report.issues[0].detail}")

        with self._lock:
            for ev in events:
                existing = fabric.get_by_seq(ev.seq)
                if existing is not None:
                    if existing.hash != ev.hash:
                        msg = f"seq {ev.seq}: journal hash {ev.hash} != fabric {existing.hash}"
                        result.conflicts.append(msg)
                        if strict:
                            raise ReplayConflict(msg)
                    result.skipped += 1
                    continue
                # re-append would assign a NEW seq — for recovery we inject via
                # a private path: journal already holds the event, so we only
                # need hot-tail admit without re-journal. Use internal helper.
                self._admit_recovered(fabric, ev)
                result.admitted += 1

        if confirm:
            result.confirmed = self.confirm_pending()
        return result

    @staticmethod
    def _admit_recovered(fabric: OmniFabric, ev: FabricEvent) -> None:
        """Hot-tail admit for an already-journaled recovered event."""
        # Access internals deliberately — recovery is a privileged path.
        with fabric._lock:  # noqa: SLF001
            if fabric._seq and ev.seq <= fabric._seq and fabric.get_by_seq(ev.seq):
                return
            if ev.seq != fabric._seq + 1 and fabric._seq != 0:
                # allow empty fabric to take first recovered seq as-is
                if fabric._seq != 0:
                    raise ReplayConflict(
                        f"cannot admit seq {ev.seq}; fabric at {fabric._seq}"
                    )
            if fabric._seq == 0:
                if ev.prev_hash != "genesis" and ev.seq != 1:
                    # starting mid-chain after drain is ok for recovery windows
                    pass
            elif ev.prev_hash != fabric._head:
                raise ReplayConflict(
                    f"prev_hash {ev.prev_hash} != fabric head {fabric._head}"
                )
            fabric._seq = max(fabric._seq, ev.seq)
            fabric._head = ev.hash
            if len(fabric._tail) >= fabric._hot_cap:
                drain = max(1, fabric._hot_cap // 4)
                del fabric._tail[:drain]
                fabric._drains += 1
            fabric._tail.append(ev)
            fabric._appends += 1


def boot_reconcile(fabric: OmniFabric) -> dict[str, Any]:
    """Standard boot hook: confirm outbox, return stats (no lifespan wiring)."""
    replayer = FabricReplayer(fabric.outbox)
    confirmed = replayer.confirm_pending()
    return {"confirmed": confirmed, "fabric": fabric.stats()}
