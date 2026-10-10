"""Integration/adversarial tests for Dragon's derived Almanac/Wiki/HOAG ledger."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from skeleton.ai.game_builder.dragon_wisdom_pyramid import DragonWisdomPyramid
from skeleton.ai.game_builder.reviewed_knowledge import (
    ReviewedDocument, ReviewedKnowledgeStore, ReviewedNote,
)

OWNER = "studio-a"
NOW = 1_791_638_400
TEXT = "Jump timing should remain predictable across platforms."
QUOTE = "Jump timing should remain predictable"


def source(source_id: str, group: str, *, when: str = "2026-10-10T12:00:00Z",
           stance: str = "supports", status: str = "active") -> ReviewedDocument:
    note = ReviewedNote(
        note_id="note-" + source_id, mechanic="platforming",
        statement="Jump timing should be predictable.",
        start=0, end=len(QUOTE), stance=stance,
        confidence_ppm=870_000, dependence_group=group,
        tags=("jump", "timing"),
    )
    return ReviewedDocument(
        owner=OWNER, source_id=source_id,
        source_url="https://example.org/" + source_id,
        title="Original gameplay research", text=TEXT if status == "active" else "",
        observed_at=when, license_id="permitted-design-reference",
        allowed_scopes=("design_reference", "research"),
        reviewer_id="reviewer-" + source_id,
        approved=status == "active",
        notes=(note,) if status == "active" else (),
        status=status,
    )


class DragonWisdomPyramidTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "wisdom.sqlite"
        self.lib = ReviewedKnowledgeStore(self.path)
        self.wiki = DragonWisdomPyramid(self.lib)
        self.a = self.lib.import_document(source("source-a", "publisher-a"),
                                          expected_parent_digest=None, authorized=True)
        self.b = self.lib.import_document(source("source-b", "publisher-b"),
                                          expected_parent_digest=None, authorized=True)

    def tearDown(self):
        self.lib.close()
        self.temp.cleanup()

    def brief(self):
        return self.lib.build_brief(
            OWNER, "jump", authorized=True,
            min_independent_groups=2,
        )

    def review(self, *, disposition="accepted"):
        return self.wiki.wiki_review(
            OWNER, self.brief(), mechanic="platforming",
            disposition=disposition, independent_reviewer_id="wiki-reviewer",
            review_evidence_digest="a" * 64,
            now=NOW, expires_at=NOW + 86400,
            authorized=True, trusted_worker=True,
        )

    def promote(self, review):
        return self.wiki.promote(
            OWNER, review["digest"], now=NOW + 1, authorized=True,
            trusted_worker=True, human_approved=True,
        )

    def test_end_to_end_review_memory_restart_and_advisory_projection(self):
        review = self.review()
        self.assertEqual(review["independent_groups"], 2)
        self.promote(review)
        view = self.wiki.hoag_view(OWNER, now=NOW + 2, authorized=True)
        self.assertEqual(view["permanent_memory_eligible"], 1)
        self.assertEqual(view["items"][0]["mechanic"], "platforming")
        self.assertFalse(view["items"][0]["training_authorized"])
        self.assertFalse(view["items"][0]["release_authorized"])
        self.assertNotIn(QUOTE, str(view))
        self.lib.close()
        self.lib = ReviewedKnowledgeStore(self.path)
        self.wiki = DragonWisdomPyramid(self.lib)
        self.assertEqual(self.wiki.hoag_view(OWNER, now=NOW + 2, authorized=True), view)
        self.assertEqual(self.wiki.hoag_view(OWNER, now=NOW + 86400, authorized=True)["items"], [])

    def test_two_dependent_sources_cannot_count_as_independent(self):
        doc = replace(source("source-b", "publisher-a"), observed_at="2026-10-11T12:00:00Z")
        self.lib.import_document(doc, expected_parent_digest=self.b.revision_digest,
                                 authorized=True)
        with self.assertRaisesRegex(ValueError, "independent"):
            self.review()

    def test_challenge_blocks_acceptance_and_requires_review(self):
        challenger = replace(source("source-b", "publisher-b", stance="challenges"),
                             observed_at="2026-10-11T12:00:00Z")
        self.lib.import_document(challenger, expected_parent_digest=self.b.revision_digest,
                                 authorized=True)
        with self.assertRaisesRegex(ValueError, "supporting"):
            self.review()
        contested = self.review(disposition="challenged")
        with self.assertRaisesRegex(ValueError, "unapproved"):
            self.promote(contested)

    def test_recrawl_request_suspends_promotion_and_requires_new_revision(self):
        review = self.review()
        order = self.wiki.recrawl(
            OWNER, "source-a", reason="changed_source",
            expected_revision=self.a.revision_digest, now=NOW + 1,
            authorized=True, trusted_worker=True,
        )
        queue = self.wiki.recrawl_queue(OWNER, now=NOW + 2, authorized=True)
        self.assertEqual(len(queue), 1)
        self.assertFalse(queue[0]["execution_authorized"])
        with self.assertRaisesRegex(ValueError, "outstanding"):
            self.wiki.recrawl(OWNER, "source-a", reason="changed_source",
                              expected_revision=self.a.revision_digest, now=NOW + 2,
                              authorized=True, trusted_worker=True)
        with self.assertRaisesRegex(ValueError, "recrawl"):
            self.promote(review)
        with self.assertRaisesRegex(ValueError, "new source revision"):
            self.wiki.complete_recrawl(OWNER, "source-a", request_digest=order["digest"],
                                       new_revision=self.a.revision_digest, now=NOW + 3,
                                       authorized=True, trusted_worker=True)
        new = self.lib.import_document(
            source("source-a", "publisher-a", when="2026-10-11T12:00:00Z"),
            expected_parent_digest=self.a.revision_digest, authorized=True,
        )
        self.wiki.complete_recrawl(OWNER, "source-a", request_digest=order["digest"],
                                   new_revision=new.revision_digest, now=NOW + 3,
                                   authorized=True, trusted_worker=True)
        self.assertEqual(self.wiki.recrawl_queue(OWNER, now=NOW + 4, authorized=True), ())
        with self.assertRaisesRegex(ValueError, "revisions changed"):
            self.promote(review)
        updated = self.review()
        self.promote(updated)
        self.assertEqual(len(self.wiki.hoag_view(OWNER, now=NOW + 4, authorized=True)["items"]), 1)

    def test_retraction_fails_closed_after_publication(self):
        review = self.review()
        self.promote(review)
        self.lib.import_document(
            source("source-a", "publisher-a", when="2026-10-11T12:00:00Z",
                   status="retracted"),
            expected_parent_digest=self.a.revision_digest, authorized=True,
        )
        self.assertEqual(self.wiki.hoag_view(OWNER, now=NOW + 3, authorized=True)["items"], [])

    def test_revocation_is_durable_and_cannot_repromote(self):
        review = self.review()
        self.promote(review)
        self.wiki.revoke(OWNER, review["digest"], reason="rights_change",
                         now=NOW + 2, authorized=True, trusted_worker=True)
        self.assertEqual(self.wiki.hoag_view(OWNER, now=NOW + 3, authorized=True)["items"], [])
        with self.assertRaisesRegex(ValueError, "revoked"):
            self.wiki.promote(OWNER, review["digest"], now=NOW + 3, authorized=True,
                              trusted_worker=True, human_approved=True)

    def test_owner_authority_and_cross_tenant_isolation(self):
        with self.assertRaises(PermissionError):
            self.wiki.hoag_view(OWNER, now=NOW, authorized=False)
        with self.assertRaises(PermissionError):
            self.wiki.recrawl(OWNER, "source-a", reason="stale_source",
                              expected_revision=self.a.revision_digest, now=NOW,
                              authorized=True, trusted_worker=False)
        self.promote(self.review())
        self.assertEqual(self.wiki.hoag_view("studio-b", now=NOW, authorized=True)["items"], [])
        with self.assertRaises(ValueError):
            self.wiki.promote("studio-b", self.wiki.hoag_view(
                OWNER, now=NOW, authorized=True)["items"][0]["review_digest"],
                now=NOW, authorized=True, trusted_worker=True, human_approved=True)

    def test_tampered_journal_halts_all_views_and_mutation(self):
        review = self.review()
        self.promote(review)
        self.lib.db.execute(
            "UPDATE dragon_wisdom_pyramid SET body=replace(body,'accepted','challenged') "
            "WHERE owner=? AND sequence=0", (OWNER,),
        )
        with self.assertRaisesRegex(ValueError, "custody"):
            self.wiki.hoag_view(OWNER, now=NOW, authorized=True)
        with self.assertRaisesRegex(ValueError, "custody"):
            self.wiki.recrawl(OWNER, "source-a", reason="scheduled_refresh",
                              expected_revision=self.a.revision_digest,
                              now=NOW + 3, authorized=True, trusted_worker=True)

    def test_stale_brief_cannot_be_relabelled_as_new_evidence(self):
        brief = self.brief()
        new = self.lib.import_document(
            source("source-a", "publisher-a", when="2026-10-11T12:00:00Z"),
            expected_parent_digest=self.a.revision_digest, authorized=True,
        )
        self.assertNotEqual(new.revision_digest, self.a.revision_digest)
        with self.assertRaisesRegex(ValueError, "changed"):
            self.wiki.wiki_review(OWNER, brief, mechanic="platforming",
                                  disposition="accepted",
                                  independent_reviewer_id="wiki-reviewer",
                                  review_evidence_digest="b" * 64,
                                  now=NOW, expires_at=NOW + 86400,
                                  authorized=True, trusted_worker=True)

    def test_invalid_inputs_do_not_mint_review_authority(self):
        brief = self.brief()
        for bad in (False, True, 1, NOW - 1, NOW + 31 * 86400):
            with self.assertRaises(ValueError):
                self.wiki.wiki_review(
                    OWNER, brief, mechanic="platforming",
                    disposition="accepted", independent_reviewer_id="wiki-reviewer",
                    review_evidence_digest="c" * 64, now=NOW,
                    expires_at=bad, authorized=True, trusted_worker=True,
                )
        with self.assertRaises(PermissionError):
            self.wiki.promote(OWNER, "a" * 64, now=NOW,
                              authorized=True, trusted_worker=True,
                              human_approved=False)


if __name__ == "__main__":
    unittest.main()
