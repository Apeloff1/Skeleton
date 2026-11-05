"""Quest progress round-trips through GameSavePlane, pinned to Director digests."""
from __future__ import annotations

from dataclasses import replace
import unittest

from skeleton.ai.game_builder.quest_fail_states import QuestFailure
from skeleton.ai.game_builder.quest_objectives import TypedObjective, objective_progress, quest_progress
from skeleton.ai.game_builder.quest_progress_save import (
    SECTION, QuestProgressSaveError, quest_section, restore_quest_progress, save_quest_progress,
)
from skeleton.ai.game_builder.quest_scene_engine import director_initial
from skeleton.ai.game_builder.quest_scene_forge import forge_director
from skeleton.kernel.game_save_plane import GameSavePlane


def world(seed=10817):
    return forge_director("scene_rpg", seed=seed,
                          regions=tuple(f"region_{i:02d}" for i in range(12)),
                          quest_types=("main_story", "combat"), stages=2)


class QuestSaveTests(unittest.TestCase):
    def setUp(self):
        self.w = world()
        st = director_initial(self.w)
        self.state = replace(st, records=(("q1", "s", "fight:wolf", 2),))
        objs = [TypedObjective("kill", "wolf", 3)]
        self.prog = quest_progress("q1", objective_progress(self.state, "q1", "s", objs))
        self.section = quest_section(self.w, self.state, [self.prog],
                                     failures=[QuestFailure("q2", "turn_limit", "late")],
                                     campaign_receipt_sha256="ab" * 32)

    def test_round_trip_with_other_sections(self):
        plane = GameSavePlane()
        save_quest_progress(plane, "slot1", 1, self.section, other_sections={"player": {"hp": 3}})
        sections, _ = plane.restore("slot1")
        self.assertEqual(sections["player"], {"hp": 3})
        self.assertEqual(sections[SECTION]["final_state_sha256"], self.state.digest)
        got = restore_quest_progress(plane, "slot1", self.w, verified_state=self.state,
                                     campaign_receipt_sha256="ab" * 32)
        self.assertEqual(got, {"q1": self.prog})
        self.assertEqual(got["q1"].objectives["0"].current, 2)

    def test_restore_requires_trusted_state_or_campaign_receipt(self):
        plane = GameSavePlane()
        save_quest_progress(plane, "s", 1, self.section)
        with self.assertRaisesRegex(QuestProgressSaveError, "requires verified"):
            restore_quest_progress(plane, "s", self.w)
        with self.assertRaisesRegex(QuestProgressSaveError, "invalid campaign receipt"):
            restore_quest_progress(plane, "s", self.w, campaign_receipt_sha256="not-a-digest")
        restored = restore_quest_progress(plane, "s", self.w, verified_state=self.state)
        self.assertEqual(restored, {"q1": self.prog})
        self.assertEqual(
            restore_quest_progress(plane, "s", self.w, campaign_receipt_sha256="ab" * 32),
            {"q1": self.prog},
        )

    def test_restore_rejects_cross_project_section(self):
        plane = GameSavePlane()
        malicious = dict(self.section, project="different-project")
        save_quest_progress(plane, "s", 1, malicious)
        with self.assertRaisesRegex(QuestProgressSaveError, "another project"):
            restore_quest_progress(plane, "s", self.w, verified_state=self.state)

    def test_restore_rejects_forged_objective_progress(self):
        plane = GameSavePlane()
        forged = dict(self.section, quests={"q1": {
            "quest_id": "q1", "status": "completed",
            "objectives_progress": {"0": {"current": 0, "target": 3, "completed": True}},
        }})
        save_quest_progress(plane, "forged", 1, forged)
        with self.assertRaisesRegex(QuestProgressSaveError, "objective progress counters"):
            restore_quest_progress(plane, "forged", self.w, verified_state=self.state)
        forged["quests"]["q1"]["objectives_progress"]["0"]["completed"] = False
        with self.assertRaisesRegex(QuestProgressSaveError, "status disagrees"):
            save_quest_progress(plane, "forged2", 1, forged)
            restore_quest_progress(plane, "forged2", self.w, verified_state=self.state)

    def test_rejects_mismatched_state_world_or_receipt(self):
        plane = GameSavePlane()
        save_quest_progress(plane, "s", 1, self.section)
        moved = replace(self.state, turn=self.state.turn + 1)
        with self.assertRaises(QuestProgressSaveError):
            restore_quest_progress(plane, "s", self.w, verified_state=moved)
        with self.assertRaises(QuestProgressSaveError):
            restore_quest_progress(plane, "s", world(seed=7))
        with self.assertRaises(QuestProgressSaveError):
            restore_quest_progress(plane, "s", self.w, campaign_receipt_sha256="cd" * 32)
        with self.assertRaises(QuestProgressSaveError):
            save_quest_progress(plane, "s", 2, self.section, other_sections={SECTION: {}})
        with self.assertRaises(QuestProgressSaveError):
            quest_section(world(seed=7), self.state, [])


if __name__ == "__main__":
    unittest.main()
