"""GB-51 quota tests."""

from __future__ import annotations

import json
import unittest

from skeleton.economy.quota import CAP, admit


class TestQuota(unittest.TestCase):
    def test_tokens_kept(self) -> None:
        card = admit(["card-a", "card-b", "card-c"])
        self.assertEqual(card["n"], 3)
        self.assertEqual(card["dropped"], 0)
        self.assertEqual(card["coin"], 0)
        self.assertEqual(card["stored_prose"], 0)
        self.assertEqual(card["kept"], ["card-a", "card-b", "card-c"])

    def test_cap_and_sentence(self) -> None:
        items = [f"t{i}" for i in range(CAP)] + ["overflow", "has a sentence"]
        card = admit(items)
        self.assertEqual(card["n"], CAP)
        self.assertEqual(card["dropped"], 2)
        self.assertNotIn("sentence", json.dumps(card))
        self.assertNotIn("overflow", card["kept"])


if __name__ == "__main__":
    unittest.main()
