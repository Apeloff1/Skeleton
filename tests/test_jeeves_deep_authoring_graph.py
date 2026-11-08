"""Regression coverage for deeply nested canonical authoring graphs."""
import unittest

from skeleton.game.flgb_editor_runtime import (
    GameProjectError, PrefabSpec, SceneGraph, SceneNode, validate_prefabs,
)


class DeepGraphValidationTests(unittest.TestCase):
    def test_deep_scene_is_accepted_without_python_recursion(self):
        nodes = [SceneNode("n0", None, None, 0)]
        nodes.extend(SceneNode(f"n{i}", f"n{i-1}", None, i) for i in range(1, 2400))
        graph = SceneGraph(nodes)
        self.assertEqual(graph.root_id, "n0")
        self.assertEqual(len(graph.nodes), 2400)

    def test_deep_scene_cycle_fails_closed(self):
        nodes = [SceneNode("root", None, None, 0)]
        nodes.extend(SceneNode(f"n{i}", f"n{i+1}", None, i) for i in range(2400))
        nodes.append(SceneNode("n2400", "n0", None, 2400))
        with self.assertRaisesRegex(GameProjectError, "cycle"):
            SceneGraph(nodes)

    def test_deep_prefab_chain_and_cycle(self):
        chain = [PrefabSpec("p0", None, ())]
        chain.extend(PrefabSpec(f"p{i}", f"p{i-1}", ()) for i in range(1, 2400))
        self.assertEqual(len(validate_prefabs(chain)), 2400)
        cyclic = [PrefabSpec(f"p{i}", f"p{i+1}", ()) for i in range(2399)]
        cyclic.append(PrefabSpec("p2399", "p0", ()))
        with self.assertRaisesRegex(GameProjectError, "cycle"):
            validate_prefabs(cyclic)

    def test_unknown_prefab_parent_rejected(self):
        with self.assertRaisesRegex(GameProjectError, "unknown prefab parent"):
            validate_prefabs([PrefabSpec("child", "missing", ())])


if __name__ == "__main__":
    unittest.main()
