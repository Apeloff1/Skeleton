"""Specialized regression suite for the live Director bridge and Dragon lab.

Run: python -m unittest tests.test_jeeves_director_live_bridge
"""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from skeleton.ai.game_builder.quest_scene_forge import forge_director
from skeleton.developer.game_cli import SCHEMA as WORKSPACE_SCHEMA
from skeleton.developer.jeeves_game_director_session import begin, choose, inspect
from skeleton.developer.jeeves_game_director_atlas import export, verify
from skeleton.developer.jeeves_game_dragon_lab import queue as dragon_lab
from skeleton.developer.jeeves_game_director_coverage import coverage
from skeleton.developer.jeeves_game_director_godot_smoke import smoke
from skeleton.developer.jeeves_game_director_events import delta
from skeleton.developer.jeeves_game_production_board import _load_world
from skeleton.ai.game_builder.quest_campaign_completion import play_campaign


class DirectorBridgeIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "original_game"
        self.root.mkdir()
        (self.root / "design").mkdir()
        (self.root / "skeleton.game.json").write_text(json.dumps({
            "schema": WORKSPACE_SCHEMA, "name": "original_game",
            "vision": "An original exploration game",
            "era": "extraction_now", "archetype": "auto",
        }))
        world = forge_director(
            "original_game", seed=21,
            regions=("harbor", "market", "tower", "ruins"),
            quest_types=("main_story", "investigation"), stages=2,
        )
        self.source = "design/director_campaign_source.json"
        (self.root / self.source).write_text(json.dumps({
            "schema": "skeleton.jeeves.director_campaign_source.v1",
            "author_review_acknowledged": True,
            "director_world": world.payload(),
        }))
        begin(self.root, source=self.source, session="primary")

    def test_persisted_state_is_optimistically_checked(self):
        current = inspect(self.root, session="primary")
        step = choose(self.root, session="primary", choice="wait:wait",
                      expected_sequence=current["sequence"],
                      expected_state_sha256=current["current_state_sha256"])
        self.assertEqual(step["sequence"], 1)
        with self.assertRaises(ValueError):
            choose(self.root, session="primary", choice="wait:wait",
                   expected_sequence=current["sequence"],
                   expected_state_sha256=current["current_state_sha256"])
        self.assertEqual(inspect(self.root, session="primary")["sequence"], 1)

    def test_godot_player_source_is_integrity_bound(self):
        result = export(self.root, source=self.source)
        folder = Path(result["path"])
        script = (folder / "director_player.gd").read_text()
        self.assertIn("/v1/actions", script)
        self.assertIn("expected_state_sha256", script)
        self.assertTrue((folder / "director_player.tscn").is_file())
        self.assertTrue(verify(self.root, source=self.source)["source_manifest_verified"])
        self.assertFalse(result["manifest"]["native_binary_executed"])

    def test_complete_director_logic_replay_emits_signed_stage_events(self):
        world, _ = _load_world(self.root, self.source)
        witness = play_campaign(world, preference=0)
        emitted = 0
        timeline_count = 0
        for segment in witness.replay["segments"]:
            for action in segment["actions"]:
                before = inspect(self.root, session="primary")
                after = choose(
                    self.root, session="primary",
                    choice=action["kind"] + ":" + action["key"],
                    expected_sequence=before["sequence"],
                    expected_state_sha256=before["current_state_sha256"],
                )
                presentation = delta(self.root, session="primary",
                                     before=before, after=after)
                self.assertEqual(presentation["state_sha256"],
                                 after["current_state_sha256"])
                emitted += len(presentation["new_story_results"])
                timeline_count += presentation["triggered_timelines"]
        final = inspect(self.root, session="primary")
        self.assertTrue(final["complete"])
        self.assertEqual(emitted, 4)
        self.assertGreater(timeline_count, 0)
        self.assertEqual(len(final["quest_stage_results"]), 4)
        self.assertFalse(presentation["native_cinematic_rendering_verified"])
        with self.assertRaises(ValueError):
            delta(self.root, session="primary", before=before, after=before)

    def test_godot_smoke_requires_real_binary_and_tracks_phases(self):
        export(self.root, source=self.source)
        with patch("skeleton.forge.playtest.resolve_binary",
                   return_value=(None, "absent", False)):
            report = smoke(self.root, source=self.source)
        self.assertFalse(report["ok"])
        self.assertFalse(report["native_gameplay_verified"])
        simulated = [{"executed": True, "exit_code": 0, "passed": True,
                      "stdout_tail": "4.4.stable", "stderr_tail": ""}]
        simulated.extend([{"executed": True, "exit_code": 0, "passed": True,
                           "stdout_tail": "", "stderr_tail": ""} for _ in range(3)])
        with patch("skeleton.forge.playtest.resolve_binary",
                   return_value=("/bin/godot", "test-stub", False)):
            with patch("skeleton.developer.jeeves_game_director_godot_smoke._execute",
                       side_effect=simulated) as execute:
                result = smoke(self.root, source=self.source)
        self.assertEqual(execute.call_count, 4)
        self.assertTrue(result["source_import_and_two_scenes_started"])
        self.assertFalse(result["native_gameplay_verified"])

    def test_comparative_learning_requires_same_verified_world(self):
        begin(self.root, source=self.source, session="alternate")
        choose(self.root, session="primary", choice="wait:wait")
        alternate = inspect(self.root, session="alternate")
        travel = next(a["choice"] for a in alternate["actions"] if a["kind"] == "travel")
        choose(self.root, session="alternate", choice=travel)
        result = dragon_lab(self.root, sessions="primary,alternate")
        self.assertEqual(result["study"]["session_count"], 2)
        self.assertFalse(result["study"]["model_weight_update_performed"])
        with self.assertRaises(ValueError):
            dragon_lab(self.root, sessions="primary,primary")
        with self.assertRaises(ValueError):
            dragon_lab(self.root, sessions="primary,alternate",
                       approved_sha256="0" * 64)

    def test_campaign_coverage_exposes_unverified_native_execution(self):
        result = coverage(self.root, source=self.source, routes=3)
        self.assertEqual(result["selected_replay_strategies"], 6)
        self.assertEqual(len(result["stage_approach_coverage"]), 4)
        self.assertFalse(result["native_scene_playthrough_verified"])


if __name__ == "__main__":
    unittest.main()
