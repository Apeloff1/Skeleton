"""GB-47 cue fold tests."""

from __future__ import annotations

import json
import unittest

from skeleton.cue.fold import fold


class TestFold(unittest.TestCase):
    def test_tokens_join(self) -> None:
        card = fold(["xarchive", "plan", "r1", "why", "yarn"])
        self.assertEqual(card["id"], "xarchive.plan.r1.why.yarn")
        self.assertEqual(card["n"], 5)
        self.assertEqual(card["dropped"], 0)
        self.assertEqual(card["stored_prose"], 0)

    def test_spaced_token_dropped(self) -> None:
        card = fold(["keep this sentence"])
        self.assertEqual(card["id"], "")
        self.assertEqual(card["dropped"], 1)
        self.assertNotIn("sentence", json.dumps(card))


if __name__ == "__main__":
    unittest.main()
