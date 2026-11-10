"""Regression for bounded iterative canonical scene validation."""
import unittest
from skeleton.game.flgb_editor_runtime import SceneGraph, SceneNode, GameProjectError


class DeepSceneGraphTests(unittest.TestCase):
    def test_deep_valid_chain(self):
        nodes = [SceneNode("root", None, None, 0)]
        nodes.extend(SceneNode(f"n{i}", "root" if i == 0 else f"n{i-1}", None, i + 1) for i in range(2500))
        graph = SceneGraph(nodes)
        self.assertEqual(len(graph.nodes), 2501)
        self.assertEqual(graph.root_id, "root")

    def test_deep_cycle_fails_closed(self):
        nodes = [SceneNode("root", None, None, 0)]
        nodes.extend(SceneNode(f"n{i}", f"n{i+1}" if i < 2499 else "n0", None, i + 1) for i in range(2500))
        with self.assertRaisesRegex(GameProjectError, "cycle"):
            SceneGraph(nodes)

    def test_missing_parent_fails_closed(self):
        with self.assertRaisesRegex(GameProjectError, "orphan"):
            SceneGraph([SceneNode("root", None, None, 0), SceneNode("child", "absent", None, 1)])

    def test_rebuild_is_deterministic(self):
        nodes = [SceneNode("root", None, None, 0), SceneNode("child", "root", None, 1)]
        self.assertEqual(SceneGraph(nodes).digest, SceneGraph(list(reversed(nodes))).digest)


if __name__ == "__main__":
    unittest.main()
