"""GB-49 genos pair tests."""

from __future__ import annotations

import json
import unittest

from skeleton.genos.pair import admit_pair


class TestPair(unittest.TestCase):
    def test_two_tokens(self) -> None:
        card = admit_pair("forge", "extraction")
        self.assertEqual(card["ok"], 1)
        self.assertEqual(card["n"], 2)
        self.assertEqual(card["stored_prose"], 0)

    def test_sentence_refused(self) -> None:
        card = admit_pair("has a sentence", "extraction")
        self.assertEqual(card["ok"], 0)
        self.assertEqual(card["n"], 0)
        self.assertNotIn("sentence", json.dumps(card))


if __name__ == "__main__":
    unittest.main()
