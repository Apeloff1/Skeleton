"""GB-22 accept tests. Isolated. No torch."""

from __future__ import annotations

import math
import sys
import unittest

from skeleton.viscera import (
    VisceraEngine,
    capabilities,
    quant_snr,
    remat,
    specdec_verify,
    steer,
)
from skeleton.viscera.qk_norm import attend
from skeleton.viscera.verify import run_all


class TestSpecdecSteer(unittest.TestCase):
    def test_accept_until_mismatch(self) -> None:
        self.assertEqual(specdec_verify([1, 2, 9, 4], [1, 2, 3, 4]), 2)

    def test_steer_length(self) -> None:
        out = steer([0.0, 1.0], [2.0, 0.0])
        self.assertEqual(len(out), 2)


class TestQuantRemat(unittest.TestCase):
    def test_snr_finite(self) -> None:
        snr = quant_snr([0.1, -0.2, 0.3])
        self.assertTrue(math.isfinite(snr) or snr == float("inf"))

    def test_remat_identity(self) -> None:
        _, _, same = remat(lambda x: [v + 0.0 for v in x], [1.0, 2.0])
        self.assertTrue(same)


class TestCapsEngine(unittest.TestCase):
    def test_qk_and_caps(self) -> None:
        self.assertTrue(math.isfinite(attend([1.0, 0.0], [1.0, 0.0])))
        cap = capabilities()
        self.assertEqual(cap["owner"], "viscera")
        self.assertEqual(cap["security"]["torch"], 0)
        self.assertNotIn("torch", sys.modules)

    def test_engine_and_verify(self) -> None:
        snap = VisceraEngine().snapshot()
        self.assertEqual(snap["hit"], 1)
        self.assertEqual(snap["stored_prose"], 0)
        self.assertEqual(snap["accepted"], 3)
        self.assertEqual(run_all()["failed"], [])


if __name__ == "__main__":
    unittest.main()
