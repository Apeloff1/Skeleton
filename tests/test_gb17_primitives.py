"""GB-17 accept tests. Isolated. No torch. No network."""

from __future__ import annotations

import math
import sys
import unittest

from skeleton.primitives import (
    KIND_COUNT,
    KINDS,
    RING_CAP,
    PrimitiveEngine,
    Ring,
    bond,
    capabilities,
    gelu,
    gossip,
    house,
    kind_count,
    primitive_card,
    rms_norm,
    silu,
    viscera_card,
    witness,
)
from skeleton.primitives.merkle import proof, root_of, verify
from skeleton.primitives.verify import run_all
from skeleton.primitives.viscera_bridge import assert_no_viscera_import


class TestKindsFrozen(unittest.TestCase):
    def test_twelve(self) -> None:
        self.assertEqual(KIND_COUNT, 12)
        self.assertEqual(kind_count(), 12)
        self.assertEqual(len(KINDS), 12)
        self.assertEqual(len(set(KINDS)), 12)

    def test_named_ops_present(self) -> None:
        for name in (
            "bond",
            "quench",
            "witness",
            "gossip",
            "fork",
            "house",
            "compact",
            "silu",
            "gelu",
            "rms_norm",
        ):
            self.assertIn(name, KINDS)


class TestRingCap(unittest.TestCase):
    def test_cap_24(self) -> None:
        ring = Ring()
        for i in range(30):
            ring.push("n" + str(i))
        self.assertEqual(len(ring), RING_CAP)
        self.assertEqual(RING_CAP, 24)
        self.assertEqual(ring.items()[0], "n6")


class TestMerkle(unittest.TestCase):
    def test_present_and_verifies(self) -> None:
        leaves = ["p://a", "p://b", "p://c"]
        root = root_of(leaves)
        self.assertTrue(root)
        self.assertTrue(verify("p://b", proof(leaves, 1), root))
        self.assertFalse(verify("p://zzz", proof(leaves, 1), root))


class TestActivations(unittest.TestCase):
    def test_finite(self) -> None:
        self.assertTrue(math.isfinite(silu(0.5)))
        self.assertTrue(math.isfinite(gelu(-0.5)))
        out = rms_norm([1.0, 2.0, 3.0])
        self.assertEqual(len(out), 3)
        self.assertTrue(all(math.isfinite(v) for v in out))


class TestOpsAndCards(unittest.TestCase):
    def test_stored_prose_zero(self) -> None:
        card = bond("a", "b")
        self.assertEqual(card["stored_prose"], 0)
        self.assertEqual(card["kind"], "bond")
        w = witness(["a", "b"])
        self.assertEqual(w["stored_prose"], 0)
        g = gossip(w["root"], w["root"])
        self.assertEqual(g["hit"], 1)
        h = house(["v"] * 3)
        self.assertEqual(h["n"], 3)

    def test_card_strips_prose_override(self) -> None:
        card = primitive_card(kind="ring", hit=1, law="x", extra={"stored_prose": 99})
        self.assertEqual(card["stored_prose"], 0)


class TestVisceraBridge(unittest.TestCase):
    def test_thin_fields(self) -> None:
        assert_no_viscera_import()
        card = viscera_card(G=1.0, law="thin", cite="docs/lineage/primitives.md", root="abc")
        self.assertEqual(card["G"], 1.0)
        self.assertEqual(card["root"], "abc")
        self.assertEqual(card["stored_prose"], 0)
        self.assertNotIn("skeleton.viscera", sys.modules)


class TestCapabilitiesAndEngine(unittest.TestCase):
    def test_capabilities_shape(self) -> None:
        cap = capabilities()
        self.assertEqual(cap["owner"], "primitives")
        self.assertEqual(cap["contract"]["kinds"], 12)
        self.assertIn("failure_modes", cap)
        self.assertIn("obs", cap)
        self.assertEqual(cap["security"]["network"], 0)

    def test_engine_health(self) -> None:
        eng = PrimitiveEngine()
        eng.push("p://1")
        eng.apply_activation("silu", [0.0, 1.0])
        snap = eng.snapshot()
        self.assertEqual(snap["kind_count"], 12)
        self.assertEqual(eng.health()["hit"], 1)

    def test_verify_suite(self) -> None:
        result = run_all()
        self.assertEqual(result["failed"], [])
        self.assertEqual(result["ok"], 1)


if __name__ == "__main__":
    unittest.main()
