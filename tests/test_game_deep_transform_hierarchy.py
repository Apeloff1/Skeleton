"""Deep deterministic transform validation: no recursive stack exhaustion."""
import unittest
from skeleton.game.simulation.flgb_simulation_runtime import (
    TransformHierarchy, TransformNode, SimulationContractError,
)

class TransformDepthTests(unittest.TestCase):
    def test_deep_valid_scene_and_restart_digest(self):
        nodes = [TransformNode(f"entity-{i}", f"entity-{i-1}" if i else None, (1, 0, 0))
                 for i in range(2500)]
        world = TransformHierarchy(nodes)
        self.assertEqual(world.world_position("entity-2499"), (2500, 0, 0))
        self.assertEqual(world.digest, TransformHierarchy(list(reversed(nodes))).digest)

    def test_deep_cycle_fails_closed(self):
        nodes = [TransformNode(f"entity-{i}", f"entity-{i-1}" if i else "entity-2499", (1, 0, 0))
                 for i in range(2500)]
        with self.assertRaisesRegex(SimulationContractError, "cycle"):
            TransformHierarchy(nodes)

    def test_unknown_parent_fails_closed(self):
        with self.assertRaisesRegex(SimulationContractError, "unknown transform parent"):
            TransformHierarchy([TransformNode("player", "missing", (0, 0, 0))])

    def test_duplicate_identity_fails_closed(self):
        node = TransformNode("player", None, (0, 0, 0))
        with self.assertRaisesRegex(SimulationContractError, "duplicate transform entity"):
            TransformHierarchy([node, node])

if __name__ == "__main__":
    unittest.main()
