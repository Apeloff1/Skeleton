"""GB-18 accept tests. Isolated. No torch. No network."""

from __future__ import annotations

import unittest

from skeleton.graphs import (
    HOUSE_N,
    GraphEngine,
    capabilities,
    conserved,
    dot,
    fiedler,
    gat_lite,
    house_card,
    lambda_max,
    mermaid,
    motif_card,
    vertex_ids,
)
from skeleton.graphs.flow import unit_path_flow
from skeleton.graphs.verify import run_all


class TestHouse(unittest.TestCase):
    def test_n_27(self) -> None:
        self.assertEqual(HOUSE_N, 27)
        self.assertEqual(len(vertex_ids()), 27)
        self.assertEqual(house_card()["n"], 27)
        self.assertEqual(house_card()["stored_prose"], 0)


class TestSpectral(unittest.TestCase):
    def test_lambda_and_fiedler(self) -> None:
        lmax, vec = lambda_max()
        self.assertGreater(lmax, 0.0)
        self.assertEqual(len(vec), 27)
        fval, fvec = fiedler()
        self.assertGreaterEqual(fval, -1e-3)
        self.assertEqual(len(fvec), 27)


class TestFlow(unittest.TestCase):
    def test_conserved(self) -> None:
        self.assertTrue(conserved(unit_path_flow()))


class TestMotifsAndGat(unittest.TestCase):
    def test_motifs(self) -> None:
        card = motif_card()
        self.assertGreater(card["wedges"], 0)
        self.assertEqual(card["stored_prose"], 0)

    def test_gat_rows(self) -> None:
        attn = gat_lite()
        self.assertEqual(len(attn), 27)
        for row in attn:
            self.assertAlmostEqual(sum(row), 1.0, places=6)


class TestExportAndCaps(unittest.TestCase):
    def test_mermaid_dot(self) -> None:
        self.assertTrue(mermaid())
        self.assertTrue(dot())
        self.assertIn("graph", mermaid())
        self.assertIn("graph", dot())

    def test_capabilities(self) -> None:
        cap = capabilities()
        self.assertEqual(cap["owner"], "graphs")
        self.assertEqual(cap["contract"]["house_n"], 27)
        self.assertEqual(cap["security"]["network"], 0)

    def test_engine_and_verify(self) -> None:
        snap = GraphEngine().snapshot()
        self.assertEqual(snap["hit"], 1)
        self.assertEqual(snap["stored_prose"], 0)
        result = run_all()
        self.assertEqual(result["failed"], [])


if __name__ == "__main__":
    unittest.main()
