"""Real durable canon continuity and independently reviewed amendment regressions."""
from __future__ import annotations

from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest

from skeleton.jeeves.ai.studio_canon_memory import (
    StudioCanonStore, CanonConflict,
)


class StudioCanonTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "canon.sqlite"
        self.store = StudioCanonStore(self.path, project_id="original-game")
        self.addCleanup(self.store.close)
        self.source = "a" * 64
        self.original = {
            "statement": "Captain Sera was born on the northern sky islands.",
            "scopes": ["cast", "world", "story"],
            "anchors": ["sera", "sky_islands"],
        }

    def revise(self, action="establish", old=None, fact=None):
        return self.store.revise(
            subject_id="captain-sera", attribute_id="origin",
            action=action, expected_fact_sha256=old,
            actor_id="narrative-author", reviewer_id="canon-reviewer",
            source_receipt_sha256=self.source,
            fact=self.original if action == "establish" and fact is None else fact,
        )

    def test_original_fact_and_search_bind_source_and_revision(self):
        receipt = self.revise()
        self.assertEqual(self.store.get("captain-sera", "origin")["fact"], self.original)
        result = self.store.search("Sera originates from northern sky islands")
        self.assertEqual(len(result["results"]), 1)
        self.assertEqual(result["results"][0]["revision_sha256"],
                         receipt["revision_sha256"])
        self.assertEqual(result["results"][0]["source_receipt_sha256"], self.source)
        self.assertEqual(result["canon_head_sha256"], receipt["revision_sha256"])

    def test_amend_requires_correct_prior_revision_and_new_review(self):
        origin = self.revise()
        changed = dict(self.original)
        changed["statement"] = "Captain Sera was born in the northern sky islands and fled to sea."
        with self.assertRaises(CanonConflict):
            self.revise(action="amend", old=None, fact=changed)
        amended = self.revise(action="amend", old=origin["revision_sha256"], fact=changed)
        self.assertNotEqual(amended["revision_sha256"], origin["revision_sha256"])
        self.assertEqual(self.store.verify()["revision_count"], 2)
        self.assertIn("fled to sea", self.store.get("captain-sera", "origin")["fact"]["statement"])

    def test_reopen_and_verify_no_canon_loss(self):
        first = self.revise()
        with StudioCanonStore(self.path, project_id="original-game",
                              expected_head_sha256=first["revision_sha256"]) as reopened:
            self.assertEqual(reopened.get("captain-sera", "origin")["fact"], self.original)
            self.assertTrue(reopened.verify()["independently_pinned"])

    def test_reopen_with_wrong_project_or_pinned_head_fails(self):
        first = self.revise()
        with self.assertRaises(CanonConflict):
            StudioCanonStore(self.path, project_id="foreign-project")
        with self.assertRaises(CanonConflict):
            StudioCanonStore(self.path, project_id="original-game",
                             expected_head_sha256="f" * 64)
        self.assertEqual(len(first["revision_sha256"]), 64)

    def test_distinct_reviewer_is_mandatory(self):
        with self.assertRaises(CanonConflict):
            self.store.revise(
                subject_id="captain-sera", attribute_id="origin",
                action="establish", expected_fact_sha256=None,
                actor_id="same-person", reviewer_id="same-person",
                source_receipt_sha256=self.source, fact=self.original,
            )
        self.assertEqual(self.store.verify()["revision_count"], 0)

    def test_retirement_removes_active_fact_but_preserves_source_history(self):
        initial = self.revise()
        retired = self.revise(action="retire", old=initial["revision_sha256"])
        self.assertIsNone(self.store.get("captain-sera", "origin"))
        self.assertEqual(self.store.search("Sera northern islands")["results"], [])
        self.assertEqual(self.store.verify()["revision_count"], 2)
        self.assertEqual(self.store.verify()["history_sha256"], retired["revision_sha256"])

    def test_wrong_scope_never_leaks_other_project_facts(self):
        self.revise()
        self.assertEqual(self.store.search("Sera", scopes=("physics",))["results"], [])
        self.assertEqual(len(self.store.search("Sera", scopes=("cast",))["results"]), 1)

    def test_external_source_forgery_detected_on_next_search(self):
        self.revise()
        with sqlite3.connect(self.path) as external:
            external.execute("UPDATE canon_revision SET fact_json=? WHERE sequence=0",
                             ('{"statement":"Sera invented the world","scopes":["cast"],'
                              '"anchors":["sera"]}',))
        with self.assertRaises(CanonConflict):
            self.store.search("Sera")

    def test_concurrent_writer_and_stale_expected_head_fail_closed(self):
        with StudioCanonStore(self.path, project_id="original-game") as other:
            first = self.revise()
            self.assertEqual(other.get("captain-sera", "origin")["revision_sha256"],
                             first["revision_sha256"])
            with self.assertRaises(CanonConflict):
                other.revise(
                    subject_id="captain-sera", attribute_id="origin",
                    action="amend", expected_fact_sha256=None,
                    actor_id="narrative-author", reviewer_id="canon-reviewer",
                    source_receipt_sha256=self.source, fact=self.original,
                )

    def test_independent_pin_advances_only_after_host_review(self):
        first = self.revise()
        with StudioCanonStore(
            self.path, project_id="original-game",
            expected_head_sha256=first["revision_sha256"],
        ) as other:
            changed = dict(self.original)
            changed["statement"] = "Sera was born on the northern sky islands and raised on cloudships."
            second = other.revise(
                subject_id="captain-sera", attribute_id="origin",
                action="amend", expected_fact_sha256=first["revision_sha256"],
                actor_id="narrative-author", reviewer_id="canon-reviewer",
                source_receipt_sha256=self.source, fact=changed,
            )
            self.assertEqual(other.verify()["history_sha256"], second["revision_sha256"])
            self.assertTrue(other.verify()["independently_pinned"])

    def test_stored_fact_does_not_mutate_with_original_input(self):
        item = dict(self.original)
        self.store.revise(
            subject_id="captain-sera", attribute_id="origin",
            action="establish", expected_fact_sha256=None,
            actor_id="narrative-author", reviewer_id="canon-reviewer",
            source_receipt_sha256=self.source, fact=item,
        )
        item["scopes"].append("different")
        self.assertEqual(self.store.get("captain-sera", "origin")["fact"]["scopes"],
                         ["cast", "world", "story"])


if __name__ == "__main__":
    unittest.main()
