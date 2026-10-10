"""End-to-end resource-admitted Dragon recrawl lifecycle (no network I/O)."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from skeleton.ai.game_builder.reviewed_knowledge import (
    ReviewedDocument, ReviewedKnowledgeStore, ReviewedNote,
)
from skeleton.ai.game_builder.dragon_wisdom_pyramid import DragonWisdomPyramid
from skeleton.ai.game_builder.dragon_recrawl_dispatch import DragonRecrawlDispatcher
from skeleton.ai.webcrawler.dragon_resource_session import (
    DragonResourceSession, HardwareSample,
)
from skeleton.kernel.global_resource_scheduler import (
    GlobalResourceScheduler, GlobalResourcePolicy, PlanePolicy, ResourceVector,
)

OWNER = "studio-a"
NOW = int(datetime(2026, 10, 20, 12, tzinfo=timezone.utc).timestamp())
TEXT = "Original jumping observations for independent study."


def original(when: str = "2026-10-01T12:00:00Z"):
    return ReviewedDocument(
        OWNER, "source-a", "https://example.org/research", "Jump study",
        TEXT, when, "design-research-license", ("design_reference",),
        "independent-reviewer", True,
        (ReviewedNote("note-a", "platforming",
                      "Jumping stays consistent on this original test.",
                      0, len("Original jumping"), "supports", 900000,
                      "publisher-a", ("jump",)),),
    )


def sample(at=NOW, *, thermal=False, pressure=.1, battery=.8, charging=True):
    return HardwareSample(
        256 * 1024**2, 4, pressure, battery, charging, thermal, float(at),
    )


def global_ledger():
    return GlobalResourceScheduler(GlobalResourcePolicy(
        ResourceVector(cpu_millis=2000, memory_mb=128, io_tokens=100),
        (PlanePolicy("interactive", 2, ResourceVector(), 1.0),
         PlanePolicy("background", 1, ResourceVector(), 1.0)),
    ))


class RecrawlWorkerLifecycleTests(TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.lib = ReviewedKnowledgeStore(Path(self.temp.name)/"knowledge.db")
        self.first = self.lib.import_document(
            original(), expected_parent_digest=None, authorized=True,
        )
        self.wiki = DragonWisdomPyramid(self.lib)
        self.queued = self.wiki.enqueue_canonical_refreshes(
            OWNER, now=NOW, authorized=True, trusted_worker=True,
        )["queued"][0]

    def tearDown(self):
        self.lib.close()
        self.temp.cleanup()

    def run_dispatch(self, *, global_sched=None, tenant=OWNER):
        session = DragonResourceSession(global_resources=global_sched, tenant=tenant)
        return DragonRecrawlDispatcher(self.wiki, session), session

    def start(self, dispatcher, **kwargs):
        arguments = dict(owner=OWNER, sample=sample(), now=NOW, consent=True,
                         trusted_worker=True, authorized=True)
        arguments.update(kwargs)
        return dispatcher.begin(**arguments)

    def test_local_advisory_capacity_is_not_execution_authority(self):
        dispatcher, session = self.run_dispatch()
        self.assertIsNone(self.start(dispatcher))
        self.assertEqual(dispatcher.active, {})
        self.assertEqual(dispatcher.stopped_tickets, {})
        self.assertEqual(len(self.wiki.recrawl_queue(OWNER, now=NOW, authorized=True)), 1)

    def test_global_ticket_consumes_capacity_until_real_worker_stop(self):
        global_sched = global_ledger()
        dispatcher, session = self.run_dispatch(global_sched=global_sched)
        ticket = self.start(dispatcher)
        self.assertIsNotNone(ticket)
        self.assertTrue(ticket.execution_authorized)
        self.assertEqual(ticket.order_digest, self.queued["order_digest"])
        self.assertEqual(global_sched.usage("background").io_tokens, 1)
        self.assertTrue(dispatcher.authorize_chunk(
            ticket, sample(), now=NOW, authorized=True,
            trusted_worker=True, consent=True,
        ))
        with self.assertRaises(PermissionError):
            dispatcher.stopped(ticket, authorized=True,
                               trusted_worker=True, worker_stopped=False)
        self.assertEqual(global_sched.usage("background").io_tokens, 1)
        dispatcher.stopped(ticket, authorized=True,
                           trusted_worker=True, worker_stopped=True)
        self.assertEqual(global_sched.usage("background").io_tokens, 0)
        self.assertEqual(len(self.wiki.recrawl_queue(OWNER, now=NOW, authorized=True)), 1)
        updated = self.lib.import_document(
            original("2026-10-20T12:00:00Z"),
            expected_parent_digest=self.first.revision_digest,
            authorized=True,
        )
        receipt = dispatcher.complete(
            ticket, new_revision=updated.revision_digest, now=NOW+1,
            authorized=True, trusted_worker=True,
        )
        self.assertEqual(receipt["new_revision"], updated.revision_digest)
        self.assertEqual(self.wiki.recrawl_queue(OWNER, now=NOW+1, authorized=True), ())

    def test_thermal_pressure_battery_and_stale_telemetry_are_hard_stops(self):
        dispatcher, session = self.run_dispatch(global_sched=global_ledger())
        for bad in (sample(thermal=True), sample(pressure=.98),
                    sample(battery=.1, charging=False), sample(at=NOW-30)):
            self.assertIsNone(self.start(dispatcher, sample=bad))
        ticket = self.start(dispatcher)
        self.assertIsNotNone(ticket)
        for bad in (sample(thermal=True), sample(pressure=.98),
                    sample(battery=.1, charging=False), sample(at=NOW-30)):
            self.assertFalse(dispatcher.authorize_chunk(
                ticket, bad, now=NOW, authorized=True,
                trusted_worker=True, consent=True,
            ))
        self.assertFalse(dispatcher.authorize_chunk(
            ticket, sample(at=NOW+60), now=NOW+60,
            authorized=True, trusted_worker=True, consent=True,
        ))
        dispatcher.stopped(ticket, authorized=True, trusted_worker=True,
                           worker_stopped=True)
        dispatcher.abandon(ticket, authorized=True, trusted_worker=True)
        self.assertEqual(len(self.wiki.recrawl_queue(OWNER, now=NOW+61, authorized=True)), 1)

    def test_scope_consent_forged_or_stopped_ticket_fail_closed(self):
        dispatcher, session = self.run_dispatch(global_sched=global_ledger())
        with self.assertRaises(PermissionError):
            self.start(dispatcher, consent=False)
        with self.assertRaises(PermissionError):
            self.start(dispatcher, trusted_worker=False)
        with self.assertRaises(PermissionError):
            self.start(dispatcher, authorized=False)
        ticket = self.start(dispatcher)
        self.assertIsNotNone(ticket)
        wrong = type(ticket)(
            ticket.owner, ticket.source_id, ticket.source_revision,
            "f"*64, ticket.task_id, ticket.granted_at, ticket.expires_at,
        )
        self.assertFalse(dispatcher.authorize_chunk(
            wrong, sample(), now=NOW, authorized=True,
            trusted_worker=True, consent=True,
        ))
        with self.assertRaises(ValueError):
            dispatcher.complete(ticket, new_revision="a"*64, now=NOW,
                                authorized=True, trusted_worker=True)
        with self.assertRaises(PermissionError):
            dispatcher.authorize_chunk(ticket, sample(), now=NOW,
                                       authorized=True, trusted_worker=True, consent=False)
        dispatcher.stopped(ticket, authorized=True, trusted_worker=True,
                           worker_stopped=True)
        self.assertFalse(dispatcher.authorize_chunk(
            ticket, sample(), now=NOW, authorized=True,
            trusted_worker=True, consent=True,
        ))

    def test_separate_tenant_and_missing_io_capacity_block_dispatch(self):
        owner_session, _ = self.run_dispatch(global_sched=global_ledger(), tenant="another-owner")
        with self.assertRaises(PermissionError):
            self.start(owner_session)
        no_io = GlobalResourceScheduler(GlobalResourcePolicy(
            ResourceVector(cpu_millis=2000, memory_mb=128),
            (PlanePolicy("interactive", 2, ResourceVector(), 1),
             PlanePolicy("background", 1, ResourceVector(), 1)),
        ))
        dispatcher, _ = self.run_dispatch(global_sched=no_io)
        self.assertIsNone(self.start(dispatcher))
        self.assertTrue(no_io.usage("background").empty)

    def test_new_almanac_revision_invalidates_inflight_chunk(self):
        dispatcher, _ = self.run_dispatch(global_sched=global_ledger())
        ticket = self.start(dispatcher)
        self.assertIsNotNone(ticket)
        self.lib.import_document(
            original("2026-10-20T11:59:00Z"),
            expected_parent_digest=self.first.revision_digest,
            authorized=True,
        )
        self.assertFalse(dispatcher.authorize_chunk(
            ticket, sample(), now=NOW, authorized=True,
            trusted_worker=True, consent=True,
        ))
        dispatcher.stopped(ticket, authorized=True, trusted_worker=True,
                           worker_stopped=True)
        dispatcher.abandon(ticket, authorized=True, trusted_worker=True)


if __name__ == "__main__":
    import unittest
    unittest.main()
