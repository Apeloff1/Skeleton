"""Full modular original game consumer source, open-source authoring and proofs."""
from __future__ import annotations

from contextlib import redirect_stdout
from dataclasses import replace
import io
import json
from pathlib import Path
import tempfile
import unittest

from skeleton.ai.game_builder.quest_scene_forge import forge_director
from skeleton.ai.game_builder.director_evolution_product import build_evolution_product
from skeleton.ai.game_builder.quest_director_export import export_director_studio
from skeleton.ai.game_builder.quest_director_cli import main as build_cli
from skeleton.ai.game_builder.quest_scene_engine import DirectorError


class EvolutionProductTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.world=forge_director(
            "original_evolution_product",seed=6719,
            regions=tuple(f"land_{i:02d}" for i in range(8)),
            quest_types=("main_story","escort_leash","investigation","profession"),
            stages=2,main_goal="Protect the living archipelago while retaining freedom.",
        )

    def test_integrated_original_consumer_product_contains_real_mechanics(self):
        result=build_evolution_product(
            self.world,population=48,tier="handheld",
            deep_route_search=True,mirror_attempts=64,authorized=True,
        )
        self.assertEqual(result.manifest["society_population"],48)
        self.assertEqual(result.manifest["target_tier"],"handheld")
        self.assertTrue(result.manifest["deep_route_search"])
        self.assertTrue(result.mirror.passed)
        self.assertIn("systems/npc_society_replay.json",result.files)
        self.assertIn("systems/npc_economy.json",result.files)
        self.assertIn("systems/npc_social_propagation.json",result.files)
        self.assertIn("systems/modular_missions.json",result.files)
        self.assertIn("systems/capability_graph.json",result.files)
        self.assertIn("systems/quest_routes.json",result.files)
        self.assertIn("game/earned_story_endings.json",result.files)
        self.assertIn("index.html",result.files)
        proof=json.loads(result.files["systems/npc_society_replay.json"])
        self.assertEqual(proof["performance"]["population"],48)
        self.assertEqual(proof["performance"]["quest_stages_completed"],2)
        self.assertGreater(proof["performance"]["observed_memory_count"],0)
        planned=json.loads(result.files["systems/quest_routes.json"])
        self.assertTrue(planned["routes"])
        self.assertGreaterEqual(len(planned["methods_explored"]),2)
        self.assertFalse(result.manifest["consumer_publication_authorized"])
        receipt=result.receipt()
        self.assertFalse(receipt["native_executable"])
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"original-world"
            export_director_studio(result,path,authorized=True)
            self.assertTrue((path/"index.html").exists())
            self.assertTrue((path/"systems/npc_society_replay.json").exists())
            self.assertEqual(json.loads((path/"release.json").read_text())["manifest_digest"],
                             result.digest)

    def test_reproducible_deterministic_output_and_unsupported_rights(self):
        first=build_evolution_product(
            self.world,population=24,tier="mobile",
            deep_route_search=False,mirror_attempts=64,authorized=True,
        )
        second=build_evolution_product(
            self.world,population=24,tier="mobile",
            deep_route_search=False,mirror_attempts=64,authorized=True,
        )
        self.assertEqual(first.digest,second.digest)
        self.assertEqual(first.files,second.files)
        routes=json.loads(first.files["systems/quest_routes.json"])
        self.assertEqual(routes["reason"],"explicitly_disabled_by_operator")
        with self.assertRaises(PermissionError):
            build_evolution_product(self.world,authorized=False)
        with self.assertRaises(DirectorError):
            build_evolution_product(self.world,population=1024,authorized=True)

    def test_full_editor_to_product_cli_keeps_original_scenes(self):
        with tempfile.TemporaryDirectory() as folder:
            blueprint=Path(folder)/"full-scene-blueprint.json"
            with redirect_stdout(io.StringIO()):
                self.assertEqual(build_cli([
                    "--mode","template","--output",str(blueprint),
                    "--project","evolved_original_game","--regions","8",
                    "--stages","2","--genres","main_story,investigation,escort_path",
                    "--trusted-local-operator",
                ]),0)
            doc=json.loads(blueprint.read_text())
            doc["scenes"][0]["camera"]="original close cinematic tracking"
            doc["scenes"][0]["lighting"]="moss lantern glow"
            doc["quests"][0]["premise"]="Reconcile all original peoples through evidence."
            blueprint.write_text(json.dumps(doc),encoding="utf-8")
            product=Path(folder)/"game"
            output=io.StringIO()
            with redirect_stdout(output):
                self.assertEqual(build_cli([
                    "--mode","build","--blueprint",str(blueprint),
                    "--human-reviewed","--trusted-local-operator",
                    "--evolve","--society-npcs","32",
                    "--target-tier","mobile","--no-deep-search",
                    "--mirror-attempts","64","--output",str(product),
                ]),0)
            receipt=json.loads(output.getvalue())
            self.assertTrue(receipt["playable"])
            self.assertFalse(receipt["commercial_publication_approved"])
            release=json.loads((product/"release.json").read_text())
            self.assertEqual(release["society_population"],32)
            authored=json.loads((product/"game/world.json").read_text())
            self.assertEqual(authored["scenes"][0]["camera"],
                             "original close cinematic tracking")
            self.assertEqual(authored["scenes"][0]["lighting"],
                             "moss lantern glow")


if __name__=="__main__":
    unittest.main()
