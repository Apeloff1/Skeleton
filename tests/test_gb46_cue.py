"""GB-46 cue tests."""

from __future__ import annotations

import json
import unittest

from skeleton.cue import Cue, capabilities
from skeleton.cue.law import AXES


class TestCue(unittest.TestCase):
    def test_five_ticks_cover_axes(self) -> None:
        cue = Cue()
        card = {}
        for _ in range(5):
            card = cue.tick()
        self.assertEqual(card["i"], 5)
        self.assertEqual(card["stored_prose"], 0)
        for name in AXES:
            self.assertEqual(card["axis"][name], 1)
        self.assertEqual(card["tokens"], ["xarchive", "plan", "r1", "why", "yarn"])

    def test_stimulus_dropped(self) -> None:
        cue = Cue()
        card = cue.tick("see the long sentence https://arxiv.org/abs/x")
        blob = json.dumps(card)
        self.assertEqual(card["dropped"], 1)
        self.assertNotIn("sentence", blob)
        self.assertNotIn("arxiv.org", blob)
        self.assertEqual(card["stored_prose"], 0)

    def test_caps(self) -> None:
        cap = capabilities()
        self.assertEqual(cap["contract"]["stimulus"], "drop")
        self.assertEqual(cap["contract"]["sentence"], 0)
        self.assertEqual(cap["security"]["network"], 0)


if __name__ == "__main__":
    unittest.main()
