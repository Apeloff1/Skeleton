"""Regression acceptance for deep canonical scene graphs and fail-closed cycles."""
import unittest

from skeleton.game.flgb_editor_runtime import GameProjectError, SceneGraph, SceneNode


class DeepSceneGraphTests(unittest.TestCase):
    def test_deep_valid_world_is_accepted_and_stable(self):
        nodes = [SceneNode("root", None, None, 0)]
        nodes.extend(SceneNode(f"n{i}", "root" if i == 0 else f"n{i-1}", None, i + 1) for i in range(2500))
        first = SceneGraph(nodes)
        second = SceneGraph(list(reversed(nodes)))
        self.assertEqual(first.root_id, "root")
        self.assertEqual(first.digest, second.digest)
        self.assertEqual(len(first.nodes), 2501)

    def test_deep_cycle_fails_with_domain_error(self):
        nodes = [SceneNode("root", None, None, 0)]
        nodes.extend(SceneNode(f"n{i}", "n2499" if i == 0 else f"n{i-1}", None, i + 1) for i in range(2500))
        with self.assertRaisesRegex(GameProjectError, "cycle"):
            SceneGraph(nodes)

    def test_orphan_and_multiple_roots_rejected(self):
        with self.assertRaisesRegex(GameProjectError, "orphan"):
            SceneGraph([SceneNode("root", None, None, 0), SceneNode("child", "missing", None, 1)])
        with self.assertRaisesRegex(GameProjectError, "exactly one root"):
            SceneGraph([SceneNode("a", None, None, 0), SceneNode("b", None, None, 1)])

    def test_duplicate_entity_rejected(self):
        with self.assertRaisesRegex(GameProjectError, "multiple scene nodes"):
            SceneGraph([SceneNode("root", None, "same", 0), SceneNode("child", "root", "same", 1)])


if __name__ == "__main__":
    unittest.main()
