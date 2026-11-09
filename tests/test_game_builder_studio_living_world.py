"""End-to-end native studio now produces two different playable genres."""
from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stdout
import io

from skeleton.ai.game_builder.original_game_studio import (
    run_original_game_studio, StudioError, export_studio_run,
)
from skeleton.ai.game_builder.original_game_studio_cli import main
from skeleton.ai.game_builder.living_story_runtime import (
    original_story_world, StoryIntent, demonstrate_story, story_choices, story_step,
)
from skeleton.ai.game_builder.living_story_export import render_story_package
from skeleton.ai.game_builder.playable_world import GameBuildIntent


class TwoGenreStudioIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.intent = GameBuildIntent(
            project_id="dual-genre-npc-story-homebrew",
            title="Gardens Beyond the Old Path",
            subtitle="An original puzzle game and a living character-led RPG.",
            seed=204611, width=11, height=11, levels=1,
            collectibles_per_level=1, hazards_per_level=1,
            theme="forest", starting_health=4,
        )

    def test_native_studio_two_actual_genres_with_distinct_mirror_proofs(self):
        run = run_original_game_studio(
            self.intent, authorized=True,
            narrative_population=64, narrative_regions=9,
            narrative_mode="postgame", narrative_quests=3,
            narrative_ending="discovery", mirror_attempts=128,
            companion_practice_games=2,
        )
        self.assertTrue(run.mirror.passed)
        self.assertIsNotNone(run.narrative)
        self.assertTrue(run.narrative_mirror.passed)
        self.assertEqual(len(run.narrative_mirror.probes), 128)
        self.assertEqual(run.narrative.manifest["npc_count"], 64)
        self.assertEqual(run.narrative.manifest["regions"], 9)
        self.assertEqual(run.narrative.manifest["mode"], "postgame")
        self.assertEqual(run.narrative.manifest["ending"], "discovery")
        self.assertIn("living_story/index.html", run.package.files)
        self.assertIn("living_story/godot/scripts/main.gd", run.package.files)
        self.assertIn("living_story/godot/proof.json", run.package.files)
        self.assertIn("living_story/release.json", run.package.files)
        self.assertIn("studio/living_story_mirror.json", run.package.files)
        self.assertIn("studio/living_story_almanac.json", run.package.files)
        almanac = json.loads(run.package.files["studio/living_story_almanac.json"])
        self.assertEqual(almanac["NPC_count"], 64)
        self.assertEqual(almanac["world_mode"], "postgame")
        self.assertFalse(almanac["human_playtested"])
        self.assertFalse(almanac["externally_trained_model"])
        trace = json.loads(run.package.files["studio/executed_tool_receipts.json"])
        names = [r["tool_id"] for r in trace["receipts"]]
        self.assertEqual(
            [x for x in names if x.startswith("story.")],
            ["story.generate", "story.simulate", "story.native", "story.mirror"],
        )
        self.assertEqual(trace["living_story_package_digest"], run.narrative.digest)
        self.assertEqual(trace["living_story_mirror_digest"], run.narrative_mirror.digest)
        self.assertNotEqual(
            run.narrative.manifest["world_digest"],
            run.project.world.digest,
        )
        self.assertIn("release-blocked", run.consumer.to_payload()["status"])
        self.assertFalse(run.consumer.platform_hardware_tested)
        self.assertEqual(run.digest, run_original_game_studio(
            self.intent, authorized=True,
            narrative_population=64, narrative_regions=9,
            narrative_mode="postgame", narrative_quests=3,
            narrative_ending="discovery", mirror_attempts=128,
            companion_practice_games=2,
        ).digest)

    def test_open_world_modes_and_reachability_from_real_player_actions(self):
        for mode in ("sandbox", "postgame", "campaign"):
            run = run_original_game_studio(
                self.intent, authorized=True, mirror_attempts=64,
                companion_practice_games=0, narrative_population=12,
                narrative_regions=6, narrative_mode=mode,
            )
            self.assertEqual(run.narrative.manifest["mode"], mode)
            self.assertTrue(run.narrative_mirror.passed)
            self.assertEqual(len(run.narrative_mirror.probes), 128)
            data = json.loads(run.package.files["living_story/proof.json"])
            self.assertEqual(data["final"]["status"], {
                "campaign": "won", "postgame": "epilogue", "sandbox": "open",
            }[mode])
            self.assertEqual(len(data["actions"]), data["final"]["turn"])
            self.assertEqual(len(
                json.loads(run.package.files["living_story/world.json"])["citizens"]
            ), 12)
            self.assertNotIn("living_story/imported-proprietary-sprites.png", run.package.files)

    def test_cli_exports_actual_story_browser_native_and_reviews(self):
        with tempfile.TemporaryDirectory() as temp:
            intent_file = Path(temp) / "intent.json"
            intent_file.write_text(json.dumps(self.intent.to_payload()), encoding="utf-8")
            out = Path(temp) / "studio"
            cmd = [
                "--intent", str(intent_file), "--output", str(out),
                "--living-world-npcs", "20", "--living-world-regions", "7",
                "--living-world-mode", "postgame", "--living-world-quests", "2",
                "--living-world-ending", "independence",
                "--mirror-attempts", "64", "--companion-practice", "1",
                "--trusted-local-operator",
            ]
            output = io.StringIO()
            with redirect_stdout(output):
                self.assertEqual(main(cmd), 0)
            response = json.loads(output.getvalue())
            self.assertEqual(response["living_world_npcs"], 20)
            self.assertEqual(response["living_world_mirror_attacks"], 128)
            self.assertEqual(len(response["living_world_manifest_digest"]), 64)
            self.assertTrue((out / "living_story/index.html").is_file())
            self.assertTrue((out / "living_story/godot/project.godot").is_file())
            self.assertTrue((out / "living_story/godot/proof.json").is_file())
            self.assertTrue((out / "studio/living_story_mirror.json").is_file())
            self.assertEqual(json.loads((out / "living_story/proof.json").read_text())[
                "final"]["ending"], "independence")
            self.assertFalse(response["publication_authorized"])

    def test_no_implicit_rpg_work_and_bounded_authorization(self):
        baseline = run_original_game_studio(
            self.intent, authorized=True, companion_practice_games=0,
            mirror_attempts=64)
        self.assertIsNone(baseline.narrative)
        self.assertNotIn("living_story/index.html", baseline.package.files)
        with self.assertRaises(StudioError):
            run_original_game_studio(self.intent, authorized=True,
                narrative_population=129)
        with self.assertRaises(StudioError):
            run_original_game_studio(self.intent, authorized=True,
                narrative_regions=11, narrative_population=0)
        with self.assertRaises(StudioError):
            run_original_game_studio(self.intent, authorized=True,
                narrative_population=12, narrative_mode="nonexistent")
        with self.assertRaises(StudioError):
            run_original_game_studio(self.intent, authorized=True,
                narrative_population=12, narrative_quests=4)
        with self.assertRaises(PermissionError):
            run_original_game_studio(self.intent, authorized=False,
                narrative_population=12)


if __name__ == "__main__":
    unittest.main()
