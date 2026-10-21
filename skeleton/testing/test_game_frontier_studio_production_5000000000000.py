"""5T real composed source operations and 900M generated continuity manuals."""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from skeleton.forge.game_frontier_studio import (
    StudioError, StudioProject, compile_studio_expedition,
)
from skeleton.forge.game_frontier_rpg_events import evaluate_environment_events
from skeleton.forge.game_frontier_studio_authoring import (
    AUTHORING_ACTIONS, execute_authoring, project_digest,
    authored_summary, apply_authoring_batch,
)
from skeleton.forge.game_frontier_studio_epoch_production import EPOCH_ACTIONS
from skeleton.forge.game_frontier_studio_continuity_production import (
    CONTINUITY_ACTIONS, CONTINUITIES, parent_action,
    describe_continuity, search_continuities,
)
from skeleton.forge.game_frontier_studio_continuity_handbooks import (
    BOOK_COUNT, CONTINUITY_BOOK_PATHS, identity, number, metadata,
    receipt, grade, list_books, rank_variants,
)
from skeleton.forge.game_frontier_studio_document import (
    authored_document, load_authored_document,
)
from skeleton.testing.test_game_frontier_studio_production_5000 import (
    original_project, arguments,
)


class FiveTrillionContinuity(unittest.TestCase):
    def test_virtual_catalogue_legacy_indices_and_exact_ownership(self):
        self.assertEqual(4_500_000_000_000, len(CONTINUITY_ACTIONS))
        self.assertEqual(5_000_000_000_000, len(AUTHORING_ACTIONS))
        self.assertEqual(EPOCH_ACTIONS[0], AUTHORING_ACTIONS[50_000_000_000])
        self.assertEqual(EPOCH_ACTIONS[-1], AUTHORING_ACTIONS[499_999_999_999])
        self.assertEqual(CONTINUITY_ACTIONS[0], AUTHORING_ACTIONS[500_000_000_000])
        self.assertEqual(CONTINUITY_ACTIONS[-1], AUTHORING_ACTIONS[-1])
        self.assertTrue(CONTINUITY_ACTIONS[-1] in AUTHORING_ACTIONS)
        self.assertNotIn("continuity_exec_arbitrary_code__________place_legacy",
                         AUTHORING_ACTIONS)
        with self.assertRaises(IndexError):
            _ = CONTINUITY_ACTIONS[len(CONTINUITY_ACTIONS)]

    def test_rank_unrank_and_constant_page_discovery(self):
        indexes = (0, 1, 9, 10, 99, 5_000_000, 15_555_555_555,
                   4_499_999_999_999)
        for i in indexes:
            name = CONTINUITY_ACTIONS[i]
            source, axis = parent_action(name)
            self.assertEqual(EPOCH_ACTIONS[i // 10], source)
            self.assertEqual(CONTINUITIES[i % 10], CONTINUITIES[axis])
            self.assertEqual(name, describe_continuity(name)["operation"])
            self.assertLessEqual(len(name), 384)
        for offset in (0, 1, 33, 444_444_444_444, 4_499_999_999_990):
            result = search_continuities(offset=offset, limit=32)
            self.assertEqual(
                tuple(row["operation"] for row in result["items"]),
                CONTINUITY_ACTIONS[offset:offset + 32],
            )
        narrowed = search_continuities(
            domain="realm", system_layer="stealth",
            director="audio_cues", finish="alternate_endings",
            worldline="sky_navigation", phase="storm_shelters",
            campaign="siege_campaigns", chronicle="emergency_response",
            epoch="daybreak_routes", continuity="climate_recovery", limit=4,
        )
        self.assertEqual(450, narrowed["matched"])
        self.assertEqual(4, len(narrowed["items"]))
        with self.assertRaises(StudioError):
            search_continuities(continuity="../../outside")
        with self.assertRaises(StudioError):
            search_continuities(limit=65)

    def test_ten_domain_by_continuity_source_edits(self):
        base = original_project()
        original_sha = project_digest(base)
        for d in range(10):
            digests = set()
            for a in range(10):
                operation = CONTINUITY_ACTIONS[d * 450_000_000_000 + a]
                with self.subTest(domain=d, continuity=a):
                    edited = execute_authoring(base, operation, arguments(operation))
                    self.assertIsInstance(edited, StudioProject)
                    self.assertNotEqual(original_sha, project_digest(edited))
                    self.assertGreater(len(edited.environmental_pages),
                                       len(base.environmental_pages))
                    self.assertEqual(base.placements,
                                     edited.placements[:len(base.placements)])
                    self.assertEqual(base.native_quests,
                                     edited.native_quests[:len(base.native_quests)])
                    digests.add(project_digest(edited))
            self.assertEqual(10, len(digests))
        self.assertEqual(original_sha, project_digest(base))

    def test_observed_native_action_is_proposal_only(self):
        base = original_project()
        op = CONTINUITY_ACTIONS[0]
        edited = execute_authoring(base, op, arguments(op))
        page = edited.environmental_pages[-1]
        self.assertEqual(2, len(page.conditions))
        accepted = evaluate_environment_events(
            (page,), current={"quest_progress": .75, "npc_reputation": 25.},
            now_ms=50_000)
        self.assertEqual(1, len(accepted.accepted))
        self.assertTrue(accepted.required_runtime_approvals)
        rejected = evaluate_environment_events(
            (page,), current={"quest_progress": 0, "npc_reputation": 0},
            now_ms=50_000)
        self.assertEqual(0, len(rejected.accepted))

    def test_atomic_failure_and_saved_source_replay(self):
        base = original_project()
        op = CONTINUITY_ACTIONS[0]
        result = apply_authoring_batch(base, [
            {"action": op, "parameters": arguments(op)},
        ])
        self.assertTrue(result["receipt"]["actually_changed"])
        reread = load_authored_document(authored_document(result["project"]),
                                        project_id=base.project_id)
        self.assertEqual(project_digest(result["project"]), project_digest(reread))
        with self.assertRaises(StudioError):
            apply_authoring_batch(base, [
                {"action": op, "parameters": arguments(op)},
                {"action": op, "parameters": {
                    **arguments(op), "instance_id": "../forged"}},
            ])
        self.assertEqual(project_digest(base), project_digest(original_project()))
        summary = authored_summary(reread)
        self.assertEqual(4_500_000_000_000, summary["continuity_recipe_count"])
        self.assertEqual(4_999_999_999_500, summary["recipe_catalog_count"])
        self.assertEqual(5_000_000_000_000, summary["catalog_total"])

    def test_native_compiler_produces_game_source(self):
        from skeleton.jeeves.game_frontier_expedition_generation import ArchipelagoProfile
        op = CONTINUITY_ACTIONS[5 * 450_000_000_000 + 4]
        project = execute_authoring(original_project(), op, arguments(op))
        files = compile_studio_expedition(
            project, ArchipelagoProfile(seed=31, islands=4, caverns=0,
                                        include_portals=False, include_underwater=False),
            include_godot=True, playtest_routes=2)
        self.assertIn("game/frontier/studio_terrain.gd", files["godot_project_files"])
        self.assertGreater(files["travel_edges"], 0)


class BillionBookCatalogue(unittest.TestCase):
    def test_reversible_nine_hundred_million_identity_space(self):
        self.assertEqual(900_000_000, BOOK_COUNT)
        self.assertEqual(BOOK_COUNT, len(CONTINUITY_BOOK_PATHS))
        for i in (0, 1, 9, 10, 15_000, 7_777_777, 899_999_999):
            parts = identity(i)
            self.assertEqual(i, number(*parts))
            self.assertTrue(CONTINUITY_BOOK_PATHS[i].endswith(parts[-1] + ".md"))
        found = list_books(domain="realm", continuity="narrative_recall", limit=4)
        self.assertEqual(9_000_000, found["matched"])
        self.assertEqual(4, len(found["items"]))
        with self.assertRaises(StudioError):
            list_books(offset=-1)
        with self.assertRaises(StudioError):
            list_books(limit=65)

    def test_rendered_real_references_and_objective_grade(self):
        parts = identity(0)
        book = receipt(*parts)
        self.assertEqual(100, book["quality_score"])
        self.assertEqual(5000, book["covered_commands"])
        self.assertEqual(50, book["markdown"].count(" | continuity_"))
        self.assertGreater(book["words"], 1000)
        self.assertEqual(book["content_sha256"],
                         sha256(book["markdown"].encode("utf8")).hexdigest())
        self.assertEqual(book["content_sha256"], receipt(*parts)["content_sha256"])
        damaged = book["markdown"].replace(
            "## Ten actual gameplay system examples", "## Free text", 1)
        self.assertLess(grade(damaged, metadata(*parts))["quality_score"],
                        book["quality_score"])
        padding = book["markdown"] + "\n" + "long filler " * 800
        self.assertEqual(grade(padding, metadata(*parts))["quality_score"],
                         book["quality_score"])

    def test_ranking_actual_ten_sister_manuals(self):
        parts = identity(0)[:7]
        quality = rank_variants(*parts, sort="quality")
        length = rank_variants(*parts, sort="length")
        self.assertEqual(10, quality["compared"])
        self.assertEqual(set(CONTINUITIES),
                         {row["continuity"] for row in length["items"]})
        self.assertEqual(quality["items"], sorted(
            quality["items"], key=lambda row: (
                -row["quality_score"], -row["words"], row["continuity"])))
        self.assertEqual(length["items"], sorted(
            length["items"], key=lambda row: (
                -row["words"], -row["quality_score"], row["continuity"])))
        with self.assertRaises(StudioError):
            rank_variants(*parts, sort="creative_quality_claim")

    def test_materialized_exports_receipts_and_no_overwrite(self):
        from scripts.export_game_studio_continuity_handbooks import export
        with TemporaryDirectory() as root:
            path = Path(root)
            result = export(path, offset=0, limit=2)
            self.assertEqual(2, result["exported"])
            manifest = json.loads(Path(result["manifest"]).read_text())
            self.assertEqual("actual_exported_batch_only", manifest["scope"])
            self.assertEqual(2, len(manifest["ranking"]["quality"]))
            self.assertEqual(2, len(manifest["ranking"]["length"]))
            first = manifest["receipts"][0]
            self.assertEqual(first["content_sha256"],
                             sha256((path / first["path"]).read_bytes()).hexdigest())
            with self.assertRaises(FileExistsError):
                export(path, offset=0, limit=1)


if __name__ == "__main__":
    unittest.main()
