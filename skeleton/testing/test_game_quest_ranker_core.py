"""Behavior contracts for fail-closed checkpoint-bound quest graph ranking.

Does not require a model artifact or run training. Runtime adapter evaluation is
available separately through explicit checkpoint and adapter paths.
"""
from __future__ import annotations

import unittest

from skeleton.ai.game_builder.quest_graph_ranker_core import check_quest_graph

QUICK = {
    "difficulty": "quick",
    "min_steps": 3,
    "max_steps": 8,
    "max_edges": 11,
    "biome": "moss ruins",
    "goal": "rescue a scout",
}
GOOD = {
    (0, 1), (0, 4), (4, 1), (1, 2), (2, 3),
    (4, 5), (5, 1), (1, 6), (6, 2),
}


class QuestRankerSafetyTests(unittest.TestCase):
    def test_good_key_gate_graph(self) -> None:
        proof = check_quest_graph(QUICK, GOOD)
        self.assertTrue(proof["accepted"], proof)
        self.assertEqual(proof["shortest_win_steps"], 3)

    def test_direct_goal_bypass_rejected(self) -> None:
        proof = check_quest_graph(QUICK, GOOD | {(0, 3)})
        self.assertFalse(proof["accepted"])
        self.assertFalse(proof["checks"]["gate_required"])

    def test_key_held_goal_bypass_rejected(self) -> None:
        proof = check_quest_graph(QUICK, GOOD | {(1, 3)})
        self.assertFalse(proof["accepted"])
        self.assertFalse(proof["checks"]["gate_required"])

    def test_unreachable_authored_room_rejected(self) -> None:
        proof = check_quest_graph(QUICK, GOOD - {(1, 6)})
        self.assertFalse(proof["accepted"])
        self.assertFalse(proof["checks"]["all_authored_rooms_reachable"])

    def test_dead_end_and_missing_goal_rejected(self) -> None:
        proof = check_quest_graph(QUICK, GOOD - {(2, 3)})
        self.assertFalse(proof["accepted"])
        self.assertFalse(proof["checks"]["reachable"])

    def test_resource_budget_rejected(self) -> None:
        task = dict(QUICK, max_edges=8)
        proof = check_quest_graph(task, GOOD)
        self.assertFalse(proof["accepted"])
        self.assertFalse(proof["checks"]["resource_budget"])

    def test_bad_graph_node_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "integer"):
            check_quest_graph(QUICK, GOOD | {(8, 3)})


if __name__ == "__main__":
    unittest.main()
