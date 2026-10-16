"""Focused Director campaign production / Dragon feedback regressions.

Specialized: python -m unittest tests.test_jeeves_director_production
Not a repo-wide merge or install gate.
"""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from skeleton.developer.game_cli import SCHEMA as WORKSPACE_SCHEMA
from skeleton.developer.jeeves_game_director_factory import draft, examine, promote
from skeleton.developer.jeeves_game_production_board import board, prepare_dragon_research
from skeleton.developer.jeeves_game_direction_cli import campaign, reopen_campaign


class DirectorMilestoneTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "original_game"
        self.root.mkdir()
        (self.root / "design").mkdir()
        self.config = {
            "schema": WORKSPACE_SCHEMA,
            "name": "original_game",
            "vision": "Restore the floating city without losing its history",
            "era": "extraction_now", "archetype": "auto",
        }
        (self.root / "skeleton.game.json").write_text(json.dumps(self.config))

    def _draft(self) -> dict:
        return draft(self.root, seed=19,
                     regions="harbor,observatory,market,catacombs",
                     quest_types="main_story,investigation,crafting",
                     stages=3, goal="Restore the floating city")

    def _promote(self) -> dict:
        candidate = self._draft()
        inspected = examine(self.root, source=candidate["source"], routes=3)
        self.assertTrue(inspected["all_routes_completed"])
        self.assertGreater(inspected["distinct_outcome_stage_count"], 0)
        return promote(self.root, source=candidate["source"],
                       approved_digest=candidate["candidate_sha256"], routes=3)

    def test_complete_simulated_campaign_and_reopen(self) -> None:
        published = self._promote()
        self.assertTrue(published["eligible_for_canonical_logic_replay"])
        self.assertFalse(published["real_native_game_verified"])
        report = campaign(self.root, source="design/director_campaign_source.json",
                          routes=3, save_prefix="new_game_run")
        self.assertTrue(report["all_routes_completed"])
        self.assertTrue(report["branch_outcomes_materially_distinct"])
        self.assertEqual(len(report["saved_campaigns"]), 3)
        restored = reopen_campaign(
            self.root, source="design/director_campaign_source.json",
            save_name="new_game_run_0")
        self.assertTrue(restored["ok"])
        self.assertFalse(restored["installed_game_recovery_qualified"])

    def test_workboard_tracks_scenes_and_real_logic_replays(self) -> None:
        self._promote()
        report = board(self.root, source="design/director_campaign_source.json",
                       routes=3)
        self.assertTrue(report["logic_campaign"]["all_stages_replayed"])
        self.assertEqual(len(report["scene_workorders"]), 4)
        self.assertEqual(len(report["quest_stage_workorders"]), 9)
        self.assertTrue(report["logic_campaign"]["branch_outcomes_materially_distinct"])
        self.assertFalse(report["independent_game_completion_verified"])
        self.assertTrue(all(not x["native_engine_played"] for x in
                            report["quest_stage_workorders"]))

    def test_dragon_replay_intake_is_explicit_and_not_training(self) -> None:
        self._promote()
        source = "design/director_campaign_source.json"
        preview = prepare_dragon_research(self.root, source=source, routes=3)
        self.assertFalse(preview["persisted"])
        self.assertFalse(preview["training_performed"])
        self.assertIsNone(preview["candidate"]["recorded_player_preference"])
        with self.assertRaises(ValueError):
            prepare_dragon_research(self.root, source=source, routes=3,
                                    approve="0" * 64)
        saved = prepare_dragon_research(self.root, source=source, routes=3,
                                       approve=preview["candidate_sha256"])
        self.assertTrue(saved["persisted"])
        self.assertTrue(Path(saved["path"]).is_file())
        self.assertFalse(json.loads(Path(saved["path"]).read_text())["model_weights_modified"])
        with self.assertRaises(ValueError):
            prepare_dragon_research(self.root, source=source, routes=3,
                                    approve=preview["candidate_sha256"])

    def test_reject_unapproved_or_modified_candidates(self) -> None:
        candidate = self._draft()
        with self.assertRaises(ValueError):
            promote(self.root, source=candidate["source"],
                    approved_digest="0" * 64)
        raw = self.root / candidate["source"]
        altered = json.loads(raw.read_text())
        altered["director_world"]["bible"]["invariant_goal"] = "Different goal"
        raw.write_text(json.dumps(altered))
        with self.assertRaises(ValueError):
            examine(self.root, source=candidate["source"])

    def test_configuration_drift_cannot_pass_review(self) -> None:
        candidate = self._draft()
        self.config["vision"] = "New incompatible canonical world"
        (self.root / "skeleton.game.json").write_text(json.dumps(self.config))
        with self.assertRaises(ValueError):
            examine(self.root, source=candidate["source"])

    def test_no_overwrite_and_invalid_inputs(self) -> None:
        self._draft()
        with self.assertRaises(ValueError):
            self._draft()
        with self.assertRaises(ValueError):
            draft(self.root, seed=2, regions="../private,market,harbor,ruins",
                  quest_types="main_story", stages=3)
        with self.assertRaises(ValueError):
            draft(self.root, seed=2, regions="harbor,market,harbor,ruins",
                  quest_types="main_story", stages=3)
        with self.assertRaises(ValueError):
            draft(self.root, seed=2, regions="harbor,market,cliffs,ruins",
                  quest_types="combat,main_story", stages=3)
        with self.assertRaises(ValueError):
            examine(self.root, source="design/no_such_file.json")

    def test_unsupported_flag_is_not_silently_ignored(self) -> None:
        from skeleton.developer.game_cli import run_game_cli
        response = run_game_cli([
            "jeeves", "director-draft", "--project", str(self.root),
            "--seed", "4", "--regions", "north,east,south,west",
            "--quest-types", "main_story", "--kind", "asset",
        ])
        self.assertFalse(response["ok"])


if __name__ == "__main__":
    unittest.main()
