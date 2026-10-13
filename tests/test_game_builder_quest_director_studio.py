"""Release-quality original scene director and alternate quest proof integration."""
from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import tempfile
from contextlib import redirect_stdout
import io
import unittest

from skeleton.ai.game_builder.quest_scene_forge import (
    forge_director, compile_director_blueprint,
)
from skeleton.ai.game_builder.quest_director_solver import (
    solve_quest, compare_solution_routes,
)
from skeleton.ai.game_builder.quest_director_studio import build_director_studio
from skeleton.ai.game_builder.quest_director_export import export_director_studio
from skeleton.ai.game_builder.quest_scene_mirror import review_director
from skeleton.ai.game_builder.quest_director_cli import main as director_cli
from skeleton.ai.game_builder.quest_scene_engine import DirectorError


class FullDirectorProductionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.world = forge_director(
            "production_scene_workshop", seed=45710,
            regions=tuple(f"region_{i:02d}" for i in range(16)),
            quest_types=(
                "main_story", "escort_path", "escort_leash",
                "escort_introduction", "dungeoneering", "infusion",
                "proficiency", "attunement", "profession", "rival_story",
                "timed_combat", "survival_waves", "reinforcement",
                "regional_story", "courier", "acquisition",
            ), stages=3, main_goal="Restore the great library while keeping every community independent.",
        )

    def test_full_quest_witnesses_solve_arcs_without_rigid_single_solution(self):
        for strategy in ("ordinary", "creative", "fast"):
            with self.subTest(strategy=strategy):
                witness = solve_quest(self.world, "quest_00",
                                      strategy=strategy, authorized=True)
                self.assertTrue(witness.completed)
                self.assertEqual(len(witness.expected_results), 3)
                self.assertIn("quest_00", witness.replay.final.complete)
                self.assertGreater(witness.score, 300)
                self.assertEqual(len(witness.replay.actions), witness.steps)
        baseline = solve_quest(self.world, "quest_00",
                               strategy="creative", authorized=True)
        enhanced = solve_quest(self.world, "quest_00", strategy="creative",
                               optional=True, authorized=True)
        self.assertEqual(len(enhanced.replay.final.results), 3)
        self.assertTrue(all(r.optional_bonus == 15 for r in
                            enhanced.replay.final.results if r.quest == "quest_00"))
        self.assertGreater(enhanced.score, baseline.score)
        comparisons = compare_solution_routes(
            self.world, "quest_00", authorized=True)
        self.assertTrue(comparisons["different_paths_proven"])
        self.assertEqual(len(comparisons["solutions"]), 3)
        self.assertNotEqual(comparisons["solutions"]["ordinary"]["replay_digest"],
                            comparisons["solutions"]["creative"]["replay_digest"])
        with self.assertRaises(PermissionError):
            solve_quest(self.world, "quest_00", authorized=False)

    def test_real_adversarial_source_and_stage_evidence(self):
        source = build_director_studio(self.world, authorized=True)
        self.assertEqual(source.manifest["scene_count"], 16)
        self.assertEqual(source.manifest["quest_count"], 16)
        self.assertEqual(source.manifest["cutscene_count"], 48)
        self.assertTrue(source.mirror.passed)
        self.assertEqual(len(source.mirror.probes), 128)
        self.assertEqual(len({p.family for p in source.mirror.probes}), 12)
        self.assertFalse(source.receipt()["native_executable"])
        self.assertFalse(source.receipt()["commercial_publication_approved"])
        self.assertIn("index.html", source.files)
        self.assertIn("editor/complete_scene_blueprint.json", source.files)
        self.assertIn("game/alternative_solutions.json", source.files)
        evidence = json.loads(source.files["almanac/observations.json"])
        self.assertEqual(evidence["quest_stage_count"] if "quest_stage_count" in evidence
                         else evidence["stage_count"], 48)
        self.assertEqual(evidence["cutscene_cue_count"], 48 * 5)
        self.assertFalse(evidence["trained_weights"])
        self.assertEqual(source.digest,
                         build_director_studio(self.world, authorized=True).digest)

    def test_atomic_export_and_strict_anti_tamper(self):
        product = build_director_studio(self.world, authorized=True,
                                        mirror_attempts=64)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "new-original-game"
            with self.assertRaises(PermissionError):
                export_director_studio(product, path, authorized=False)
            self.assertFalse(path.exists())
            self.assertEqual(export_director_studio(
                product, path, authorized=True), path)
            self.assertTrue((path / "index.html").is_file())
            self.assertTrue((path / "editor/complete_scene_blueprint.json").is_file())
            self.assertTrue((path / "review/consumer_gate.json").is_file())
            self.assertEqual(json.loads((path / "release.json").read_text())["manifest_digest"],
                             product.digest)
            with self.assertRaises(DirectorError):
                export_director_studio(product, path, authorized=True)
            modified = replace(product, files={
                **product.files, "index.html": b"changed browser game",
            })
            with self.assertRaises(DirectorError):
                export_director_studio(modified, Path(folder) / "bad-game",
                                       authorized=True)

    def test_cli_generates_editable_all_scene_blueprint_then_consumer_preview(self):
        with tempfile.TemporaryDirectory() as folder:
            blueprint = Path(folder) / "complete-original-scenes.json"
            command = [
                "--mode", "template", "--project", "new_original_quest_game",
                "--regions", "8", "--stages", "2",
                "--genres", "main_story,escort_path,rival_story,investigation",
                "--trusted-local-operator", "--output", str(blueprint),
            ]
            with redirect_stdout(io.StringIO()):
                self.assertEqual(director_cli(command), 0)
            doc = json.loads(blueprint.read_text())
            self.assertEqual(len(doc["scenes"]), 8)
            self.assertEqual(len(doc["quests"]), 4)
            doc["scenes"][0]["title"] = "Player authored spaceport station"
            doc["scenes"][0]["lighting"] = "soft comet light"
            scene = next(s for s in doc["scenes"] if s["cutscenes"])
            scene["cutscenes"][0]["cues"][0]["value"] = "new original camera dolly"
            blueprint.write_text(json.dumps(doc), encoding="utf-8")
            destination = Path(folder) / "preview-product"
            output = io.StringIO()
            with redirect_stdout(output):
                self.assertEqual(director_cli([
                    "--mode", "build", "--blueprint", str(blueprint),
                    "--human-reviewed", "--trusted-local-operator",
                    "--output", str(destination),
                ]), 0)
            receipt = json.loads(output.getvalue())
            self.assertTrue(receipt["playable"])
            self.assertEqual(receipt["authored_scene_count"], 8)
            self.assertEqual(receipt["quest_count"], 4)
            world = json.loads((destination / "game/world.json").read_text())
            self.assertEqual(world["scenes"][0]["title"], "Player authored spaceport station")
            self.assertEqual(world["scenes"][0]["lighting"], "soft comet light")
            self.assertTrue((destination / "index.html").is_file())
            self.assertFalse(receipt["commercial_publication_approved"])

    def test_no_implicit_permissions_or_false_native_claims(self):
        with self.assertRaises(PermissionError):
            build_director_studio(self.world, authorized=False)
        with self.assertRaises(DirectorError):
            build_director_studio(self.world, authorized=True, mirror_attempts=12)
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "unapproved"
            self.assertEqual(director_cli([
                "--mode", "build", "--output", str(output),
            ]), 2)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
