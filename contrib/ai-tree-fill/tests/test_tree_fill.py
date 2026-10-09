import math
import unittest

from ai_tree_fill.conductor import probe_all
from ai_tree_fill.laws import ClippedG, LawBreak, mass_admit, parse_pointers
from ai_tree_fill.numerics import conjugate_gradient, householder_qr, matvec, qk_scores
from ai_tree_fill.organs import dispatch


class TreeFillTests(unittest.TestCase):
    def test_pointers_cap_and_reject_bare_sentence(self):
        pts = parse_pointers("see github.com/Apeloff1/Skeleton and VOL-113 AIFT-MEMORY GB-16")
        self.assertLessEqual(len(pts), 8)
        with self.assertRaises(LawBreak):
            parse_pointers("This is a long stored sentence that must never enter the mesh at all.")

    def test_clipped_g_forbids_stamp(self):
        with self.assertRaises(LawBreak):
            ClippedG(10.0, 10.0, 0.0, 0.0, [])
        g = ClippedG(1.0, 1.0, 0.0, 0.0, [1.0]).step(0.5, 1.0)
        self.assertGreater(g.g, 1.0)
        with self.assertRaises(LawBreak):
            mass_admit(1.0, 1.2)

    def test_qr_reconstructs(self):
        a = [[1.0, 1.0], [1.0, -1.0], [1.0, 2.0]]
        q, r = householder_qr(a)
        rebuilt = []
        for i in range(3):
            rebuilt.append([sum(q[i][k] * r[k][j] for k in range(2)) for j in range(2)])
        for i in range(3):
            for j in range(2):
                self.assertAlmostEqual(rebuilt[i][j], a[i][j], places=6)

    def test_cg_solves_spd(self):
        matrix = [[4.0, 1.0], [1.0, 3.0]]
        b = [1.0, 2.0]
        x = conjugate_gradient(matrix, b)
        ax = matvec(matrix, x)
        self.assertAlmostEqual(ax[0], b[0], places=5)
        self.assertAlmostEqual(ax[1], b[1], places=5)

    def test_unknown_organ_fail_closed(self):
        card = dispatch("not-an-organ", "VOL-1")
        self.assertEqual(card["hit"], 0)
        self.assertEqual(card["law"], "unknown-organ")

    def test_full_probe_available(self):
        report_rows = probe_all().snapshot()
        self.assertGreaterEqual(len(report_rows), 40)
        bad = [row for row in report_rows if row["availability"] != "available"]
        self.assertEqual(bad, [])

    def test_qk_sums_to_one(self):
        scores = qk_scores([0.1, 0.2, 0.3], [[0.1, 0.2, 0.3], [-1.0, 0.2, 0.0]])
        self.assertAlmostEqual(sum(scores), 1.0, places=6)
        self.assertTrue(all(math.isfinite(s) for s in scores))


if __name__ == "__main__":
    unittest.main()
