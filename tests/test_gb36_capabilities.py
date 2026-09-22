"""GB-36 registry tests. Empty is legal. Shape is required when present."""

from __future__ import annotations

import unittest

from skeleton.frontier.capabilities import REQUIRED, collect, capabilities


class TestRegistry(unittest.TestCase):
    def test_empty_or_shaped(self) -> None:
        cards = collect()
        self.assertIsInstance(cards, dict)
        for owner, card in cards.items():
            self.assertEqual(card["owner"], owner)
            for key in REQUIRED:
                self.assertIn(key, card)

    def test_registry_card(self) -> None:
        cap = capabilities()
        self.assertEqual(cap["packet"], "GB-36")
        self.assertEqual(cap["contract"]["empty_ok"], 1)
        self.assertEqual(cap["security"]["network"], 0)
        self.assertIn("owners", cap)


if __name__ == "__main__":
    unittest.main()
