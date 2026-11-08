"""Regression for deeply nested canonical authored world graphs."""
import unittest

from skeleton.game.flgb_editor_runtime import GameProjectError, SceneGraph, SceneNode


class DeepSceneGraphTests(unittest.TestCase):
    def test_deep_valid_scene_survives_validation_and_reopen(self):
        nodes = [SceneNode("root", None, None, 0)]
        nodes.extend(
            SceneNode(f"node-{index}", "root" if index == 0 else f"node-{index-1}", None, index + 1)
            for index in range(2500)
        )
        graph = SceneGraph(nodes)
        reopened = SceneGraph(tuple(reversed(nodes)))
        self.assertEqual(graph.digest, reopened.digest)
        self.assertEqual(graph.root_id, "root")

    def test_deep_cycle_fails_closed(self):
        nodes = [SceneNode("root", None, None, 0)]
        nodes.extend(
            SceneNode(f"node-{index}", f"node-{index+1}" if index < 2499 else "node-0", None, index + 1)
            for index in range(2500)
        )
        with self.assertRaisesRegex(GameProjectError, "cycle"):
            SceneGraph(nodes)

    def test_orphan_fails_closed(self):
        with self.assertRaisesRegex(GameProjectError, "orphan"):
            SceneGraph((SceneNode("root", None, None, 0), SceneNode("lost", "missing", None, 1)))

    def test_duplicate_entity_fails_closed(self):
        with self.assertRaisesRegex(GameProjectError, "multiple scene nodes"):
            SceneGraph((SceneNode("root", None, "hero", 0), SceneNode("child", "root", "hero", 1)))


if __name__ == "__main__":
    unittest.main()
