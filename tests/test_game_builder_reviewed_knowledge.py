"""Focused integration and hostile-input coverage for reviewed game knowledge."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import sqlite3
import tempfile
import unittest

from skeleton.ai.game_builder.reviewed_knowledge import (
    KnowledgeError,
    KnowledgePolicy,
    ReviewedDocument,
    ReviewedKnowledgeStore,
    ReviewedNote,
)


TEXT = (
    "Jump arcs should remain predictable across platforms. "
    "Wall jumping needs readable feedback. "
    "A camera should preserve spatial context while the player moves."
)


def document(
    *, owner="studio-a", source_id="source-a", text=TEXT,
    time="2026-10-08T12:00:00Z", scopes=("design_reference", "research"),
    dependence_group="publisher-a", approved=True, status="active",
    stance="supports", mechanic="platforming", statement="Jump timing should be predictable.",
    marker="Jump arcs should remain predictable", note_id="note-a",
    url="https://example.org/game-research",
):
    notes = ()
    if status == "active":
        start = text.index(marker)
        notes = (ReviewedNote(
            note_id=note_id,
            mechanic=mechanic,
            statement=statement,
            start=start,
            end=start + len(marker),
            stance=stance,
            confidence_ppm=850_000,
            dependence_group=dependence_group,
            tags=("gameplay", "timing"),
        ),)
    return ReviewedDocument(
        owner=owner, source_id=source_id, source_url=url,
        title="Game research observations", text=text, observed_at=time,
        license_id="licensed-for-reference", allowed_scopes=scopes,
        reviewer_id="human-reviewer", approved=approved,
        notes=notes, status=status,
    )


def mapped_document(doc):
    return {
        "owner": doc.owner, "source_id": doc.source_id,
        "source_url": doc.source_url, "title": doc.title,
        "text": doc.text, "observed_at": doc.observed_at,
        "license_id": doc.license_id,
        "allowed_scopes": list(doc.allowed_scopes),
        "reviewer_id": doc.reviewer_id, "approved": doc.approved,
        "notes": [note.to_payload() for note in doc.notes],
        "status": doc.status,
    }


class ReviewedKnowledgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.dbfile = Path(self.temp.name, "reviewed.sqlite3")
        self.store = ReviewedKnowledgeStore(self.dbfile)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def admit(self, doc=None, *, expected=None):
        return self.store.import_document(
            doc or document(), expected_parent_digest=expected,
            authorized=True,
        )

    def test_import_persists_exact_citations_not_entire_source(self):
        receipt = self.admit()
        self.assertEqual(receipt.revision, 0)
        self.assertEqual(receipt.claim_count, 1)
        hits = self.store.search("studio-a", "jump timing", authorized=True)
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].exact_quote, "Jump arcs should remain predictable")
        self.assertEqual(hits[0].start, 0)
        self.assertEqual(hits[0].revision_digest, receipt.revision_digest)
        raw = self.store.db.execute(
            "SELECT payload FROM game_builder_knowledge"
        ).fetchone()[0]
        self.assertNotIn(TEXT, raw)
        self.assertIn("Jump arcs should remain predictable", raw)
        self.store.close()
        self.store = ReviewedKnowledgeStore(self.dbfile)
        reopened = self.store.search("studio-a", "jump", authorized=True)
        # Relevance is specific to the query, not an immutable citation field.
        self.assertEqual(
            tuple(replace(hit, relevance=0) for hit in hits),
            tuple(replace(hit, relevance=0) for hit in reopened),
        )
        self.assertEqual(self.store.history("studio-a", "source-a", authorized=True)[0], receipt)

    def test_idempotent_queries_and_root(self):
        self.admit()
        first = self.store.snapshot_root("studio-a", authorized=True)
        self.assertEqual(first, self.store.snapshot_root("studio-a", authorized=True))
        self.assertEqual(
            self.store.search("studio-a", "platforming", authorized=True),
            self.store.search("studio-a", "platforming", authorized=True),
        )

    def test_repeated_source_revision_and_optimistic_custody(self):
        first = self.admit()
        with self.assertRaisesRegex(KnowledgeError, "parent"):
            self.admit(replace(document(), observed_at="2026-10-09T12:00:00Z"))
        updated = replace(
            document(),
            observed_at="2026-10-09T12:00:00Z",
            notes=(replace(document().notes[0], confidence_ppm=990_000),),
        )
        second = self.admit(updated, expected=first.revision_digest)
        self.assertEqual(second.revision, 1)
        self.assertEqual(second.parent_digest, first.revision_digest)
        self.assertEqual(len(self.store.history("studio-a", "source-a", authorized=True)), 2)
        self.assertEqual(self.store.search("studio-a", "jump", authorized=True)[0].confidence_ppm, 990_000)
        with self.assertRaisesRegex(KnowledgeError, "parent"):
            self.admit(replace(updated, observed_at="2026-10-10T12:00:00Z"), expected=first.revision_digest)

    def test_retraction_hides_old_evidence_and_invalidates_brief(self):
        first = self.admit()
        brief = self.store.build_brief("studio-a", "jump", authorized=True)
        retraction = replace(
            document(), text="", notes=(), approved=False, status="retracted",
            observed_at="2026-10-09T12:00:00Z",
        )
        self.admit(retraction, expected=first.revision_digest)
        self.assertEqual(self.store.search("studio-a", "jump", authorized=True), ())
        with self.assertRaisesRegex(KnowledgeError, "changed"):
            self.store.require_fresh_brief(brief, authorized=True)
        self.assertEqual(len(self.store.history("studio-a", "source-a", authorized=True)), 2)

    def test_rights_scope_no_inferred_design_permission(self):
        self.admit(replace(document(), allowed_scopes=("research",)))
        self.assertEqual(self.store.search("studio-a", "jump", authorized=True), ())
        self.assertEqual(len(self.store.search(
            "studio-a", "jump", scope="research", authorized=True,
        )), 1)
        with self.assertRaisesRegex(KnowledgeError, "insufficient"):
            self.store.build_brief("studio-a", "jump", authorized=True)

    def test_nonapproved_source_cannot_publish_active_claims(self):
        with self.assertRaises(KnowledgeError):
            replace(document(), approved=False)
        with self.assertRaises(KnowledgeError):
            replace(document(), notes=())
        with self.assertRaises(KnowledgeError):
            replace(document(), status="retracted")

    def test_citation_span_is_exact_and_bounded(self):
        base = document()
        bad = replace(base.notes[0], end=len(TEXT) + 1)
        with self.assertRaisesRegex(KnowledgeError, "outside"):
            self.admit(replace(base, notes=(bad,)))
        # The immutable note itself rejects invalid zero-length spans at creation.
        with self.assertRaises(KnowledgeError):
            replace(base.notes[0], start=6, end=6)
        long_doc = replace(
            base, text="Z" * 1200,
            notes=(replace(base.notes[0], start=0, end=1100),),
        )
        with self.assertRaisesRegex(KnowledgeError, "quote"):
            self.admit(long_doc)

    def test_fail_closed_on_duplicate_identity(self):
        base = document()
        with self.assertRaisesRegex(KnowledgeError, "duplicate note"):
            self.admit(replace(base, notes=base.notes + base.notes))

    def test_unicode_offsets_and_digest(self):
        txt = "🔊 Прыжок читаемый — camera follows the player."
        note = replace(
            document().notes[0],
            start=0, end=len("🔊 Прыжок читаемый"),
            statement="Camera framing remains legible.",
            mechanic="camera",
        )
        self.admit(replace(document(), text=txt, notes=(note,)))
        hit = self.store.search("studio-a", "camera", authorized=True)[0]
        self.assertEqual(hit.exact_quote, "🔊 Прыжок читаемый")

    def test_owner_isolation_and_erase(self):
        self.admit()
        self.admit(document(owner="studio-b"))
        self.assertEqual(len(self.store.search("studio-a", "jump", authorized=True)), 1)
        self.assertEqual(len(self.store.search("studio-b", "jump", authorized=True)), 1)
        with self.assertRaises(PermissionError):
            self.store.erase_owner("studio-a", authorized=False)
        self.assertEqual(self.store.erase_owner("studio-a", authorized=True), 1)
        self.assertEqual(self.store.search("studio-a", "jump", authorized=True), ())
        self.assertEqual(len(self.store.search("studio-b", "jump", authorized=True)), 1)

    def test_same_publisher_is_not_multiple_independent_support(self):
        self.admit()
        other = replace(
            document(source_id="source-b", dependence_group="publisher-a"),
            source_url="https://another.example.org/research",
        )
        self.admit(other)
        self.assertEqual(len(self.store.search(
            "studio-a", "jump", authorized=True, diversify=False,
        )), 2)
        self.assertEqual(len(self.store.search("studio-a", "jump", authorized=True)), 1)
        with self.assertRaisesRegex(KnowledgeError, "independent"):
            self.store.build_brief(
                "studio-a", "jump", min_independent_groups=2, authorized=True,
            )

    def test_conflicting_sources_are_exposed_not_resolved(self):
        self.admit()
        challenger = replace(
            document(
                source_id="source-b", dependence_group="publisher-b",
                stance="challenges", note_id="note-b",
                statement="Jump timing is often unpredictable in this scenario.",
            ),
            source_url="https://independent.example.org/research",
        )
        self.admit(challenger)
        brief = self.store.build_brief(
            "studio-a", "jump", min_independent_groups=2, authorized=True,
        )
        self.assertEqual(brief.conflicts, ("platforming",))
        self.assertEqual(brief.independent_groups, 2)
        self.assertTrue(brief.requires_human_decision)
        self.assertEqual(brief.to_payload()["schema"], "skeleton.game_builder.reviewed_brief.v1")
        self.store.require_fresh_brief(brief, authorized=True)

    def test_research_brief_rejects_modified_or_stale_claims(self):
        self.admit()
        brief = self.store.build_brief("studio-a", "jump", authorized=True)
        forged = replace(brief, citations=(replace(brief.citations[0], exact_quote="fabricated"),))
        with self.assertRaises(KnowledgeError):
            self.store.require_fresh_brief(forged, authorized=True)

    def test_authorization_on_every_read_write_control(self):
        with self.assertRaises(PermissionError):
            self.store.import_document(document(), expected_parent_digest=None, authorized=False)
        self.admit()
        with self.assertRaises(PermissionError):
            self.store.search("studio-a", "jump", authorized=False)
        with self.assertRaises(PermissionError):
            self.store.build_brief("studio-a", "jump", authorized=False)
        with self.assertRaises(PermissionError):
            self.store.history("studio-a", "source-a", authorized=False)
        with self.assertRaises(PermissionError):
            self.store.snapshot_root("studio-a", authorized=False)

    def test_mutated_stored_claim_digest_is_rejected(self):
        self.admit()
        self.store.db.execute(
            """UPDATE game_builder_knowledge SET payload=replace(payload, 'predictable', 'unreliable')
            WHERE owner='studio-a'"""
        )
        with self.assertRaisesRegex(KnowledgeError, "integrity"):
            self.store.search("studio-a", "jump", authorized=True)

    def test_modified_digest_is_rejected(self):
        self.admit()
        self.store.db.execute(
            "UPDATE game_builder_knowledge SET digest=? WHERE owner=?",
            ("0" * 64, "studio-a"),
        )
        with self.assertRaises(KnowledgeError):
            self.store.snapshot_root("studio-a", authorized=True)

    def test_broken_revision_chain_rejected(self):
        first = self.admit()
        self.admit(
            replace(document(), observed_at="2026-10-09T12:00:00Z"),
            expected=first.revision_digest,
        )
        self.store.db.execute(
            "UPDATE game_builder_knowledge SET parent_digest=? WHERE revision=1",
            ("0" * 64,),
        )
        with self.assertRaises(KnowledgeError):
            self.store.search("studio-a", "jump", authorized=True)

    def test_noncanonical_duplicate_key_rejected(self):
        self.admit()
        row = self.store.db.execute(
            "SELECT payload FROM game_builder_knowledge"
        ).fetchone()[0]
        raw = row.replace('{"allowed_scopes":', '{"owner":"studio-a","allowed_scopes":', 1)
        self.store.db.execute(
            "UPDATE game_builder_knowledge SET payload=?", (raw,),
        )
        with self.assertRaises(KnowledgeError):
            self.store.search("studio-a", "jump", authorized=True)

    def test_capacity_and_query_bounds(self):
        store = ReviewedKnowledgeStore(":memory:", policy=KnowledgePolicy(
            max_document_chars=10, max_evidence_chars=5,
            max_claims_per_revision=1, max_revisions_per_owner=2,
            max_query_results=1, max_brief_hits=1,
        ))
        try:
            with self.assertRaisesRegex(KnowledgeError, "character budget"):
                store.import_document(document(), expected_parent_digest=None, authorized=True)
        finally:
            store.close()
        self.admit()
        with self.assertRaises(KnowledgeError):
            self.store.search("studio-a", "jump", limit=101, authorized=True)
        with self.assertRaises(KnowledgeError):
            self.store.search("studio-a", "jump", min_confidence_ppm=True, authorized=True)
        with self.assertRaises(KnowledgeError):
            self.store.build_brief("studio-a", "jump", min_independent_groups=0, authorized=True)

    def test_malicious_source_metadata_rejected(self):
        base = document()
        for value in (
            "http://example.com",
            "https://user:pass@example.org/path",
            "https://example.org/path#fragment",
            "https://example.org:1234/path",
        ):
            with self.subTest(url=value):
                with self.assertRaises(KnowledgeError):
                    replace(base, source_url=value)
        for value in ("2026-10-08 12:00:00", "2026-02-30T12:00:00Z"):
            with self.subTest(time=value):
                with self.assertRaises(KnowledgeError):
                    replace(base, observed_at=value)

    def test_import_mapping_strict_and_bool_offsets(self):
        mapped = mapped_document(document())
        reconstructed = ReviewedDocument.from_mapping(mapped)
        self.assertEqual(reconstructed, document())
        mapped["notes"][0]["start"] = True
        with self.assertRaises(KnowledgeError):
            ReviewedDocument.from_mapping(mapped)
        mapped = mapped_document(document())
        mapped["unknown"] = "must reject"
        with self.assertRaises(KnowledgeError):
            ReviewedDocument.from_mapping(mapped)

    def test_notes_must_be_sorted_and_token_ranking_stable(self):
        note = document().notes[0]
        with self.assertRaises(KnowledgeError):
            replace(note, tags=("timing", "gameplay"))
        self.admit()
        self.assertEqual(
            self.store.search("studio-a", "jump timing", authorized=True),
            self.store.search("studio-a", "timing jump", authorized=True),
        )

    def test_no_false_knowledge_from_empty_owner(self):
        self.assertEqual(self.store.search("studio-a", "jump", authorized=True), ())
        with self.assertRaises(KnowledgeError):
            self.store.build_brief("studio-a", "jump", authorized=True)
        self.assertEqual(len(self.store.snapshot_root("studio-a", authorized=True)), 64)

    def test_rejection_rolls_back_atomically(self):
        self.admit()
        before = self.store.db.execute("SELECT COUNT(*) FROM game_builder_knowledge").fetchone()[0]
        with self.assertRaises(KnowledgeError):
            self.admit(replace(document(), observed_at="2026-10-09T12:00:00Z"))
        after = self.store.db.execute("SELECT COUNT(*) FROM game_builder_knowledge").fetchone()[0]
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
