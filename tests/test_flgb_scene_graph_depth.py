"""Regression tests for deep, cyclic, and malformed editor scene graphs."""
import unittest

from skeleton.game.flgb_editor_runtime import GameProjectError, SceneGraph, SceneNode


class SceneGraphDepthTests(unittest.TestCase):
    def test_deep_chain_is_valid_without_python_recursion(self):
        nodes = [SceneNode("root", None, None, 0)]
        nodes.extend(SceneNode(f"n{i}", "root" if i == 0 else f"n{i-1}", None, i + 1) for i in range(3000))
        graph = SceneGraph(nodes)
        self.assertEqual(graph.root_id, "root")
        self.assertEqual(len(graph.nodes), 3001)
        self.assertEqual(graph.digest, SceneGraph(tuple(reversed(nodes))).digest)

    def test_deep_cycle_is_rejected_as_contract_error(self):
        nodes = [SceneNode("root", None, None, 0)]
        nodes.extend(SceneNode(f"n{i}", f"n{i+1}" if i < 2999 else "n0", None, i + 1) for i in range(3000))
        with self.assertRaisesRegex(GameProjectError, "cycle"):
            SceneGraph(nodes)

    def test_missing_parent_rejected(self):
        with self.assertRaisesRegex(GameProjectError, "orphan"):
            SceneGraph([SceneNode("root", None, None, 0), SceneNode("child", "missing", None, 1)])

    def test_duplicate_entity_rejected(self):
        with self.assertRaisesRegex(GameProjectError, "multiple"):
            SceneGraph([SceneNode("root", None, "entity", 0), SceneNode("child", "root", "entity", 1)])


if __name__ == "__main__":
    unittest.main()
