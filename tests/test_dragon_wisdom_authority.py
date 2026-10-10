"""Signed Dragon reviewer/approver separation and replay-scope adversarial tests."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from skeleton.ai.game_builder.reviewed_knowledge import (
    ReviewedDocument, ReviewedNote, ReviewedKnowledgeStore,
)
from skeleton.ai.game_builder.dragon_wisdom_pyramid import DragonWisdomPyramid
from skeleton.ai.game_builder.dragon_wisdom_authority import DragonWisdomAuthority

NOW = int(datetime(2026, 10, 20, 14, tzinfo=timezone.utc).timestamp())
OWNER = "studio-a"
TEXT = "Original input buffering should be tested with fresh hardware."


def doc(letter: str) -> ReviewedDocument:
    return ReviewedDocument(
        owner=OWNER, source_id="source-" + letter,
        source_url="https://example.org/" + letter,
        title="Independent controller study", text=TEXT,
        observed_at="2026-10-10T12:00:00Z",
        license_id="design-reference",
        allowed_scopes=("design_reference",),
        reviewer_id="source-author-" + letter, approved=True,
        notes=(ReviewedNote(
            note_id="note-" + letter, mechanic="platforming",
            statement="Input buffering merits independent comparison.",
            start=0, end=len("Original input buffering"),
            stance="supports", confidence_ppm=900000,
            dependence_group="publisher-" + letter,
            tags=("input", "buffering"),
        ),),
    )


class SignedAuthorityTests(TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.library = ReviewedKnowledgeStore(Path(self.temp.name) / "knowledge.sqlite")
        self.wiki = DragonWisdomPyramid(self.library)
        for name in ("a", "b"):
            self.library.import_document(doc(name),
                                         expected_parent_digest=None, authorized=True)
        self.auth = DragonWisdomAuthority(
            self.wiki, wiki_signing_key=b"w" * 32,
            approval_signing_key=b"a" * 32, issuer="studio-security",
        )
        self.brief = self.library.build_brief(
            OWNER, "input", min_independent_groups=2, authorized=True,
        )

    def tearDown(self):
        self.library.close()
        self.temp.cleanup()

    def grant(self, role: str, target: str, *, subject="independent-human",
              affiliation="neutral-lab", at=NOW, expiry=None):
        return self.auth.issue_grant(
            OWNER, subject, affiliation, role, target,
            now=at, expires_at=expiry or at + 1000,
            identity_verified=True, authorized=True,
        )

    def review(self, grant=None):
        target = self.brief.to_payload()["brief_digest"]
        return self.auth.review(
            OWNER, self.brief, mechanic="platforming",
            disposition="accepted", review_evidence_digest="b" * 64,
            grant=grant or self.grant("wiki_reviewer", target),
            now=NOW, expires_at=NOW + 3600,
            authorized=True, trusted_worker=True,
        )

    def test_sealed_review_and_separate_human_approval(self):
        result = self.review()
        self.assertEqual(result["reviewer"], "independent-human")
        self.assertEqual(len(result["reviewer_grant_digest"]), 64)
        approver = self.grant("memory_approver", result["digest"], subject="separate-person")
        promoted = self.auth.approve(
            OWNER, result["digest"], grant=approver, now=NOW+1,
            authorized=True, trusted_worker=True,
        )
        self.assertEqual(promoted["approval_evidence_digest"], approver.digest)
        self.assertEqual(len(self.wiki.hoag_view(OWNER, now=NOW+2, authorized=True)["items"]), 1)

    def test_forged_signature_wrong_issuer_role_owner_and_clock(self):
        from skeleton.ai.game_builder.dragon_wisdom_authority import WisdomGrant
        target = self.brief.to_payload()["brief_digest"]
        valid = self.grant("wiki_reviewer", target)
        for change in (
            {"signature": "0" * 64}, {"issuer": "rogue-issuer"},
            {"owner": "another-studio"}, {"role": "memory_approver"},
            {"target_digest": "f" * 64}, {"nonce": "0" * 32},
        ):
            with self.assertRaises(PermissionError):
                self.review(replace(valid, **change))
        for at in (NOW-1, NOW+1000):
            with self.assertRaises(PermissionError):
                self.auth.verify_grant(
                    valid, role="wiki_reviewer", owner=OWNER,
                    target_digest=target, now=at,
                )
        with self.assertRaises(ValueError):
            DragonWisdomAuthority(
                self.wiki, wiki_signing_key=b"same-key-" * 5,
                approval_signing_key=b"same-key-" * 5,
                issuer="studio-security",
            )
        with self.assertRaises(PermissionError):
            self.auth.issue_grant(
                OWNER, "person", "neutral", "wiki_reviewer", target,
                now=NOW, expires_at=NOW+2,
                identity_verified=False, authorized=True,
            )

    def test_source_reviewer_or_publisher_cannot_self_review(self):
        target = self.brief.to_payload()["brief_digest"]
        for kwargs in (
            {"subject": "source-author-a"},
            {"affiliation": "publisher-b"},
        ):
            with self.assertRaisesRegex(PermissionError, "conflicts"):
                self.review(self.grant("wiki_reviewer", target, **kwargs))

    def test_one_person_cannot_self_approve_memory(self):
        reviewed = self.review()
        approver = self.grant("memory_approver", reviewed["digest"],
                              subject="independent-human")
        with self.assertRaisesRegex(PermissionError, "differ"):
            self.auth.approve(
                OWNER, reviewed["digest"], grant=approver, now=NOW+1,
                authorized=True, trusted_worker=True,
            )
        self.assertEqual(self.wiki.hoag_view(OWNER, now=NOW+2, authorized=True)["items"], [])

    def test_challenged_or_changed_source_is_not_approvable(self):
        reviewed = self.review()
        updated = replace(doc("a"), observed_at="2026-10-20T12:00:00Z")
        parent = self.library.history(OWNER, "source-a", authorized=True)[-1].revision_digest
        self.library.import_document(updated, expected_parent_digest=parent,
                                     authorized=True)
        with self.assertRaisesRegex(ValueError, "revisions changed"):
            self.auth.approve(
                OWNER, reviewed["digest"],
                grant=self.grant("memory_approver", reviewed["digest"],
                                 subject="another-person"),
                now=NOW+1, authorized=True, trusted_worker=True,
            )

    def test_unknown_approver_or_wrong_review_receipt_cannot_mint_promotion(self):
        reviewed = self.review()
        target = self.brief.to_payload()["brief_digest"]
        for grant in (self.grant("wiki_reviewer", target),
                      self.grant("memory_approver", "f"*64)):
            with self.assertRaises(PermissionError):
                self.auth.approve(
                    OWNER, reviewed["digest"], grant=grant,
                    now=NOW+1, authorized=True, trusted_worker=True,
                )


if __name__ == "__main__":
    import unittest
    unittest.main()
