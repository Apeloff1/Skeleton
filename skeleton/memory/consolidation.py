"""
Skeleton Memory — Consolidation cycle

Closes the retention loop:

    Jeeves turns feed KREM → concepts decay → due() flags stale ones
    → ConsolidationCycle schedules reviews in the RepetitionScheduler
    → refresh re-observes concepts (strengthening KREM)
    → DreamEngine consolidates refreshed episodes into RAG themes

One `cycle()` call runs the whole pass; `auto_cycle` runs it as a
maintenance tick suitable for a background thread or cron.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from skeleton.kernel.events import DomainEvent, EventBus


def _unit_retention(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("retention must be in [0, 1]")
    number = float(value)
    if number != number or number in (float("inf"), float("-inf")) or not 0.0 <= number <= 1.0:
        raise ValueError("retention must be in [0, 1]")
    return number


class ConsolidationCycle:
    """Wire KREM due-refresh into spaced repetition and dream synthesis."""

    def __init__(
        self,
        krem: Any,
        scheduler: Any,
        dream: Optional[Any] = None,
        retriever: Optional[Any] = None,
        bus: Optional[EventBus] = None,
    ):
        self._krem = krem
        self._scheduler = scheduler
        self._dream = dream
        self._retriever = retriever
        self._bus = bus
        self._stats = {"cycles": 0, "scheduled": 0, "refreshed": 0, "themes": 0}

    def cycle(self, max_concepts: int = 10) -> Dict[str, Any]:
        """Run one consolidation pass."""
        if isinstance(max_concepts, bool) or not isinstance(max_concepts, int) or max_concepts < 0:
            raise ValueError("max_concepts must be a non-negative integer")
        self._stats["cycles"] += 1
        due = self._krem.due()[:max_concepts]

        # 1. Schedule stale concepts for spaced review
        for concept in due:
            self._scheduler.schedule(f"krem:{concept}", interval_hours=self._interval_for(concept))
            self._stats["scheduled"] += 1

        # 2. Refresh anything whose review slot has arrived
        refreshed: List[str] = []
        for item in self._scheduler.due_items():
            if not item.startswith("krem:"):
                continue
            concept = item[len("krem:"):]
            _unit_retention(self._krem.retention(concept))
            self._krem.observe(concept)  # review strengthens the cell
            after = _unit_retention(self._krem.retention(concept))
            self._scheduler.review(item, performance=after)
            refreshed.append(concept)
            self._stats["refreshed"] += 1

        # 3. Dream consolidation: fold refreshed concepts into themes
        themes: List[Dict[str, Any]] = []
        if self._dream is not None:
            themes = self._dream.dream(min_cluster=2)
            self._stats["themes"] += len(themes)

        report = {
            "cycle": self._stats["cycles"],
            "due": due,
            "scheduled": len(due),
            "refreshed": refreshed,
            "themes": [t.get("tag") for t in themes],
            "remaining_due": len(self._krem.due()),
        }

        if self._bus:
            self._bus.publish(DomainEvent(
                topic="memory.consolidation.cycle",
                payload=report,
                correlation_id=f"consolidation_{self._stats['cycles']}",
            ))

        return report

    def auto_cycle(self, interval_seconds: float = 3600.0, max_ticks: Optional[int] = None) -> None:
        """Maintenance loop: run cycles on an interval. Blocking.

        Pass max_ticks for bounded runs (tests, cron); None runs until
        interrupted.
        """
        ticks = 0
        while True:
            self.cycle()
            ticks += 1
            if max_ticks is not None and ticks >= max_ticks:
                return
            time.sleep(interval_seconds)

    def _interval_for(self, concept: str) -> float:
        """Lower retention → shorter review interval (refresh sooner)."""
        retention = self._krem.retention(concept)
        return max(1.0, 24.0 * retention)

    def stats(self) -> Dict[str, Any]:
        return dict(self._stats)


def wire_from_genesis(genesis: Any, jeeves: Any, bus: Optional[EventBus] = None) -> ConsolidationCycle:
    """Build a ConsolidationCycle from genesis handles + a Jeeves instance."""
    return ConsolidationCycle(
        krem=jeeves.krem,
        scheduler=genesis.get("repetition"),
        dream=genesis.handles.get("dream"),
        retriever=genesis.handles.get("quad"),
        bus=bus or genesis.bus,
    )
