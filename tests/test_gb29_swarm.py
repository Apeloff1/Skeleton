"""GB-29 2-agent handoff tests."""

from __future__ import annotations

import unittest

from skeleton.swarm import Mesh, N_CAP, boundary, capabilities, handoff


class TestHandoff(unittest.TestCase):
    def test_two_agent(self) -> None:
        card = handoff("a1", "a2", "cut")
        self.assertEqual(card["state"], "accept")
        self.assertEqual(card["from"], "a1")
        self.assertEqual(card["to"], "a2")
        self.assertEqual(card["stored_prose"], 0)

    def test_n_cap(self) -> None:
        m = Mesh()
        for i in range(N_CAP):
            m.offer("a%d" % i, "t")
        with self.assertRaises(ValueError):
            m.offer("overflow", "t")

    def test_refuse_expire(self) -> None:
        m = Mesh()
        m.offer("x", "t")
        self.assertEqual(m.refuse("x"), "refuse")
        m.offer("y", "t")
        self.assertEqual(m.expire("y"), "expire")


class TestCaps(unittest.TestCase):
    def test_no_diet_fork(self) -> None:
        self.assertEqual(capabilities()["contract"]["diet_fork"], 0)
        self.assertEqual(boundary()["n_cap"], 8)


if __name__ == "__main__":
    unittest.main()
