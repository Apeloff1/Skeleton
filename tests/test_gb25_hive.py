"""GB-25 accept tests. Isolated. No network."""

from __future__ import annotations

import unittest

from skeleton.hive import Hive, HiveEngine, WALK_CAP, capabilities
from skeleton.hive.verify import run_all


class TestMintGossipWalk(unittest.TestCase):
    def test_mint_link_card(self) -> None:
        h = Hive()
        a = h.mint("forge")
        b = h.link(a["root"], "child")
        c = h.card_root(a["root"])
        self.assertEqual(a["stored_prose"], 0)
        self.assertEqual(c["kind"], "root")
        self.assertTrue(b["root"])

    def test_two_gossip(self) -> None:
        h = Hive()
        h.mint("a")
        h.gossip()
        g2 = h.gossip()
        self.assertGreaterEqual(g2["n_history"], 2)
        self.assertTrue(g2["consensus"])

    def test_walk_cap(self) -> None:
        h = Hive()
        node = h.mint("s")["root"]
        start = node
        for i in range(12):
            node = h.link(node, "n%d" % i)["child"]
        path = h.walk(start)["path"]
        self.assertLessEqual(len(path), WALK_CAP)
        self.assertEqual(WALK_CAP, 8)


class TestCaps(unittest.TestCase):
    def test_engine(self) -> None:
        cap = capabilities()
        self.assertEqual(cap["contract"]["chain"], 0)
        self.assertEqual(cap["contract"]["coin"], 0)
        snap = HiveEngine().snapshot()
        self.assertEqual(snap["hit"], 1)
        self.assertEqual(run_all()["failed"], [])


if __name__ == "__main__":
    unittest.main()
