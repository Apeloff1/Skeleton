"""Fail-closed tests for PR #3474 seam deterministic_token_pipeline."""
from __future__ import annotations

import importlib
import unittest


mod = importlib.import_module("skeleton.ai.pr_seams.deterministic_token_pipeline")


class TestDeterministicTokenPipeline(unittest.TestCase):
    def test_card_law(self):
        self.assertEqual(mod.LAW, "stored_prose=0")
        self.assertIn("/pull/3474", mod.CITATION)
        sample = mod.card(True, probe=1)
        self.assertEqual(sample["stored_prose"], 0)
        self.assertTrue(sample["hit"])
        self.assertEqual(sample["kind"], "token-pipeline")

    def test_rejects_prose(self):
        with self.assertRaises(PermissionError):
            mod.card(True, stored_prose=1)

    def test_pointer_bound(self):
        with self.assertRaises(ValueError):
            mod._id("has\nnewline", "x")
        with self.assertRaises(ValueError):
            mod._u(-1, "n")
        with self.assertRaises(ValueError):
            mod._u(True, "n")



    def test_rejects_non_utf8_unicode_surrogate(self):
        with self.assertRaisesRegex(ValueError, "invalid Unicode"):
            mod.tokenize("\\ud800")
        with self.assertRaisesRegex(ValueError, "invalid Unicode"):
            mod.receipt("\\udfff")

    def test_token_boundaries_are_deterministic_and_cover_input(self):
        text = "alpha  beta_2!"
        tokens = mod.tokenize(text)
        self.assertEqual("".join(item.piece for item in tokens), text)
        self.assertEqual(tokens[0].start, 0)
        self.assertEqual(tokens[-1].end, len(text))
        self.assertTrue(all(a.end == b.start for a, b in zip(tokens, tokens[1:])))

    def test_stable(self):
        a = mod.receipt("alpha beta_2")
        b = mod.receipt("alpha beta_2")
        self.assertEqual(a.receipt_id, b.receipt_id)
        self.assertGreaterEqual(a.n, 3)
        card = mod.exit_card(a)
        self.assertEqual(card["stored_prose"], 0)

if __name__ == "__main__":
    unittest.main()
