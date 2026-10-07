"""Fail-closed tests for PR #3476 seam crawler_provenance_bind."""
from __future__ import annotations

import importlib
import unittest


mod = importlib.import_module("skeleton.ai.pr_seams.crawler_provenance_bind")


class TestCrawlerProvenanceBind(unittest.TestCase):
    def test_card_law(self):
        self.assertEqual(mod.LAW, "stored_prose=0")
        self.assertIn("/pull/3476", mod.CITATION)
        sample = mod.card(True, probe=1)
        self.assertEqual(sample["stored_prose"], 0)
        self.assertTrue(sample["hit"])
        self.assertEqual(sample["kind"], "crawler-provenance")

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



    def test_https_only(self):
        pointer = mod.CrawlPointer.create("https://example.com/doc", 9, "digest")
        bound = mod.bind(pointer, "ctx-1")
        self.assertTrue(bound.root.startswith("bind-root:"))
        with self.assertRaises(ValueError):
            mod.CrawlPointer.create("http://example.com/doc", 9, "digest")

if __name__ == "__main__":
    unittest.main()
