"""Regression coverage for bounded iterative scene graph validation."""
import unittest

from skeleton.game.flgb_editor_runtime import GameProjectError, SceneGraph, SceneNode


class SceneGraphDepthTests(unittest.TestCase):
    def test_deep_valid_parent_chain(self):
        nodes = [SceneNode("root", None, None, 0)]
        nodes.extend(SceneNode(f"n{i}", "root" if i == 0 else f"n{i-1}", None, i + 1) for i in range(2500))
        graph = SceneGraph(nodes)
        self.assertEqual(graph.root_id, "root")
        self.assertEqual(len(graph.nodes), 2501)

    def test_deep_cycle_fails_closed(self):
        nodes = [SceneNode("root", None, None, 0)]
        nodes.extend(SceneNode(f"n{i}", f"n{i+1}" if i < 2499 else "n0", None, i + 1) for i in range(2500))
        with self.assertRaisesRegex(GameProjectError, "cycle"):
            SceneGraph(nodes)

    def test_orphan_rejected(self):
        with self.assertRaisesRegex(GameProjectError, "orphan"):
            SceneGraph([SceneNode("root", None, None, 0), SceneNode("bad", "missing", None, 1)])


if __name__ == "__main__":
    unittest.main()
