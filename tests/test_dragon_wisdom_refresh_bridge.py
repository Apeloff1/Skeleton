"""Canonical Almanac gap plans -> durable Wiki queue: integration + hostile paths."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from skeleton.ai.game_builder.reviewed_knowledge import (
    ReviewedDocument, ReviewedKnowledgeStore, ReviewedNote,
)
from skeleton.ai.game_builder.dragon_wisdom_pyramid import DragonWisdomPyramid


OWNER = "studio-a"
NOW = int(datetime(2026, 10, 20, 12, tzinfo=timezone.utc).timestamp())
TEXT = "Predictable jump timing supports skillful platforming."
QUOTE = "Predictable jump timing"


def doc(source_id, group, *, observed_at="2026-10-10T12:00:00Z",
        stance="supports", statement="Jump timing should be predictable.") -> ReviewedDocument:
    return ReviewedDocument(
        owner=OWNER, source_id=source_id,
        source_url="https://example.org/" + source_id,
        title="Original platforming research",
        text=TEXT, observed_at=observed_at,
        license_id="approved-design-reference",
        allowed_scopes=("design_reference", "research"),
        reviewer_id="reviewer-" + source_id,
        approved=True,
        notes=(ReviewedNote(
            note_id="note-" + source_id,
            mechanic="platforming", statement=statement,
            start=0, end=len(QUOTE), stance=stance, confidence_ppm=900000,
            dependence_group=group, tags=("timing",),
        ),),
    )


class DragonWisdomRefreshTests(TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.path = Path(self.temp.name) / "wisdom.db"
        self.library = ReviewedKnowledgeStore(self.path)
        self.wiki = DragonWisdomPyramid(self.library)
        self.parents = {}
        for suffix in ("a", "b"):
            receipt = self.library.import_document(
                doc("source-" + suffix, "publisher-" + suffix),
                expected_parent_digest=None, authorized=True,
            )
            self.parents[suffix] = receipt.revision_digest

    def tearDown(self):
        self.library.close()
        self.temp.cleanup()

    def enqueue(self, **changes):
        params = dict(owner=OWNER, now=NOW, authorized=True,
                      trusted_worker=True)
        params.update(changes)
        return self.wiki.enqueue_canonical_refreshes(**params)

    def test_two_real_stale_sources_queue_in_one_atomic_chain(self):
        plan = self.library.plan_recrawl(OWNER, as_of="2026-10-20T12:00:00Z", authorized=True)
        self.assertEqual(plan["total_requests"], 2)
        queued = self.enqueue()
        self.assertEqual(queued["planned"], 2)
        self.assertEqual(len(queued["queued"]), 2)
        self.assertEqual(queued["plan_digest"], plan["plan_digest"])
        self.assertFalse(queued["execution_authorized"])
        self.assertFalse(queued["memory_promotion_authorized"])
        self.assertEqual(set(x["source_id"] for x in queued["queued"]),
                         {"source-a", "source-b"})
        self.assertTrue(all(x["reason"] == "stale_source" for x in queued["queued"]))
        orders = self.wiki.recrawl_queue(OWNER, now=NOW, authorized=True)
        self.assertEqual(len(orders), 2)
        self.assertTrue(all(x["execution_authorized"] is False for x in orders))
        head = self.wiki.hoag_view(OWNER, now=NOW, authorized=True)["head_digest"]
        rerun = self.enqueue()
        self.assertEqual(rerun["queued"], ())
        self.assertEqual(rerun["already_pending"], ("source-a", "source-b"))
        self.assertEqual(self.wiki.hoag_view(OWNER, now=NOW, authorized=True)["head_digest"], head)
        self.library.close()
        self.library = ReviewedKnowledgeStore(self.path)
        self.wiki = DragonWisdomPyramid(self.library)
        self.assertEqual(len(self.wiki.recrawl_queue(OWNER, now=NOW, authorized=True)), 2)

    def test_atomic_rollback_when_second_source_parent_was_swapped(self):
        original = self.library.plan_recrawl
        def corrupt(*args, **kwargs):
            plan = original(*args, **kwargs)
            requests = [dict(x) for x in plan["requests"]]
            requests[1]["expected_parent_digest"] = "f" * 64
            return {**plan, "requests": requests}
        with patch.object(self.library, "plan_recrawl", side_effect=corrupt):
            with self.assertRaisesRegex(ValueError, "parent"):
                self.enqueue()
        self.assertEqual(self.wiki.recrawl_queue(OWNER, now=NOW, authorized=True), ())
        self.assertIsNone(self.wiki.hoag_view(OWNER, now=NOW, authorized=True)["head_digest"])

    def test_resource_and_trusted_worker_fail_closed(self):
        with self.assertRaises(PermissionError):
            self.enqueue(trusted_worker=False)
        with self.assertRaises(PermissionError):
            self.enqueue(authorized=False)
        for invalid in (False, 0, -1, 33, 100):
            with self.assertRaises(ValueError):
                self.enqueue(limit=invalid)
        self.assertEqual(self.wiki.recrawl_queue(OWNER, now=NOW, authorized=True), ())

    def test_review_below_query_relevance_is_still_a_conflict(self):
        # Two independent supporting sources rank in "jump" queries. A third
        # lower-relevance challenge has no matching query term or tag, but
        # covers the identical canonical mechanic and MUST invalidate acceptance.
        self.library.import_document(
            doc("source-c", "publisher-c", statement="Unrelated observation challenges this claim.",
                stance="challenges", observed_at="2026-10-10T12:30:00Z"),
            expected_parent_digest=None, authorized=True,
        )
        brief = self.library.build_brief(
            OWNER, "jump", authorized=True, min_independent_groups=2,
        )
        self.assertEqual({h.source_id for h in brief.citations},
                         {"source-a", "source-b"})
        with self.assertRaisesRegex(ValueError, "without challenge"):
            self.wiki.wiki_review(
                OWNER, brief, mechanic="platforming",
                disposition="accepted", independent_reviewer_id="wiki-human",
                review_evidence_digest="a" * 64, now=NOW, expires_at=NOW+3600,
                authorized=True, trusted_worker=True,
            )

    def test_completion_requires_real_admitted_new_parent(self):
        first = self.enqueue()
        order = next(x for x in first["queued"] if x["source_id"] == "source-a")
        with self.assertRaisesRegex(ValueError, "new source revision"):
            self.wiki.complete_recrawl(
                OWNER, "source-a", request_digest=order["order_digest"],
                new_revision=self.parents["a"], now=NOW + 1,
                authorized=True, trusted_worker=True,
            )
        updated = self.library.import_document(
            doc("source-a", "publisher-a", observed_at="2026-10-20T11:00:00Z"),
            expected_parent_digest=self.parents["a"], authorized=True,
        )
        result = self.wiki.complete_recrawl(
            OWNER, "source-a", request_digest=order["order_digest"],
            new_revision=updated.revision_digest, now=NOW + 1,
            authorized=True, trusted_worker=True,
        )
        self.assertEqual(result["new_revision"], updated.revision_digest)
        self.assertEqual([x["source_id"] for x in self.wiki.recrawl_queue(
            OWNER, now=NOW + 2, authorized=True)], ["source-b"])
        with self.assertRaisesRegex(ValueError, "wrong"):
            self.wiki.complete_recrawl(
                OWNER, "source-a", request_digest=order["order_digest"],
                new_revision=updated.revision_digest, now=NOW + 2,
                authorized=True, trusted_worker=True,
            )

    def test_freshness_and_clock_reversal_halt_enqueue(self):
        self.enqueue(now=NOW)
        with self.assertRaisesRegex(ValueError, "predates"):
            self.enqueue(now=NOW-1)
        with self.assertRaises(ValueError):
            self.enqueue(max_age_seconds=-1)

    def test_future_observation_is_queued_for_review_not_memory(self):
        updated = self.library.import_document(
            doc("source-a", "publisher-a", observed_at="2026-11-01T12:00:00Z"),
            expected_parent_digest=self.parents["a"], authorized=True,
        )
        self.assertNotEqual(updated.revision_digest, self.parents["a"])
        batch = self.enqueue()
        source_a = next(x for x in batch["queued"] if x["source_id"] == "source-a")
        self.assertEqual(source_a["reason"], "stale_source")
        self.assertEqual(source_a["priority"], 1)


    def test_operator_cli_queues_and_inspects_same_durable_authority(self):
        import io
        import json
        from contextlib import redirect_stdout, redirect_stderr
        from skeleton.ai.game_builder.knowledge_cli import main
        base = ["--store", str(self.path), "--trusted-local-operator"]
        def invoke(*command):
            out = io.StringIO()
            with redirect_stdout(out):
                code = main([*base, *command])
            self.assertEqual(code, 0, out.getvalue())
            return json.loads(out.getvalue())
        response = invoke("queue-recrawls", "--owner", OWNER, "--at-epoch", str(NOW))
        self.assertEqual(len(response["queued"]), 2)
        self.assertFalse(response["execution_authorized"])
        queue = invoke("pending-recrawls", "--owner", OWNER, "--at-epoch", str(NOW))
        self.assertEqual(len(queue["orders"]), 2)
        self.assertTrue(all(not x["execution_authorized"] for x in queue["orders"]))
        hoag = invoke("hoag-view", "--owner", OWNER, "--at-epoch", str(NOW))
        self.assertEqual(hoag["pending_recrawls"], 2)
        self.assertEqual(hoag["items"], [])
        rejected = io.StringIO()
        with redirect_stderr(rejected):
            self.assertEqual(main(["--store", str(self.path), "queue-recrawls",
                                   "--owner", OWNER, "--at-epoch", str(NOW)]), 2)
        self.assertIn("external operator authentication", rejected.getvalue())

    def test_new_accepted_review_supersedes_prior_card_until_reapproved(self):
        # No source drift: even a second accepted Wiki review needs a new
        # explicit human approval and must not keep the older card visible.
        brief = self.library.build_brief(
            OWNER, "jump", authorized=True, min_independent_groups=2,
        )
        def approve(at, hash_char):
            return self.wiki.wiki_review(
                OWNER, brief, mechanic="platforming", disposition="accepted",
                independent_reviewer_id="wiki-human",
                review_evidence_digest=hash_char * 64, now=at,
                expires_at=at + 3600, authorized=True, trusted_worker=True,
            )
        first = approve(NOW, "a")
        self.wiki.promote(OWNER, first["digest"], now=NOW+1,
                          authorized=True, trusted_worker=True, human_approved=True)
        self.assertEqual(len(self.wiki.hoag_view(
            OWNER, now=NOW+1, authorized=True)["items"]), 1)
        next_review = approve(NOW+2, "b")
        self.assertEqual(self.wiki.hoag_view(
            OWNER, now=NOW+2, authorized=True)["items"], [])
        self.wiki.promote(OWNER, next_review["digest"], now=NOW+3,
                          authorized=True, trusted_worker=True, human_approved=True)
        view = self.wiki.hoag_view(OWNER, now=NOW+3, authorized=True)
        self.assertEqual(len(view["items"]), 1)
        self.assertEqual(view["items"][0]["review_digest"], next_review["digest"])


if __name__ == "__main__":
    import unittest
    unittest.main()
