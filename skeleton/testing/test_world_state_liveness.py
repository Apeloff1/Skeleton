"""Regression contracts for canonical world-state termination proofs."""
from __future__ import annotations

import unittest

from skeleton.jeeves.worlds.world_canon import CanonError, propose, prove


def world_with_trap():
    world = propose(world_id="liveness", premise="A signal calls from the hills.",
                    protagonist="Mira", region="Cinder Vale", goal="Reach safety.")
    world["scenes"].append({"id": "trap", "title": "Echo chamber",
                            "narrative": "An echo repeats without escape."})
    world["choices"].extend([
        {"id": "enter_trap", "from": "opening", "to": "trap",
         "label": "Follow the echo", "requires": [], "grants": []},
        {"id": "repeat", "from": "trap", "to": "trap",
         "label": "Listen again", "requires": [], "grants": []},
    ])
    return world


class WorldLivenessProofTests(unittest.TestCase):
    def test_reachable_closed_cycle_rejected_despite_another_ending(self):
        world = world_with_trap()
        with self.assertRaises(CanonError) as caught:
            prove(world)
        self.assertEqual(caught.exception.code, "nonterminating_world_state")
        self.assertIn("trap", str(caught.exception))

    def test_optional_cycle_with_exit_is_accepted(self):
        world = world_with_trap()
        world["choices"].append({
            "id": "escape", "from": "trap", "to": "resolution",
            "label": "Follow the light", "requires": [], "grants": [],
        })
        proof = prove(world)
        self.assertEqual(set(proof.visited_scenes), {"opening", "trap", "resolution"})
        self.assertIn("resolution", proof.ending_witnesses)

    def test_flag_gated_cycle_with_unreachable_exit_is_rejected(self):
        world = world_with_trap()
        world["choices"].append({
            "id": "locked_escape", "from": "trap", "to": "resolution",
            "label": "Use the missing key", "requires": ["key"], "grants": [],
        })
        with self.assertRaises(CanonError) as caught:
            prove(world)
        self.assertEqual(caught.exception.code, "nonterminating_world_state")

    def test_proposed_minimal_world_remains_valid(self):
        world = propose(world_id="baseline", premise="A beacon awakens.",
                        protagonist="Mira", region="Cinder Vale", goal="Find home.")
        proof = prove(world)
        self.assertEqual(proof.states_explored, 2)


if __name__ == "__main__":
    unittest.main()
