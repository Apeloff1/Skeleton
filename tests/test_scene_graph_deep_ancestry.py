"""Regression for bounded scene ancestry validation and malformed imports."""
import unittest

from skeleton.game.flgb_editor_runtime import GameProjectError, SceneGraph, SceneNode


class SceneGraphAncestryTests(unittest.TestCase):
    def test_deep_valid_chain_is_not_limited_by_python_recursion(self):
        nodes = [SceneNode("root", None, None, 0)]
        parent = "root"
        for index in range(2500):
            node_id = f"node-{index}"
            nodes.append(SceneNode(node_id, parent, f"entity-{index}", index + 1))
            parent = node_id
        graph = SceneGraph(nodes)
        self.assertEqual(len(graph.nodes), 2501)
        self.assertEqual(graph.root_id, "root")
        self.assertEqual(graph.digest, SceneGraph(tuple(reversed(nodes))).digest)

    def test_disconnected_cycle_fails_closed(self):
        nodes = [
            SceneNode("root", None, None, 0),
            SceneNode("a", "b", None, 1),
            SceneNode("b", "a", None, 2),
        ]
        with self.assertRaisesRegex(GameProjectError, "cycle"):
            SceneGraph(nodes)

    def test_orphan_and_duplicate_identity_fail_closed(self):
        with self.assertRaisesRegex(GameProjectError, "orphan"):
            SceneGraph([SceneNode("root", None, None, 0),
                        SceneNode("orphan", "missing", None, 1)])
        with self.assertRaisesRegex(GameProjectError, "duplicate scene node"):
            SceneGraph([SceneNode("root", None, None, 0),
                        SceneNode("root", None, None, 1)])


if __name__ == "__main__":
    unittest.main()
