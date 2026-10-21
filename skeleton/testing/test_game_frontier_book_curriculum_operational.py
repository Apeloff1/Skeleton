"""Jeeves' source-grounded study, real book materialization and source practice.

No fake weight-training outcomes. Practical exercises run on immutable
canonical project source and only become persisted via host-authorized CAS.
"""
from __future__ import annotations

from hashlib import sha256
from io import BytesIO
import json
from unittest.mock import AsyncMock, patch
import unittest
from zipfile import ZipFile

from skeleton.forge.game_frontier_studio import StudioError, StudioProject
from skeleton.forge.game_frontier_studio_authoring import (
    AUTHORING_ACTIONS, apply_authoring_batch, project_digest,
)
from skeleton.jeeves.game_frontier_book_curriculum import (
    GENERATIONS, TOTAL_REFERENCES, assessment, curriculum_catalog,
    exemplar, from_uri, lesson, locate, manifest, materialize_archive,
    reference,
)
from skeleton.jeeves.game_frontier_curriculum_path import (
    learning_path, batch_program, PRACTICE_CHECKS,
)
from skeleton.jeeves.game_frontier_curriculum_practice import verify_source_practice
from skeleton.jeeves.game_studio_tools import (
    StudioCommand, READ_OPERATIONS, WRITE_OPERATIONS,
)
from skeleton.testing.test_game_frontier_studio_production_5000 import (
    original_project, arguments,
)


class CompleteJeevesSourceCurriculum(unittest.TestCase):
    def test_all_seven_generations_have_exact_complete_address_ranges(self):
        book = curriculum_catalog()
        self.assertEqual(7, len(book["curriculum_levels"]))
        self.assertEqual(TOTAL_REFERENCES, book["book_count"])
        self.assertEqual(9_999_999_000, TOTAL_REFERENCES)
        self.assertFalse(book["weight_promoted"])
        for n, (generation, _, count) in enumerate(GENERATIONS):
            with self.subTest(generation=generation):
                self.assertEqual(count, book["curriculum_levels"][n]["book_count"])
                for index in (0, count-1):
                    item = reference(generation, index)
                    self.assertEqual(item["ref"], f"forgebook:{generation}:{index}")
                    self.assertEqual(item, from_uri(item["ref"]))
                    self.assertEqual(index, item["index"])
                    self.assertTrue(item["path"].endswith(".md"))
                    self.assertFalse(item["trained"])
                    if index == 0:
                        self.assertEqual(
                            item, locate(sum(n2 for _, _, n2 in GENERATIONS[:n])))
        with self.assertRaises(StudioError):
            from_uri("forgebook:epic:00012")
        with self.assertRaises(StudioError):
            from_uri("forgebook:epic:-1")
        with self.assertRaises(StudioError):
            from_uri("forgebook:unknown:0")
        with self.assertRaises(StudioError):
            reference("epic", 9_000_000_000)

    def test_hash_linked_seven_level_prerequisites(self):
        for generation, _, count in GENERATIONS:
            for index in (0, min(432_100, count-1), count-1):
                with self.subTest(generation=generation, index=index):
                    path = learning_path(generation, index)
                    self.assertTrue(path["curriculum_sha256"])
                    self.assertEqual(f"forgebook:{generation}:{index}", path["target"])
                    self.assertEqual(
                        [entry[0] for entry in GENERATIONS[:path["course_levels"]]],
                        [entry["generation"] for entry in path["modules"]])
                    self.assertFalse(path["weights_promoted"])
                    self.assertTrue(path["requires_independent_practical_receipts"])
                    for pos, module in enumerate(path["modules"]):
                        self.assertEqual(pos+1, module["level"])
                        self.assertEqual(8, len(module["practical_checkpoints"]))
                        self.assertEqual(PRACTICE_CHECKS,
                                         tuple(module["practical_checkpoints"]))
                        self.assertFalse(module["practical_evidence_verified"])
                        self.assertIn(module["operation"], AUTHORING_ACTIONS)
                        if pos:
                            self.assertEqual(
                                path["modules"][pos-1]["book"],
                                module["parent_book"])
                            self.assertEqual(
                                path["modules"][pos-1]["lesson_sha256"],
                                module["prerequisite_sha256"])
                        else:
                            self.assertIsNone(module["parent_book"])
                            self.assertIsNone(module["prerequisite_sha256"])

    def test_real_bounded_curriculum_sessions_and_no_false_job_claims(self):
        book = batch_program("epic", 5, sessions=8, stride=2)
        self.assertEqual(8, len(book["tasks"]))
        self.assertEqual("forgebook:epic:19", book["tasks"][-1]["book"])
        self.assertEqual(0, book["issued_jobs"])
        self.assertEqual(0, book["completed_lessons"])
        self.assertFalse(book["model_weights_updated"])
        for item in book["tasks"]:
            self.assertIn(item["exact_operation"], AUTHORING_ACTIONS)
            self.assertEqual("not_started", item["status"])
        for args in (dict(generation="epic", index=-1),
                     dict(generation="epic", index=8_999_999_999, sessions=2),
                     dict(generation="epic", index=0, sessions=0),
                     dict(generation="epic", index=0, stride=0)):
            with self.subTest(request=args):
                with self.assertRaises(StudioError):
                    batch_program(**args)

    def test_book_lessons_and_checks_are_bounded_provenance_not_weights(self):
        item = lesson("epic", 0)
        self.assertEqual(10, len(item["questions"]))
        self.assertIn(item["source_exercise_action"], AUTHORING_ACTIONS)
        answers = item["reference"]["identity"]
        exact = assessment("epic", 0, answers)
        self.assertEqual(1., exact["score"])
        self.assertTrue(exact["mastery_earned"])
        self.assertFalse(exact["practical_preview_verified"])
        self.assertFalse(exact["weight_trained"])
        self.assertEqual(64, len(exact["receipt_sha256"]))
        incorrect = assessment("epic", 0, ["mismatch"]*len(answers))
        self.assertLess(incorrect["score"], 1.)
        with self.assertRaises(StudioError):
            assessment("epic", 0, answers[:-1])

    def test_actual_manifest_bytes_and_reproducible_zip_bundle(self):
        for generation in ("worldline", "epoch", "saga", "epic"):
            with self.subTest(generation=generation):
                rendered = manifest(generation, 0)
                self.assertTrue(rendered["content_realized"])
                self.assertEqual(
                    sha256(rendered["markdown"].encode("utf8")).hexdigest(),
                    rendered["content_sha256"])
                self.assertFalse(rendered["weight_trained"])
        chosen = [{"generation": "worldline", "index": 0},
                  {"generation": "epic", "index": 1}]
        first, receipt = materialize_archive(chosen)
        second, again = materialize_archive(chosen)
        self.assertEqual(first, second)
        self.assertEqual(receipt["archive_sha256"], again["archive_sha256"])
        with ZipFile(BytesIO(first)) as zipfile:
            names = zipfile.namelist()
            self.assertEqual(3, len(names))
            self.assertIn("manifest.json", names)
            ledger = json.loads(zipfile.read("manifest.json"))
            self.assertEqual(2, ledger["books_physically_rendered"])
            self.assertFalse(ledger["training_weights_promoted"])
            for recorded in ledger["manifestations"]:
                self.assertEqual(
                    recorded["content_sha256"],
                    sha256(zipfile.read(recorded["path"])).hexdigest())
        with self.assertRaises(StudioError):
            materialize_archive(chosen*2)

    def test_exact_book_operation_actually_mutates_game_source_without_saving(self):
        original = original_project()
        action = exemplar("epic", 0)
        self.assertIn(action, AUTHORING_ACTIONS)
        before = project_digest(original)
        params = arguments(action)
        output = apply_authoring_batch(original, [
            {"action": action, "parameters": params}
        ])
        self.assertIsInstance(output["project"], StudioProject)
        self.assertNotEqual(before, project_digest(output["project"]))
        self.assertEqual(before, project_digest(original))
        self.assertEqual(output["receipt"]["action_count"], 1)
        self.assertTrue(output["receipt"]["actually_changed"])

    def test_independent_practical_evidence_rejects_forged_source_or_book(self):
        original = original_project()
        operation = exemplar("epic", 0)
        result = apply_authoring_batch(original, [
            {"action": operation, "parameters": arguments(operation)}
        ])
        evidence = verify_source_practice(
            original.project_id, "epic", 0, result["receipt"],
            current_source_sha256=project_digest(original),
            expected_candidate_sha256=project_digest(result["project"]),
        )
        self.assertTrue(evidence["source_practice_verified"])
        self.assertEqual("forgebook:epic:0", evidence["book"])
        self.assertEqual(operation, evidence["source_operation"])
        self.assertFalse(evidence["model_weights_trained"])
        self.assertFalse(evidence["project_saved"])
        self.assertFalse(evidence["independent_human_reviewed"])
        self.assertEqual(64, len(evidence["evidence_sha256"]))
        with self.assertRaises(StudioError):
            verify_source_practice(
                original.project_id, "epic", 1, result["receipt"],
                current_source_sha256=project_digest(original),
                expected_candidate_sha256=project_digest(result["project"]),
            )
        fake = {**result["receipt"],
                "changes": [dict(result["receipt"]["changes"][0],
                                 operation="epic_fake_authoring_operation")]}
        with self.assertRaises(StudioError):
            verify_source_practice(
                original.project_id, "epic", 0, fake,
                current_source_sha256=project_digest(original),
                expected_candidate_sha256=project_digest(result["project"]),
            )
        forged = dict(result["receipt"], receipt_sha256="0"*64)
        with self.assertRaises(StudioError):
            verify_source_practice(
                original.project_id, "epic", 0, forged,
                current_source_sha256=project_digest(original),
                expected_candidate_sha256=project_digest(result["project"]),
            )

    def test_jeeves_registry_advertises_separate_read_and_write_auth(self):
        for name in (
            "game.studio.curriculum.catalog", "game.studio.curriculum.reference",
            "game.studio.curriculum.lesson", "game.studio.curriculum.path",
            "game.studio.curriculum.worklist",
            "game.studio.curriculum.assess", "game.studio.curriculum.practice",
            "game.studio.curriculum.automation.plan",
            "game.studio.curriculum.automation.preview",
            "game.studio.book.manifest",
        ):
            self.assertIn(name, READ_OPERATIONS)
        self.assertIn("game.studio.curriculum.automation.commit",
                      WRITE_OPERATIONS)
        self.assertNotIn("game.studio.curriculum.automation.commit",
                         READ_OPERATIONS)
        self.assertFalse(StudioCommand(
            "game.studio.curriculum.automation.plan", "owned",
            {"books": [{"generation": "epic", "index": 0}], "parameters": {}},
        ).mutates)


class HostAuthorizedCurriculumOperation(unittest.IsolatedAsyncioTestCase):
    async def test_host_scoped_plan_preview_commit_and_reject_stale(self):
        # Focused CI runs with --noconftest, so resolve the canonical app root
        # explicitly rather than relying on another test suite's sys.path.
        import sys
        backend = str(Path(__file__).resolve().parents[2] / "backend")
        if backend not in sys.path:
            sys.path.insert(0, backend)
        from core.game_studio_tools import execute_studio_command
        from core import game_frontier_authoring as forge_author
        from core.game_learning import workspace

        original = original_project()
        initial = project_digest(original)
        op = exemplar("epic", 0)
        altered = apply_authoring_batch(original, [
            {"action": op, "parameters": arguments(op)}
        ])
        candidate = project_digest(altered["project"])
        saved = {"revision": 7, "sha": initial}
        calls = []

        async def fake_document(_scope, _id):
            return {"expected_version": saved["revision"],
                    "source_sha256": saved["sha"]}

        async def fake_edit(_scope, _id, body, *, preview):
            calls.append((preview, body))
            if body["expected_version"] != saved["revision"] or (
                    body["expected_sha256"] != saved["sha"]):
                raise StudioError("stale authorization")
            if preview:
                return {"candidate_sha256": candidate,
                        "batch_receipt": altered["receipt"]}
            saved.update(revision=8, sha=candidate)
            return {"source_sha256": candidate, "expected_version": 8,
                    "persisted": True}

        def command(mode, **payload):
            return StudioCommand("game.studio.curriculum.automation."+mode,
                                 "owned", {"books": [{"generation": "epic", "index": 0}],
                                           "parameters": arguments(op), **payload})

        scope = {"tenant_id": "company", "owner_id": "owner"}
        with (patch.object(workspace, "_scope", side_effect=lambda *_: scope),
              patch.object(workspace, "_project", new_callable=AsyncMock, return_value={"id": "owned"}),
              patch.object(workspace, "_input", new_callable=AsyncMock, return_value={"input": True}),
              patch.object(workspace, "_authority", new_callable=AsyncMock, return_value=True),
              patch.object(forge_author, "document", side_effect=fake_document),
              patch.object(forge_author, "edit", side_effect=fake_edit)):
            plan = await execute_studio_command(scope, command("plan"))
            self.assertEqual([op], plan["operations"])
            self.assertFalse(plan["persisted"])
            preview = await execute_studio_command(scope, command(
                "preview", expected_revision=7, expected_sha256=initial))
            self.assertEqual(candidate, preview["candidate_sha256"])
            self.assertFalse(preview["persisted"])
            self.assertTrue(preview["measured_changed"])
            practical = await execute_studio_command(scope, StudioCommand(
                "game.studio.curriculum.practice", "owned", {
                    "books": [{"generation": "epic", "index": 0}],
                    "parameters": arguments(op),
                    "expected_revision": 7,
                    "expected_sha256": initial,
                }))
            self.assertFalse(practical["persisted"])
            self.assertTrue(practical["practical_attestation"]["source_practice_verified"])
            self.assertEqual(candidate,
                             practical["practical_attestation"]["candidate_sha256"])
            with self.assertRaises(StudioError):
                await execute_studio_command(scope, command(
                    "commit", expected_revision=7, expected_sha256=initial,
                    idempotency_key="operator-saved",
                    approved_candidate_sha256="0"*64))
            self.assertEqual(0, len([c for c in calls if not c[0]]))
            committed = await execute_studio_command(scope, command(
                "commit", expected_revision=7, expected_sha256=initial,
                idempotency_key="operator-saved",
                approved_candidate_sha256=candidate))
            self.assertTrue(committed["persisted"])
            self.assertEqual(candidate, committed["saved_source_sha256"])
            self.assertEqual(1, len([c for c in calls if not c[0]]))
            with self.assertRaises(StudioError):
                await execute_studio_command(scope, command(
                    "preview", expected_revision=7, expected_sha256=initial))


if __name__ == "__main__":
    unittest.main()
