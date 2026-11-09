"""SC-160 fail-closed tests. No network."""

from __future__ import annotations

import unittest

from skeleton.supply_chain.vol178 import Conductor, capabilities, index
from skeleton.supply_chain.vol178.caps.c001_component_id_grammar import ComponentPulse, OrganError
from skeleton.supply_chain.vol178.law import CAPABILITY_COUNT


DIGEST = "a" * 64
REVISION = "b" * 40


class Supply160Tests(unittest.TestCase):
    def test_count(self) -> None:
        reg = capabilities()
        self.assertEqual(reg["count"], 160)
        self.assertEqual(reg["count"], CAPABILITY_COUNT)
        self.assertEqual(len(index()), 160)
        self.assertEqual(reg["stored_prose"], 0)
        self.assertEqual(reg["security"]["coin"], 0)
        self.assertEqual(reg["security"]["network"], 0)

    def test_unique(self) -> None:
        ids = [item["id"] for item in capabilities()["items"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(ids[0], "SC160-001")
        self.assertEqual(ids[-1], "SC160-160")

    def test_families(self) -> None:
        fams = {item["contract"]["family"] for item in capabilities()["items"]}
        self.assertEqual(len(fams), 16)

    def test_pulse_reverse(self) -> None:
        deck = Conductor()
        cards = deck.pulse_all(1, 1)
        self.assertEqual(len(cards), 160)
        self.assertTrue(all(c.get("stored_prose", 0) == 0 for c in cards))
        self.assertGreater(deck.snapshot()["mass"], 0)
        self.assertGreater(deck.reverse_all(), 0)

    def test_stale(self) -> None:
        deck = Conductor()
        cards = deck.pulse_all(2, 1)
        self.assertTrue(any(c.get("hit") == 0 for c in cards))

    def test_bad_digest(self) -> None:
        with self.assertRaises(OrganError):
            ComponentPulse(1, 1, "cmp", "direct", "low", "open", "aa", REVISION)

    def test_critical_risk(self) -> None:
        from skeleton.supply_chain.vol178.caps.c001_component_id_grammar import Organ

        pulse = ComponentPulse(1, 1, "cmp", "direct", "critical", "accepted-risk", DIGEST, REVISION)
        with self.assertRaises(OrganError):
            Organ().admit(pulse)

    def test_double_prior(self) -> None:
        self.assertEqual(CAPABILITY_COUNT, 80 * 2)


if __name__ == "__main__":
    unittest.main()
