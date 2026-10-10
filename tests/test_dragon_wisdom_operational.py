"""Operational Dragon: signed memory, anchored recovery, and admitted live crawler."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from skeleton.ai.game_builder.reviewed_knowledge import ReviewedDocument, ReviewedNote, ReviewedKnowledgeStore
from skeleton.ai.game_builder.dragon_wisdom_pyramid import DragonWisdomPyramid
from skeleton.ai.game_builder.dragon_wisdom_authority import DragonWisdomAuthority
from skeleton.ai.game_builder.dragon_wisdom_memory import DragonWisdomMemory
from skeleton.ai.game_builder.dragon_wisdom_custody import DragonCustodyAnchor
from skeleton.ai.game_builder.dragon_recrawl_dispatch import DragonRecrawlDispatcher
from skeleton.ai.game_builder.dragon_recrawl_executor import run_admitted_recrawl
from skeleton.ai.webcrawler.dragon_resource_session import DragonResourceSession, HardwareSample
from skeleton.ai.webcrawler.http import SafeHttpFetcher
from skeleton.ai.webcrawler.core import FetchResponse
from skeleton.kernel.global_resource_scheduler import (
    GlobalResourcePolicy, GlobalResourceScheduler, PlanePolicy, ResourceVector,
)

OWNER = "studio-a"
NOW = int(datetime(2026, 10, 20, 15, tzinfo=timezone.utc).timestamp())
TEXT = "Jump buffering and hit feedback require measurements."


def source(name):
    return ReviewedDocument(
        owner=OWNER, source_id="source-"+name,
        source_url="https://example.org/"+name,
        title="Game mechanics study", text=TEXT,
        observed_at="2026-10-10T12:00:00Z",
        license_id="design_reference_license", allowed_scopes=("design_reference",),
        reviewer_id="source_author_"+name, approved=True,
        notes=(ReviewedNote(
            note_id="note-"+name, mechanic="platforming",
            statement="Measured jump buffering merits new tests.",
            start=0, end=len("Jump buffering"), stance="supports",
            confidence_ppm=910000, dependence_group="publisher_"+name,
            tags=("jump", "buffer"),
        ),),
    )


def sample():
    return HardwareSample(256*1024**2, 4, .1, .9, True, False, float(NOW))


class DragonOperationalTests(TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        root = Path(self.temp.name)
        self.path = root/"knowledge.sqlite"
        self.anchor_dir = root/"sealed-heads"
        self.anchor_dir.mkdir()
        self.lib = ReviewedKnowledgeStore(self.path)
        self.pyramid = DragonWisdomPyramid(self.lib)
        self.first = self.lib.import_document(
            source("a"), expected_parent_digest=None, authorized=True,
        )
        self.other = self.lib.import_document(
            source("b"), expected_parent_digest=None, authorized=True,
        )
        self.auth = DragonWisdomAuthority(
            self.pyramid, wiki_signing_key=b"r"*32,
            approval_signing_key=b"m"*32, issuer="trusted-identity",
        )
        self.anchor = DragonCustodyAnchor(
            self.anchor_dir, signing_key=b"c"*32,
        )

    def tearDown(self):
        self.lib.close()
        self.temp.cleanup()

    def sign(self):
        brief = self.lib.build_brief(
            OWNER, "jump", authorized=True, min_independent_groups=2,
        )
        wiki_grant = self.auth.issue_grant(
            OWNER, "wiki-human", "independent_lab", "wiki_reviewer",
            brief.to_payload()["brief_digest"], now=NOW,
            expires_at=NOW+300, identity_verified=True, authorized=True,
        )
        decision = self.auth.review(
            OWNER, brief, mechanic="platforming", disposition="accepted",
            review_evidence_digest="a"*64, grant=wiki_grant,
            now=NOW, expires_at=NOW+3600, authorized=True,
            trusted_worker=True,
        )
        approver = self.auth.issue_grant(
            OWNER, "approver-human", "governance_board", "memory_approver",
            decision["digest"], now=NOW, expires_at=NOW+300,
            identity_verified=True, authorized=True,
        )
        self.auth.approve(
            OWNER, decision["digest"], grant=approver, now=NOW+1,
            authorized=True, trusted_worker=True,
        )
        return decision

    def test_signed_memory_survives_restart_and_revokes_without_training(self):
        signed = self.sign()
        memory = DragonWisdomMemory(self.pyramid)
        first = memory.reconcile(
            OWNER, now=NOW+2, authorized=True, trusted_worker=True,
        )
        self.assertEqual(first["eligible"], 1)
        self.assertEqual(first["changes"], 1)
        self.assertEqual(memory.reconcile(
            OWNER, now=NOW+3, authorized=True, trusted_worker=True,
        )["changes"], 0)
        results = memory.retrieve(
            OWNER, "platforming", now=NOW+3,
            authorized=True, trusted_worker=True,
        )
        self.assertEqual(len(results), 1)
        self.assertFalse(results[0]["training_authorized"])
        self.assertFalse(results[0]["memorized_source_text"])
        self.lib.close()
        self.lib = ReviewedKnowledgeStore(self.path)
        self.pyramid = DragonWisdomPyramid(self.lib)
        memory = DragonWisdomMemory(self.pyramid)
        self.assertEqual(len(memory.retrieve(
            OWNER, "platforming", now=NOW+4, authorized=True,
            trusted_worker=True,
        )), 1)
        self.pyramid.revoke(
            OWNER, signed["digest"], reason="rights_change",
            now=NOW+5, authorized=True, trusted_worker=True,
        )
        self.assertEqual(memory.retrieve(
            OWNER, "platforming", now=NOW+6,
            authorized=True, trusted_worker=True,
        ), ())
        self.assertEqual(memory._rows(OWNER), {})
        actions = [e["action"] for e in memory._events(OWNER)]
        self.assertEqual(actions, ["admit", "withdraw"])

    def test_legacy_unsigned_approval_is_excluded_from_durable_memory(self):
        brief = self.lib.build_brief(
            OWNER, "jump", authorized=True, min_independent_groups=2,
        )
        old = self.pyramid.wiki_review(
            OWNER, brief, mechanic="platforming",
            disposition="accepted", independent_reviewer_id="old-identity",
            review_evidence_digest="a"*64, now=NOW,
            expires_at=NOW+3600, authorized=True, trusted_worker=True,
        )
        self.pyramid.promote(
            OWNER, old["digest"], now=NOW+1, authorized=True,
            trusted_worker=True, human_approved=True,
        )
        memory = DragonWisdomMemory(self.pyramid)
        self.assertEqual(memory.reconcile(
            OWNER, now=NOW+2, authorized=True, trusted_worker=True,
        )["eligible"], 0)

    def test_signed_anchor_detects_snapshot_rollback_and_tampering(self):
        self.sign()
        with self.assertRaisesRegex(ValueError, "no independent"):
            self.anchor.verify(self.pyramid, OWNER, authorized=True)
        with self.assertRaises(PermissionError):
            self.anchor.checkpoint(
                self.pyramid, OWNER, now=NOW+2, authorized=True,
                trusted_worker=True,
            )
        sealed = self.anchor.checkpoint(
            self.pyramid, OWNER, now=NOW+2, authorized=True,
            trusted_worker=True, allow_initial_bootstrap=True,
        )
        self.assertEqual(
            self.anchor.verify(self.pyramid, OWNER, authorized=True)["head_digest"],
            sealed["body"]["head_digest"],
        )
        self.assertEqual(self.anchor.checkpoint(
            self.pyramid, OWNER, now=NOW+3, authorized=True,
            trusted_worker=True,
        ), sealed)
        self.pyramid.recrawl(
            OWNER, "source-a", reason="scheduled_refresh",
            expected_revision=self.first.revision_digest,
            now=NOW+4, authorized=True, trusted_worker=True,
        )
        with self.assertRaisesRegex(ValueError, "not externally anchored"):
            self.anchor.verify(self.pyramid, OWNER, authorized=True)
        self.anchor.checkpoint(
            self.pyramid, OWNER, now=NOW+5,
            authorized=True, trusted_worker=True,
        )
        self.assertTrue(self.anchor.verify(
            self.pyramid, OWNER, authorized=True,
        )["current"])
        self.lib.db.execute("""DELETE FROM dragon_wisdom_pyramid
            WHERE owner=? AND sequence=2""", (OWNER,))
        with self.assertRaisesRegex(ValueError, "rollback|journal"):
            self.anchor.verify(self.pyramid, OWNER, authorized=True)

    def test_anchor_file_mutation_fails_even_if_sqlite_unchanged(self):
        self.sign()
        self.anchor.checkpoint(self.pyramid, OWNER, now=NOW+2,
                               authorized=True, trusted_worker=True,
                               allow_initial_bootstrap=True)
        target = next(self.anchor._path(OWNER).iterdir())
        content = target.read_text()
        target.write_text(content.replace("trusted", "untrusted") if "trusted" in content
                          else content.replace("signature", "signatvre"))
        with self.assertRaises(ValueError):
            self.anchor.verify(self.pyramid, OWNER, authorized=True)

    def dispatch(self, *args):
        scheduler = GlobalResourceScheduler(GlobalResourcePolicy(
            ResourceVector(cpu_millis=2000, memory_mb=128, io_tokens=100),
            (PlanePolicy("interactive",2,ResourceVector(),1.0),
             PlanePolicy("background",1,ResourceVector(),1.0)),
        ))
        worker = DragonRecrawlDispatcher(
            self.pyramid, DragonResourceSession(
                global_resources=scheduler, tenant=OWNER,
            ),
        )
        return worker, scheduler

    def pending(self):
        return self.pyramid.recrawl(
            OWNER, "source-a", reason="scheduled_refresh",
            expected_revision=self.first.revision_digest,
            now=NOW, authorized=True, trusted_worker=True,
        )

    def mock_fetcher(self, requests):
        fetcher = SafeHttpFetcher(allowed_hosts=frozenset({"example.org"}))
        def once(url, *, user_agent, max_bytes, extra_headers=None):
            requests.append(url)
            if url.endswith("/robots.txt"):
                return FetchResponse(url,200,{"content-type":"text/plain"},
                    b"User-agent: *\nAllow: /\n",NOW)
            return FetchResponse(url,200,{"content-type":"text/plain"},
                b"Documented original controller timing and jump responsiveness.",NOW)
        fetcher.fetch_once = once
        return fetcher

    def test_live_recrawl_returns_unapproved_custodied_document_only(self):
        self.pending()
        worker, scheduler = self.dispatch()
        requests = []
        result = run_admitted_recrawl(
            worker, owner=OWNER, sample_provider=sample,
            consent_provider=lambda: True, fetcher=self.mock_fetcher(requests),
            now=NOW, authorized=True, trusted_worker=True,
            consent=True, clock=lambda: NOW, sleep=lambda _: None,
        )
        self.assertIsNotNone(result)
        self.assertEqual(result.parent_revision, self.first.revision_digest)
        self.assertTrue(result.source_review_required)
        self.assertFalse(result.memory_promotion_authorized)
        self.assertEqual(len(requests), 2)
        self.assertTrue(requests[0].endswith("robots.txt"))
        self.assertEqual(requests[1], "https://example.org/a")
        self.assertTrue(scheduler.usage("background").empty)
        self.assertEqual(len(self.pyramid.recrawl_queue(
            OWNER, now=NOW, authorized=True,
        )), 1)

    def test_live_consent_revocation_after_robots_blocks_page_fetch(self):
        self.pending()
        worker, scheduler = self.dispatch()
        requests = []
        result = run_admitted_recrawl(
            worker, owner=OWNER, sample_provider=sample,
            consent_provider=lambda: len(requests)==0,
            fetcher=self.mock_fetcher(requests),
            now=NOW, authorized=True, trusted_worker=True,
            consent=True, clock=lambda: NOW, sleep=lambda _: None,
        )
        self.assertIsNone(result)
        self.assertEqual(len(requests), 1)
        self.assertTrue(scheduler.usage("background").empty)

    def test_live_transport_without_dns_socket_binding_is_forbidden(self):
        self.pending()
        worker, scheduler = self.dispatch()
        with self.assertRaises(PermissionError):
            run_admitted_recrawl(
                worker, owner=OWNER, sample_provider=sample,
                consent_provider=lambda: True,
                fetcher=SafeHttpFetcher(bind_dns_to_socket=False),
                now=NOW, authorized=True, trusted_worker=True,
                consent=True,
            )
        self.assertTrue(scheduler.usage("background").empty)


if __name__ == "__main__":
    import unittest
    unittest.main()
