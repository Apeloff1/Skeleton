"""PR 3538: a repeated URL with a new digest must not bind."""
from __future__ import annotations

import unittest

from skeleton.ai.pr_seams.crawler_holdout import HoldoutError, ProvenanceHoldout
from skeleton.ai.pr_seams.crawler_provenance_bind import CrawlPointer

URL = "https://example.com/source"


class HoldoutLaw(unittest.TestCase):
    def test_drift_does_not_bind(self) -> None:
        gate = ProvenanceHoldout()
        first = CrawlPointer.create(URL, 1, "ab" * 32)
        gate.admit(first, "ctx")
        drifted = CrawlPointer.create(URL, 2, "cd" * 32)
        with self.assertRaises(HoldoutError):
            gate.admit(drifted, "ctx")

    def test_same_digest_binds(self) -> None:
        gate = ProvenanceHoldout()
        pointer = CrawlPointer.create(URL, 1, "ab" * 32)
        card = gate.admit(pointer, "ctx")
        self.assertEqual(card["stored_prose"], 0)
        self.assertEqual(card["digest"], "ab" * 32)


if __name__ == "__main__":
    unittest.main()
