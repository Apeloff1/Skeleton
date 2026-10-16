"""Real, deterministic >256-frame platformer replay acceptance."""
from __future__ import annotations

import unittest

from skeleton.ai.runtime.gameplay_capabilities import GameplayError, platformer_replay
from skeleton.ai.runtime.gameplay_long_replay import MAX_LONG_REPLAY_FRAMES, replay_long_controller

TILES = ["########", "#S.G...#", "########", "########", "########"]
NEUTRAL = {"left": False, "right": False, "jump": False}
RIGHT = {"left": False, "right": True, "jump": False}
START = {"x": 1, "y": 1, "vx": 0, "vy": 0}


class LongControllerReplayTests(unittest.TestCase):
    def test_real_winning_goal_occurs_after_frame_256(self):
        controls = [dict(NEUTRAL) for _ in range(318)] + [dict(RIGHT), dict(RIGHT)]
        first = replay_long_controller({"tiles": TILES, "avatar": START, "controls": controls})
        second = replay_long_controller({"tiles": TILES, "avatar": START, "controls": controls})
        self.assertEqual(first, second)
        self.assertEqual(first["frames_simulated"], 320)
        self.assertEqual(first["segment_count"], 5)
        self.assertEqual(first["goal_first_reached_frame"], 320)
        self.assertEqual(first["final_avatar"]["x"], 3)
        self.assertEqual(len(first["receipt_digest"]), 64)
        self.assertFalse(first["native_emulator_certified"])
        self.assertFalse(first["trained_model_used"])
        self.assertEqual(first["training_examples_added"], 0)
        self.assertTrue(all(s["frames"] <= 64 for s in first["segments"]))

    def test_segmented_state_matches_raw_physics(self):
        controls = [dict(NEUTRAL) for _ in range(67)] + [dict(RIGHT), dict(RIGHT)]
        output = replay_long_controller({"tiles": TILES, "avatar": START, "controls": controls})
        prefix = platformer_replay({"tiles": TILES, "avatar": START, "controls": controls[:64]})
        suffix = platformer_replay({"tiles": TILES, "avatar": prefix["final_avatar"], "controls": controls[64:]})
        self.assertEqual(output["final_avatar"], suffix["final_avatar"])
        self.assertEqual(output["goal_first_reached_frame"], 64 + suffix["goal_first_reached_frame"])

    def test_two_continuations_reach_frame_320(self):
        first = replay_long_controller({
            "tiles": TILES, "avatar": START, "controls": [dict(NEUTRAL) for _ in range(192)],
        })
        second = replay_long_controller({
            "tiles": TILES, "avatar": first["final_avatar"],
            "controls": [dict(NEUTRAL) for _ in range(126)] + [dict(RIGHT), dict(RIGHT)],
            "start_frame": first["end_frame"],
            "previous_receipt_digest": first["receipt_digest"],
        })
        self.assertEqual(second["goal_first_reached_frame"], 320)
        self.assertEqual(second["previous_receipt_digest"], first["receipt_digest"])
        self.assertEqual(second["end_frame"], 320)

    def test_changes_in_actions_change_receipts(self):
        a = replay_long_controller({
            "tiles": TILES, "avatar": START, "controls": [dict(NEUTRAL) for _ in range(320)],
        })
        b = replay_long_controller({
            "tiles": TILES, "avatar": START,
            "controls": [dict(NEUTRAL) for _ in range(319)] + [dict(RIGHT)],
        })
        self.assertNotEqual(a["receipt_digest"], b["receipt_digest"])

    def test_bounds_and_chain_integrity(self):
        for controls in ([], [dict(NEUTRAL)] * (MAX_LONG_REPLAY_FRAMES + 1)):
            with self.subTest(frames=len(controls)), self.assertRaises(GameplayError):
                replay_long_controller({"tiles": TILES, "avatar": START, "controls": controls})
        with self.assertRaises(GameplayError):
            replay_long_controller({
                "tiles": TILES, "avatar": START, "controls": [dict(NEUTRAL)],
                "start_frame": 10,
            })
        with self.assertRaises(GameplayError):
            replay_long_controller({
                "tiles": TILES, "avatar": START, "controls": [dict(NEUTRAL)],
                "previous_receipt_digest": "f" * 64,
            })
        with self.assertRaises(GameplayError):
            replay_long_controller({
                "tiles": TILES, "avatar": START, "controls": [dict(NEUTRAL)],
                "start_frame": True,
            })


if __name__ == "__main__":
    unittest.main()
