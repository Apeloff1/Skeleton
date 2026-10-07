"""GB-48 era admit tests."""

from __future__ import annotations

import json
import unittest

from skeleton.era.admit import admit


class TestAdmit(unittest.TestCase):
    def test_token_citation(self) -> None:
        card = admit({"citation": "era_bind"})
        self.assertEqual(card["ok"], 1)
        self.assertEqual(card["citation"], "era_bind")
        self.assertEqual(card["stored_prose"], 0)

    def test_spaced_citation_refused(self) -> None:
        card = admit({"citation": "has a sentence"})
        self.assertEqual(card["ok"], 0)
        self.assertEqual(card["citation"], "")
        self.assertNotIn("sentence", json.dumps(card))


if __name__ == "__main__":
    unittest.main()
