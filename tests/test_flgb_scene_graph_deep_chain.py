"""Deep scene graph admission, deterministic digest, and fail-closed cycle tests."""
import unittest

from skeleton.game.flgb_editor_runtime import GameProjectError, SceneGraph, SceneNode


class SceneGraphDepthTests(unittest.TestCase):
    def test_long_valid_chain_survives_stack_limit(self):
        nodes = [SceneNode("root", None, None, 0)]
        for index in range(1, 4097):
            parent = "root" if index == 1 else f"node_{index-1}"
            nodes.append(SceneNode(f"node_{index}", parent, None, index))
        graph = SceneGraph(nodes)
        self.assertEqual(len(graph.nodes), 4097)
        self.assertEqual(graph.root_id, "root")
        self.assertEqual(graph.digest, SceneGraph(list(reversed(nodes))).digest)

    def test_deep_cycle_fails_as_contract_error(self):
        nodes = [SceneNode("root", None, None, 0)]
        for index in range(1, 3001):
            parent = "node_3000" if index == 1 else f"node_{index-1}"
            nodes.append(SceneNode(f"node_{index}", parent, None, index))
        with self.assertRaisesRegex(GameProjectError, "cycle"):
            SceneGraph(nodes)

    def test_orphan_and_duplicate_fail_closed(self):
        with self.assertRaisesRegex(GameProjectError, "orphan"):
            SceneGraph([SceneNode("root", None, None, 0),
                        SceneNode("orphan", "missing", None, 1)])
        with self.assertRaisesRegex(GameProjectError, "duplicate"):
            SceneGraph([SceneNode("root", None, None, 0),
                        SceneNode("root", None, None, 1)])

    def test_unrelated_entity_ownership_is_preserved(self):
        graph = SceneGraph([SceneNode("root", None, "player", 0),
                            SceneNode("child", "root", "npc", 1)])
        self.assertEqual([node.entity_id for node in graph.nodes], ["player", "npc"])
        with self.assertRaisesRegex(GameProjectError, "multiple"):
            SceneGraph([SceneNode("root", None, "player", 0),
                        SceneNode("child", "root", "player", 1)])


if __name__ == "__main__":
    unittest.main()
