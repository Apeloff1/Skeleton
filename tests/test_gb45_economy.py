"""GB-45 catalog economy tests."""

from __future__ import annotations

import unittest

from skeleton.economy import Harbor, capabilities


class TestHarbor(unittest.TestCase):
    def test_weight_sum(self) -> None:
        h = Harbor({"house": 0.4, "lineage": 0.6})
        self.assertTrue(h.balanced())
        self.assertEqual(h.card()["coin"], 0)
        self.assertEqual(h.card()["stored_prose"], 0)

    def test_bag_reversible(self) -> None:
        h = Harbor()
        h.put("card-a")
        h.put("card-b")
        self.assertEqual(h.bag, ["card-a", "card-b"])
        h.undo()
        self.assertEqual(h.bag, ["card-a"])
        h.take("card-a")
        h.undo()
        self.assertEqual(h.bag, ["card-a"])

    def test_caps(self) -> None:
        cap = capabilities()
        self.assertEqual(cap["contract"]["coin"], 0)
        self.assertEqual(cap["contract"]["network_currency"], 0)


if __name__ == "__main__":
    unittest.main()
