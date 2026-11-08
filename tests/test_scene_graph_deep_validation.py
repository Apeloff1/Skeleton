"""Regression coverage for deep and adversarial authored scene graphs."""
import unittest

from skeleton.game.flgb_editor_runtime import GameProjectError, SceneGraph, SceneNode


class SceneGraphDepthTests(unittest.TestCase):
    def test_deep_valid_graph_compiles_and_is_stable(self):
        nodes = [SceneNode("root", None, None, 0)]
        for index in range(1, 2500):
            nodes.append(SceneNode(f"node-{index}", "root" if index == 1 else f"node-{index-1}", None, index))
        first = SceneGraph(nodes)
        second = SceneGraph(tuple(reversed(nodes)))
        self.assertEqual(first.digest, second.digest)
        self.assertEqual(first.root_id, "root")

    def test_deep_cycle_fails_closed(self):
        nodes = [SceneNode("root", None, None, 0)]
        nodes.extend(SceneNode(f"node-{i}", f"node-{i+1}", None, i) for i in range(1, 2499))
        nodes.append(SceneNode("node-2499", "node-1", None, 2499))
        with self.assertRaisesRegex(GameProjectError, "cycle"):
            SceneGraph(nodes)

    def test_orphan_and_duplicate_still_fail_closed(self):
        with self.assertRaisesRegex(GameProjectError, "orphan"):
            SceneGraph([SceneNode("root", None, None, 0), SceneNode("orphan", "missing", None, 1)])
        with self.assertRaisesRegex(GameProjectError, "duplicate"):
            SceneGraph([SceneNode("root", None, None, 0), SceneNode("root", None, None, 1)])


if __name__ == "__main__":
    unittest.main()
