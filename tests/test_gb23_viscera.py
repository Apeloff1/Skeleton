"""GB-23 accept tests. Isolated. No torch."""

from __future__ import annotations

import sys
import unittest

from skeleton.viscera import Tape, capabilities, checkgrad, gqa_scores, lens, newton_schulz
from skeleton.viscera.muon import near_orthogonal
from skeleton.viscera.verify_v24 import run_all


class TestTapeMuon(unittest.TestCase):
    def test_rev_mode(self) -> None:
        t = Tape()
        a = t.leaf(4.0)
        b = t.leaf(0.5)
        y = t.mul(a, b)
        t.backward(y)
        self.assertAlmostEqual(a.grad, 0.5)
        self.assertAlmostEqual(b.grad, 4.0)

    def test_muon_ns(self) -> None:
        self.assertTrue(near_orthogonal(newton_schulz([[0.9, 0.1], [0.2, 0.8]])))


class TestLensGqaGrad(unittest.TestCase):
    def test_logit_lens(self) -> None:
        idx, p = lens([0.0, 2.0], [[1.0, 0.0], [0.0, 1.0]])
        self.assertEqual(idx, 1)
        self.assertAlmostEqual(sum(p), 1.0)

    def test_gqa_groups(self) -> None:
        scores = gqa_scores(
            [[1.0, 0.0], [0.0, 1.0], [1.0, 1.0], [0.0, 0.5]],
            [[1.0, 0.0], [0.0, 1.0]],
            n_kv=2,
        )
        self.assertEqual(len(scores), 4)

    def test_checkgrad_toy(self) -> None:
        self.assertTrue(checkgrad())


class TestCaps(unittest.TestCase):
    def test_capabilities_and_verify(self) -> None:
        cap = capabilities()
        self.assertEqual(cap["packet"], "GB-23")
        self.assertEqual(cap["contract"]["checkgrad"], "2-layer-toy")
        self.assertNotIn("torch", sys.modules)
        self.assertEqual(run_all()["failed"], [])


if __name__ == "__main__":
    unittest.main()
