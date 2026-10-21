"""Regression checks for Jeeves game-studio rights, receipts and drafts."""
from __future__ import annotations
import json
import sqlite3
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from skeleton.ai.training.book_learning_bridge import BookIntakeError, CHUNK_CHARS, compile_book_intake
from skeleton.ai.training.book_weight_candidate import (_receipt, _all_rows, _bounded_output_hash, _publish_receipt)
from skeleton.jeeves.ai.studio_interaction_contract import (
    FACETS, questions, StudioProposal, StudioEvidenceJournal,
    StudioInteractionError, JeevesStudioController,
)
from skeleton.jeeves.ai.creator_runbook_store import CreatorRunbookStore
from skeleton.jeeves.agent.tools import ToolExecutor, ToolRegistry


class BookTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.out = self.root / "out"
        self.out.mkdir()

    def source(self, text, *, approved=True, permitted=True):
        raw = text.encode("utf-8")
        (self.root / "chapter.txt").write_bytes(raw)
        manifest = {
            "schema_version": "skeleton.jeeves.book_weights_intake.v1",
            "books": [{
                "id": "book-alpha",
                "title": "Original Game Design",
                "rights": {
                    "schema_version": "skeleton.jeeves.game_corpus_rights.v1",
                    "source_kind": "original_authoring",
                    "training_permitted": permitted,
                    "rights_holder": "Independent Author",
                    "rights_basis": "Original authored material",
                    "review_id": "review-2026",
                },
                "chapters": [{
                    "id": "chapter-one", "file": "chapter.txt",
                    "sha256": sha256(raw).hexdigest(), "family": "narrative",
                    "quality_approved": approved,
                    "quality_reviewer_id": "human-reviewer",
                    "quality_review_note": "This chapter has been reviewed as original authored material.",
                }],
            }],
        }
        path = self.root / "manifest.json"
        path.write_text(json.dumps(manifest))
        return path

    def test_full_book_character_coverage(self):
        source = "Real original game design principles. " * 900
        receipt = compile_book_intake(self.source(source), self.out,
                                      operator_review_id="operator-2026")
        chunks = _all_rows(receipt, self.out)
        self.assertEqual(source, "".join(item["answer"] for item in chunks.values()))
        self.assertEqual(len(chunks), receipt["training_examples"])
        self.assertFalse(receipt["candidate_weights_created"])
        self.assertEqual(
            _receipt(self.out / "jeeves-books-operator-2026-receipts.json")["digest"],
            receipt["digest"],
        )

    def test_short_final_segment_merged(self):
        source = "A" * (CHUNK_CHARS + 9)
        receipt = compile_book_intake(self.source(source), self.out,
                                      operator_review_id="operator-2026")
        self.assertEqual(len(_all_rows(receipt, self.out)), 1)

    def test_reject_unreviewed_sources(self):
        for approved, permitted in ((False, True), (True, False)):
            with self.subTest(approved=approved, permitted=permitted):
                with self.assertRaises(BookIntakeError):
                    compile_book_intake(
                        self.source("Original games and authored principles. " * 70,
                                    approved=approved, permitted=permitted),
                        self.out, operator_review_id="operator-2026",
                    )

    def test_shard_digest_changes_detected(self):
        receipt = compile_book_intake(
            self.source("Original gameplay skills. " * 2000),
            self.out, operator_review_id="operator-2026",
        )
        shard = self.out / receipt["shards"][0]["file"]
        shard.write_bytes(shard.read_bytes() + b" ")
        with self.assertRaises(BookIntakeError):
            _all_rows(receipt, self.out)


class InteractionTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.journal = StudioEvidenceJournal(
            self.root / "journal.db", project_id="project-one", session_id="session-one",
        )
        self.addCleanup(self.journal.close)
        self.jeeves = JeevesStudioController(self.journal)

    def test_all_facet_questions_present(self):
        self.assertEqual(len(FACETS), 38)
        self.assertEqual(len(questions()), 38)

    def test_preview_requires_approval_before_running(self):
        plan = self.jeeves.propose(
            [StudioProposal("world", "create", {"intent": {"world": "floating terrain"}})],
            model_checkpoint_sha256="a" * 64,
        )
        self.assertEqual(plan["execution_authority"], "none")
        with CreatorRunbookStore(
            self.root / "runbook.db", plan_sha256=plan["plan_sha256"],
        ) as store:
            executor = ToolExecutor(ToolRegistry())
            with self.assertRaises(StudioInteractionError):
                self.jeeves.runner(plan, executor=executor, store=store)
            self.jeeves.approve(plan, reviewer_id="human-reviewer")
            runner = self.jeeves.runner(plan, executor=executor, store=store)
            self.assertEqual(runner.ready(), ("step-000",))
            with self.assertRaises(StudioInteractionError):
                self.jeeves.observe(runner=runner, store=store, step_id="step-000")

    def test_tamper_resistance(self):
        self.jeeves.answer("canon", "Original world constraints", actor_id="operator")
        with sqlite3.connect(str(self.root / "journal.db")) as db:
            db.execute("UPDATE studio_event SET payload='{}' WHERE sequence=0")
        with self.assertRaises(StudioInteractionError):
            self.journal.read()

    def test_model_cannot_fabricate_execution_receipt(self):
        with self.assertRaises(StudioInteractionError):
            self.journal.append("execution_succeeded", {
                "step_id": "step-000", "receipt_digest": "f" * 64,
            })
        self.assertEqual(self.journal.read(), ())

    def test_unverified_media_rejected(self):
        with self.assertRaises(StudioInteractionError):
            self.jeeves.attach(
                modality="image", artifact_digest="bad",
                source_id="asset-01", rights_scope="original",
            )


class BookCandidateReceiptTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_actual_model_bytes_are_hashed(self):
        checkpoint = self.root / "candidate.json"
        checkpoint.write_bytes(b"actual tensor checkpoint bytes")
        self.assertEqual(_bounded_output_hash(checkpoint),
                         sha256(checkpoint.read_bytes()).hexdigest())
        checkpoint.write_bytes(checkpoint.read_bytes() + b"mutated")
        self.assertNotEqual(_bounded_output_hash(checkpoint),
                            sha256(b"actual tensor checkpoint bytes").hexdigest())

    def test_evaluation_receipt_is_immutable(self):
        target = self.root / "evaluation-receipt.json"
        record = {"candidate_sha256": "a" * 64,
                  "production_model_auto_promoted": False}
        _publish_receipt(target, record)
        self.assertEqual(json.loads(target.read_text()), record)
        with self.assertRaises(BookIntakeError):
            _publish_receipt(target, record)

    def test_refuse_fake_or_symlink_candidate(self):
        with self.assertRaises(BookIntakeError):
            _bounded_output_hash(self.root / "missing")
        (self.root / "real").write_bytes(b"real model")
        (self.root / "link").symlink_to(self.root / "real")
        with self.assertRaises(BookIntakeError):
            _bounded_output_hash(self.root / "link")


if __name__ == "__main__":
    unittest.main()
