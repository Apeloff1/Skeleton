"""Regression coverage for deep prefab inheritance in the canonical editor."""
import unittest

from skeleton.game.flgb_editor_runtime import (
    GameProjectError, PrefabSpec, validate_prefabs,
)


class PrefabInheritanceDepthTests(unittest.TestCase):
    def test_deep_valid_chain_and_deterministic_order(self):
        prefabs = [
            PrefabSpec(f"p{i:05}", f"p{i-1:05}" if i else None, ())
            for i in range(4097)
        ]
        validated = validate_prefabs(tuple(reversed(prefabs)))
        self.assertEqual(len(validated), 4097)
        self.assertEqual(validated[0].prefab_id, "p00000")
        self.assertEqual(validated[-1].prefab_id, "p04096")

    def test_deep_cycle_fails_closed(self):
        prefabs = [
            PrefabSpec(f"p{i:05}", f"p{i-1:05}" if i else "p04096", ())
            for i in range(4097)
        ]
        with self.assertRaisesRegex(GameProjectError, "cycle"):
            validate_prefabs(prefabs)

    def test_missing_parent_fails_closed(self):
        with self.assertRaisesRegex(GameProjectError, "unknown prefab parent"):
            validate_prefabs([PrefabSpec("child", "missing", ())])

    def test_duplicate_identity_fails_closed(self):
        with self.assertRaisesRegex(GameProjectError, "duplicate prefab identity"):
            validate_prefabs([PrefabSpec("same", None, ()), PrefabSpec("same", None, ())])

    def test_independent_roots_and_shared_ancestor(self):
        result = validate_prefabs([
            PrefabSpec("b", "root", ()),
            PrefabSpec("other", None, ()),
            PrefabSpec("root", None, ()),
            PrefabSpec("a", "root", ()),
        ])
        self.assertEqual(tuple(p.prefab_id for p in result), ("a", "b", "other", "root"))


if __name__ == "__main__":
    unittest.main()
