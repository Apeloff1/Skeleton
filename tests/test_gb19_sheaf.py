"""GB-19 accept tests. Isolated. No torch. No network."""

from __future__ import annotations

import unittest

from skeleton.sheaf import (
    COVER_N,
    SheafEngine,
    capabilities,
    exact_r_compose_r,
    glue,
    h0_constant,
    h1_constant,
    nerve,
    opens,
)
from skeleton.sheaf.cover import sites
from skeleton.sheaf.verify import run_all


class TestCover(unittest.TestCase):
    def test_twelve(self) -> None:
        self.assertEqual(COVER_N, 12)
        self.assertEqual(len(opens()), 12)


class TestRestrictGlue(unittest.TestCase):
    def test_exact_r_compose_r(self) -> None:
        names = opens()
        section = frozenset(sites())
        self.assertTrue(exact_r_compose_r(section, (names[0], names[1], names[1])))

    def test_glue_skips_cite_feed(self) -> None:
        locals_ = {name: frozenset(("p://root",)) for name in opens()}
        self.assertIsNotNone(glue(locals_))
        self.assertIsNone(glue(locals_, tags=("cite",)))
        self.assertIsNone(glue(locals_, tags=("feed",)))


class TestCechNerve(unittest.TestCase):
    def test_h0_h1(self) -> None:
        self.assertEqual(h0_constant(), 1)
        self.assertEqual(h1_constant(), 1)

    def test_nerve(self) -> None:
        n = nerve()
        self.assertEqual(n["n"], 12)
        self.assertEqual(len(n["edges"]), 12)


class TestCapsEngine(unittest.TestCase):
    def test_capabilities(self) -> None:
        cap = capabilities()
        self.assertEqual(cap["owner"], "sheaf")
        self.assertEqual(cap["contract"]["cover_n"], 12)
        self.assertEqual(cap["security"]["network"], 0)

    def test_engine_and_verify(self) -> None:
        snap = SheafEngine().snapshot()
        self.assertEqual(snap["hit"], 1)
        self.assertEqual(snap["stored_prose"], 0)
        self.assertEqual(snap["H0"], 1)
        result = run_all()
        self.assertEqual(result["failed"], [])


if __name__ == "__main__":
    unittest.main()
