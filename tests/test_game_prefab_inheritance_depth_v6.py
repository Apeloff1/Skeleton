"""Regression coverage for deeply nested original-game prefab inheritance."""
import unittest

from skeleton.game.flgb_editor_runtime import (
    GameProjectError, PrefabSpec, validate_prefabs,
)


class PrefabInheritanceDepthTests(unittest.TestCase):
    def chain(self, count):
        return tuple(
            PrefabSpec(f"prefab-{i}", f"prefab-{i-1}" if i else None, ())
            for i in range(count)
        )

    def test_valid_2501_depth_chain(self):
        prefabs = self.chain(2501)
        result = validate_prefabs(tuple(reversed(prefabs)))
        self.assertEqual(len(result), 2501)
        self.assertEqual(result, validate_prefabs(prefabs))

    def test_deep_cycle_fails_closed(self):
        prefabs = list(self.chain(2501))
        prefabs[0] = PrefabSpec("prefab-0", "prefab-2500", ())
        with self.assertRaisesRegex(GameProjectError, "cycle"):
            validate_prefabs(prefabs)

    def test_unknown_parent_fails_closed(self):
        prefabs = list(self.chain(2501))
        prefabs[0] = PrefabSpec("prefab-0", "missing-parent", ())
        with self.assertRaisesRegex(GameProjectError, "unknown prefab parent"):
            validate_prefabs(prefabs)

    def test_duplicate_identity_fails_closed(self):
        with self.assertRaisesRegex(GameProjectError, "duplicate prefab"):
            validate_prefabs((PrefabSpec("same", None, ()), PrefabSpec("same", None, ())))

    def test_self_parent_fails_closed(self):
        with self.assertRaisesRegex(GameProjectError, "cannot inherit itself"):
            PrefabSpec("same", "same", ())


if __name__ == "__main__":
    unittest.main()
