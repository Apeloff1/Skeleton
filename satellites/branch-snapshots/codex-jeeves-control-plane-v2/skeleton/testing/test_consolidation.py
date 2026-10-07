"""Tests for the consolidation cycle (KREM → scheduler → dream)."""

from __future__ import annotations

import time
import unittest


class TestConsolidationCycle(unittest.TestCase):
    def _build(self):
        from skeleton.jeeves.matrices import KnowledgeRetentionMatrix
        from skeleton.memory.core import RepetitionScheduler
        from skeleton.memory.consolidation import ConsolidationCycle

        krem = KnowledgeRetentionMatrix()
        scheduler = RepetitionScheduler()
        cycle = ConsolidationCycle(krem=krem, scheduler=scheduler)
        return krem, scheduler, cycle

    def test_due_concepts_get_scheduled(self):
        krem, scheduler, cycle = self._build()
        krem.observe("forge")
        # Force staleness
        krem._cells["forge"].last_seen = time.time() - (krem.HALF_LIFE_HOURS * 10 * 3600)

        report = cycle.cycle()
        self.assertIn("forge", report["due"])
        self.assertEqual(report["scheduled"], 1)
        self.assertIn("krem:forge", scheduler._schedule)

    def test_refresh_strengthens_retention(self):
        krem, scheduler, cycle = self._build()
        krem.observe("blueprint")
        cell = krem._cells["blueprint"]
        cell.last_seen = time.time() - (krem.HALF_LIFE_HOURS * 10 * 3600)
        stale = krem.retention("blueprint")

        # Cycle 1: schedules the due concept
        cycle.cycle()
        # Force the scheduled review to be due now
        scheduler._schedule["krem:blueprint"]["next_review"] = time.time() - 1
        # Cycle 2: refreshes it
        report = cycle.cycle()

        self.assertIn("blueprint", report["refreshed"])
        self.assertGreater(krem.retention("blueprint"), stale)

    def test_weaker_concepts_get_shorter_intervals(self):
        krem, scheduler, cycle = self._build()
        strong = cycle._interval_for.__self__._krem  # not needed; call directly below
        krem.observe("strong-concept")
        krem.observe("weak-concept")
        krem._cells["weak-concept"].last_seen = time.time() - (krem.HALF_LIFE_HOURS * 5 * 3600)

        strong_interval = cycle._interval_for("strong-concept")
        weak_interval = cycle._interval_for("weak-concept")
        self.assertLess(weak_interval, strong_interval)

    def test_cycle_reports_shape(self):
        krem, scheduler, cycle = self._build()
        report = cycle.cycle()
        for key in ("cycle", "due", "scheduled", "refreshed", "themes", "remaining_due"):
            self.assertIn(key, report)

    def test_events_published(self):
        from skeleton.kernel.events import EventBus
        from skeleton.jeeves.matrices import KnowledgeRetentionMatrix
        from skeleton.memory.core import RepetitionScheduler
        from skeleton.memory.consolidation import ConsolidationCycle

        bus = EventBus()
        received = []
        bus.subscribe("memory.consolidation.cycle", lambda e: received.append(e.payload))
        cycle = ConsolidationCycle(krem=KnowledgeRetentionMatrix(), scheduler=RepetitionScheduler(), bus=bus)
        cycle.cycle()
        self.assertEqual(len(received), 1)

    def test_auto_cycle_bounded(self):
        krem, scheduler, cycle = self._build()
        cycle.auto_cycle(interval_seconds=0, max_ticks=3)
        self.assertEqual(cycle.stats()["cycles"], 3)


class TestConsolidationWithGenesis(unittest.TestCase):
    def test_wire_from_genesis(self):
        from skeleton.genesis import Genesis
        from skeleton.jeeves import JeevesCore
        from skeleton.jeeves.providers import LocalEchoProvider
        from skeleton.memory.consolidation import wire_from_genesis

        genesis = Genesis(seed=42).boot()
        jeeves = JeevesCore(provider=LocalEchoProvider())
        cycle = wire_from_genesis(genesis, jeeves)

        session = jeeves.open_session("consolidate-user")
        jeeves.ask(session.session_id, "forge builds blueprints")
        report = cycle.cycle()
        self.assertIn("cycle", report)


if __name__ == "__main__":
    unittest.main(verbosity=2)
