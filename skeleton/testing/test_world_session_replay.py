"""Source-bound deterministic replay, stale source and tamper regressions."""
from __future__ import annotations

from copy import deepcopy
import unittest

from skeleton.jeeves.worlds.world_canon import CanonError, propose
from skeleton.jeeves.worlds.world_session import replay, restore, SESSION_SCHEMA


def sample():
    world = propose(world_id="replay", premise="A beacon shines.",
                    protagonist="Mira", region="Vale", goal="Find the gate.")
    world["scenes"].insert(1, {
        "id": "bridge", "title": "Stone bridge", "narrative": "The river turns."
    })
    world["choices"][0]["to"] = "bridge"
    world["choices"].append({
        "id": "cross", "from": "bridge", "to": "resolution",
        "label": "Cross the bridge", "requires": ["key"], "grants": []
    })
    world["choices"][0]["grants"] = ["key"]
    return world


class WorldSessionTests(unittest.TestCase):
    def test_empty_trace_is_resumable(self):
        receipt = replay(sample(), [])
        self.assertEqual(receipt["schema"], SESSION_SCHEMA)
        self.assertEqual(receipt["scene"], "opening")
        self.assertFalse(receipt["ended"])
        self.assertEqual(restore(sample(), receipt), receipt)

    def test_round_trip_to_ending(self):
        world = sample()
        receipt = replay(world, ["pursue_goal", "cross"])
        self.assertTrue(receipt["ended"])
        self.assertEqual(receipt["flags"], ["key"])
        self.assertEqual(restore(world, receipt), receipt)

    def test_partial_round_trip(self):
        world = sample()
        receipt = replay(world, ["pursue_goal"])
        self.assertEqual(receipt["scene"], "bridge")
        self.assertFalse(receipt["ended"])
        self.assertEqual(restore(world, receipt), receipt)

    def test_unknown_choice_rejected(self):
        with self.assertRaises(CanonError) as error:
            replay(sample(), ["not_a_choice"])
        self.assertEqual(error.exception.code, "unknown_session_choice")

    def test_wrong_scene_rejected(self):
        with self.assertRaises(CanonError) as error:
            replay(sample(), ["cross"])
        self.assertEqual(error.exception.code, "session_wrong_scene")

    def test_choice_after_ending_rejected(self):
        with self.assertRaises(CanonError) as error:
            replay(sample(), ["pursue_goal", "cross", "cross"])
        self.assertEqual(error.exception.code, "session_after_ending")

    def test_trace_type_rejected(self):
        with self.assertRaises(CanonError) as error:
            replay(sample(), "pursue_goal")
        self.assertEqual(error.exception.code, "invalid_session_trace")

    def test_stale_world_rejected(self):
        world = sample()
        receipt = replay(world, ["pursue_goal"])
        edited = deepcopy(world)
        edited["region"] = "New Vale"
        with self.assertRaises(CanonError) as error:
            restore(edited, receipt)
        self.assertEqual(error.exception.code, "session_stale_source")

    def test_tampered_flags_rejected(self):
        world = sample()
        receipt = replay(world, ["pursue_goal"])
        receipt["flags"] = []
        with self.assertRaises(CanonError) as error:
            restore(world, receipt)
        self.assertEqual(error.exception.code, "session_state_mismatch")

    def test_extra_fields_rejected(self):
        world = sample()
        receipt = replay(world, [])
        receipt["privilege"] = "admin"
        with self.assertRaises(CanonError) as error:
            restore(world, receipt)
        self.assertEqual(error.exception.code, "invalid_fields")


if __name__ == "__main__":
    unittest.main()
