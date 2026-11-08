"""Regression tests for deeply nested deterministic transform graphs."""
import unittest

from skeleton.game.simulation.flgb_simulation_runtime import (
    MAX_COORD, SimulationContractError, TransformHierarchy, TransformNode,
)


class TransformHierarchyDepthTests(unittest.TestCase):
    def test_deep_chain_and_world_position(self):
        nodes = [
            TransformNode(f"n{i}", None if i == 0 else f"n{i-1}", (1, 0, 0))
            for i in range(2500)
        ]
        graph = TransformHierarchy(nodes)
        self.assertEqual(graph.world_position("n2499"), (2500, 0, 0))
        self.assertEqual(graph.digest, TransformHierarchy(list(reversed(nodes))).digest)

    def test_deep_cycle_rejected_without_recursion_error(self):
        nodes = [
            TransformNode(f"n{i}", f"n{i-1}" if i else "n2499", (0, 0, 0))
            for i in range(2500)
        ]
        with self.assertRaisesRegex(SimulationContractError, "cycle"):
            TransformHierarchy(nodes)

    def test_orphan_and_duplicate_rejected(self):
        with self.assertRaisesRegex(SimulationContractError, "unknown transform parent"):
            TransformHierarchy([TransformNode("a", "missing", (0, 0, 0))])
        with self.assertRaisesRegex(SimulationContractError, "duplicate transform"):
            TransformHierarchy([
                TransformNode("a", None, (0, 0, 0)),
                TransformNode("a", None, (1, 0, 0)),
            ])

    def test_overflow_remains_fail_closed(self):
        graph = TransformHierarchy([
            TransformNode("a", None, (MAX_COORD, 0, 0)),
            TransformNode("b", "a", (1, 0, 0)),
        ])
        with self.assertRaisesRegex(SimulationContractError, "overflow"):
            graph.world_position("b")


if __name__ == "__main__":
    unittest.main()
