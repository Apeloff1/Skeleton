"""Regression tests for bounded original adventure inventory admission."""
import unittest

from skeleton.jeeves.adventure_game_capability import AdventureGameCapability


class AdventureInventoryCustodyTests(unittest.TestCase):
    def setUp(self):
        self.capability = AdventureGameCapability()

    def test_valid_inventory_is_stable(self):
        result = self.capability.create_inventory_system(["bronze_key", "map"])
        self.assertEqual([item["id"] for item in result["items"]],
                         ["bronze_key", "map"])
        self.assertEqual(result, self.capability.create_inventory_system(
            ["bronze_key", "map"]))

    def test_empty_inventory_is_valid(self):
        self.assertEqual(self.capability.create_inventory_system([])["items"], [])

    def test_invalid_input_fails_without_partial_output(self):
        invalid = (None, "key", ("key",), [1], [None], [True],
                   ["key", "key"], ["Key"], ["a/b"], [""],
                   ["a" * 49], ["a"] * 257)
        for value in invalid:
            with self.subTest(value=str(value)[:40]):
                with self.assertRaises(ValueError):
                    self.capability.create_inventory_system(value)

    def test_pipeline_inventory_remains_compatible(self):
        result = self.capability.full_adventure_pipeline("Original Adventure")
        self.assertEqual(len(result["inventory"]["items"]), 5)
        self.assertEqual(len({x["id"] for x in result["inventory"]["items"]}), 5)


if __name__ == "__main__":
    unittest.main()
