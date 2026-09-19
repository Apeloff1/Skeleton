"""GB-20 verify gates, engine facade, capabilities, cards."""

from __future__ import annotations

import unittest

from skeleton.spine import (
    PACKET,
    SEGMENT_N,
    SpineEngine,
    VERTEBRA_N,
    VERSION,
    capabilities,
    default_chain,
    spine_card,
)
from skeleton.spine.verify import SEV1, SEV2, run_all


class TestVerifyGates(unittest.TestCase):
    def test_run_all_ok(self) -> None:
        result = run_all()
        self.assertEqual(result["ok"], 1, result["failed"])
        self.assertEqual(result["failed"], [])
        self.assertEqual(result["packet"], "GB-20")
        self.assertEqual(result["n"], len(SEV1) + len(SEV2))
        self.assertEqual(result["sev1"], len(SEV1))
        self.assertEqual(result["sev2"], len(SEV2))

    def test_sev_tables_nonempty(self) -> None:
        self.assertGreaterEqual(len(SEV1), 6)
        self.assertGreaterEqual(len(SEV2), 5)
        names = [fn.__name__ for fn in SEV1 + SEV2]
        self.assertEqual(len(names), len(set(names)))


class TestEngineFacade(unittest.TestCase):
    def test_snapshot_hit(self) -> None:
        card = SpineEngine().snapshot()
        self.assertEqual(card["hit"], 1)
        self.assertEqual(card["stored_prose"], 0)
        self.assertEqual(card["packet"], PACKET)
        self.assertEqual(card["vertebra_n"], VERTEBRA_N)
        self.assertEqual(card["segment_n"], SEGMENT_N)
        self.assertEqual(card["rom_ok"], 1)
        self.assertEqual(card["load_conserved"], 1)
        self.assertLessEqual(card["load_residual"], 1e-6)
        self.assertEqual(len(card["digest"]), 16)

    def test_verify_local(self) -> None:
        local = SpineEngine().verify_local()
        self.assertEqual(local["ok"], 1)
        self.assertEqual(local["failed"], [])

    def test_metrics_and_digest(self) -> None:
        eng = SpineEngine()
        m = eng.metrics()
        self.assertEqual(m["vertebra_n"], 33)
        self.assertEqual(eng.digest(), m["digest"])

    def test_with_chain(self) -> None:
        chain = default_chain("custom")
        eng = SpineEngine().with_chain(chain)
        self.assertEqual(eng.chain.name, "custom")

    def test_curvature_helpers(self) -> None:
        eng = SpineEngine()
        self.assertTrue(eng.curvature_ok())
        summary = eng.curvature_summary()
        self.assertIn("cervical_cobb", summary)
        curved = eng.curved()
        self.assertEqual(len(curved.chain.vertebrae), VERTEBRA_N)


class TestCapabilitiesAndCards(unittest.TestCase):
    def test_capabilities_shape(self) -> None:
        cap = capabilities()
        self.assertEqual(cap["owner"], "spine")
        self.assertEqual(cap["packet"], PACKET)
        self.assertEqual(cap["version"], VERSION)
        self.assertEqual(cap["contract"]["vertebra_n"], 33)
        self.assertEqual(cap["contract"]["segment_n"], 32)
        self.assertEqual(cap["contract"]["stored_prose"], 0)
        self.assertEqual(cap["security"]["network"], 0)
        self.assertEqual(cap["security"]["torch"], 0)
        self.assertEqual(cap["security"]["ace"], "fail-closed")
        self.assertTrue(cap["failure_modes"])
        self.assertTrue(cap["obs"])

    def test_spine_card_forces_stored_prose_zero(self) -> None:
        card = spine_card(kind="spine", hit=1, law="spine 1.0", extra={"stored_prose": 99, "x": 1})
        self.assertEqual(card["stored_prose"], 0)
        self.assertEqual(card["x"], 1)
        self.assertNotIn(99, card.values())


if __name__ == "__main__":
    unittest.main()
