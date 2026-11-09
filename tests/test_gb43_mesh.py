"""GB-43 mesh tests."""

from __future__ import annotations

import json
import unittest

from skeleton.parse.mesh import scan


class TestMesh(unittest.TestCase):
    def test_tokens_pass(self) -> None:
        card = scan({"tokens": ["why", "how", "r3halt"]})
        self.assertEqual(card["hits"], 0)
        self.assertEqual(card["doctor"], 0)
        self.assertEqual(card["stored_prose"], 0)

    def test_sentence_counted_not_kept(self) -> None:
        card = scan({"note": "see the long sentence"})
        self.assertEqual(card["hits"], 1)
        self.assertEqual(card["doctor"], 1)
        self.assertNotIn("sentence", json.dumps(card))


if __name__ == "__main__":
    unittest.main()
