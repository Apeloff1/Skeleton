"""GB-20 engine/verify stress and package export surface."""

from __future__ import annotations

import unittest

import skeleton.spine as spine
from skeleton.spine.engine import SpineEngine
from skeleton.spine.posture import build_posture, list_postures
from skeleton.spine.verify import run_all


class TestPackageExports(unittest.TestCase):
    def test_all_exports_importable(self) -> None:
        for name in spine.__all__:
            self.assertTrue(hasattr(spine, name), name)
            self.assertIsNotNone(getattr(spine, name))

    def test_law_constants(self) -> None:
        self.assertEqual(spine.PACKET, "GB-20")
        self.assertEqual(spine.VERSION, "1.0")
        self.assertEqual(spine.VERTEBRA_N, 33)
        self.assertEqual(spine.SEGMENT_N, 32)
        self.assertEqual(spine.LAYER, "spine")
        self.assertEqual(spine.TOPOLOGY_KIND, "path-33")
        self.assertEqual(spine.DOF_PER_SEGMENT, 6)


class TestEngineStress(unittest.TestCase):

    def test_engine_snapshot_neutral(self) -> None:
        chain = build_posture("neutral")
        eng = SpineEngine(chain)
        card = eng.snapshot()
        self.assertEqual(card["stored_prose"], 0)
        self.assertEqual(card["vertebra_n"], 33)
        self.assertEqual(card["segment_n"], 32)
        self.assertEqual(card["rom_ok"], 1)
        self.assertEqual(len(card["digest"]), 16)
        local = eng.verify_local()
        self.assertEqual(local["ok"], 1, local)
        m = eng.metrics()
        self.assertEqual(m["rom_ok"], 1)
        self.assertEqual(eng.digest(), card["digest"])

    def test_engine_snapshot_flexion_30(self) -> None:
        chain = build_posture("flexion_30")
        eng = SpineEngine(chain)
        card = eng.snapshot()
        self.assertEqual(card["stored_prose"], 0)
        self.assertEqual(card["vertebra_n"], 33)
        self.assertEqual(card["segment_n"], 32)
        self.assertEqual(card["rom_ok"], 1)
        self.assertEqual(len(card["digest"]), 16)
        local = eng.verify_local()
        self.assertEqual(local["ok"], 1, local)
        m = eng.metrics()
        self.assertEqual(m["rom_ok"], 1)
        self.assertEqual(eng.digest(), card["digest"])

    def test_engine_snapshot_flexion_60(self) -> None:
        chain = build_posture("flexion_60")
        eng = SpineEngine(chain)
        card = eng.snapshot()
        self.assertEqual(card["stored_prose"], 0)
        self.assertEqual(card["vertebra_n"], 33)
        self.assertEqual(card["segment_n"], 32)
        self.assertEqual(card["rom_ok"], 1)
        self.assertEqual(len(card["digest"]), 16)
        local = eng.verify_local()
        self.assertEqual(local["ok"], 1, local)
        m = eng.metrics()
        self.assertEqual(m["rom_ok"], 1)
        self.assertEqual(eng.digest(), card["digest"])

    def test_engine_snapshot_extension_20(self) -> None:
        chain = build_posture("extension_20")
        eng = SpineEngine(chain)
        card = eng.snapshot()
        self.assertEqual(card["stored_prose"], 0)
        self.assertEqual(card["vertebra_n"], 33)
        self.assertEqual(card["segment_n"], 32)
        self.assertEqual(card["rom_ok"], 1)
        self.assertEqual(len(card["digest"]), 16)
        local = eng.verify_local()
        self.assertEqual(local["ok"], 1, local)
        m = eng.metrics()
        self.assertEqual(m["rom_ok"], 1)
        self.assertEqual(eng.digest(), card["digest"])

    def test_engine_snapshot_sitting(self) -> None:
        chain = build_posture("sitting")
        eng = SpineEngine(chain)
        card = eng.snapshot()
        self.assertEqual(card["stored_prose"], 0)
        self.assertEqual(card["vertebra_n"], 33)
        self.assertEqual(card["segment_n"], 32)
        self.assertEqual(card["rom_ok"], 1)
        self.assertEqual(len(card["digest"]), 16)
        local = eng.verify_local()
        self.assertEqual(local["ok"], 1, local)
        m = eng.metrics()
        self.assertEqual(m["rom_ok"], 1)
        self.assertEqual(eng.digest(), card["digest"])

    def test_engine_snapshot_forward_bend(self) -> None:
        chain = build_posture("forward_bend")
        eng = SpineEngine(chain)
        card = eng.snapshot()
        self.assertEqual(card["stored_prose"], 0)
        self.assertEqual(card["vertebra_n"], 33)
        self.assertEqual(card["segment_n"], 32)
        self.assertEqual(card["rom_ok"], 1)
        self.assertEqual(len(card["digest"]), 16)
        local = eng.verify_local()
        self.assertEqual(local["ok"], 1, local)
        m = eng.metrics()
        self.assertEqual(m["rom_ok"], 1)
        self.assertEqual(eng.digest(), card["digest"])

    def test_engine_snapshot_lateral_right_15(self) -> None:
        chain = build_posture("lateral_right_15")
        eng = SpineEngine(chain)
        card = eng.snapshot()
        self.assertEqual(card["stored_prose"], 0)
        self.assertEqual(card["vertebra_n"], 33)
        self.assertEqual(card["segment_n"], 32)
        self.assertEqual(card["rom_ok"], 1)
        self.assertEqual(len(card["digest"]), 16)
        local = eng.verify_local()
        self.assertEqual(local["ok"], 1, local)
        m = eng.metrics()
        self.assertEqual(m["rom_ok"], 1)
        self.assertEqual(eng.digest(), card["digest"])

    def test_engine_snapshot_lateral_left_15(self) -> None:
        chain = build_posture("lateral_left_15")
        eng = SpineEngine(chain)
        card = eng.snapshot()
        self.assertEqual(card["stored_prose"], 0)
        self.assertEqual(card["vertebra_n"], 33)
        self.assertEqual(card["segment_n"], 32)
        self.assertEqual(card["rom_ok"], 1)
        self.assertEqual(len(card["digest"]), 16)
        local = eng.verify_local()
        self.assertEqual(local["ok"], 1, local)
        m = eng.metrics()
        self.assertEqual(m["rom_ok"], 1)
        self.assertEqual(eng.digest(), card["digest"])

    def test_engine_snapshot_axial_cw_10(self) -> None:
        chain = build_posture("axial_cw_10")
        eng = SpineEngine(chain)
        card = eng.snapshot()
        self.assertEqual(card["stored_prose"], 0)
        self.assertEqual(card["vertebra_n"], 33)
        self.assertEqual(card["segment_n"], 32)
        self.assertEqual(card["rom_ok"], 1)
        self.assertEqual(len(card["digest"]), 16)
        local = eng.verify_local()
        self.assertEqual(local["ok"], 1, local)
        m = eng.metrics()
        self.assertEqual(m["rom_ok"], 1)
        self.assertEqual(eng.digest(), card["digest"])

    def test_engine_snapshot_axial_ccw_10(self) -> None:
        chain = build_posture("axial_ccw_10")
        eng = SpineEngine(chain)
        card = eng.snapshot()
        self.assertEqual(card["stored_prose"], 0)
        self.assertEqual(card["vertebra_n"], 33)
        self.assertEqual(card["segment_n"], 32)
        self.assertEqual(card["rom_ok"], 1)
        self.assertEqual(len(card["digest"]), 16)
        local = eng.verify_local()
        self.assertEqual(local["ok"], 1, local)
        m = eng.metrics()
        self.assertEqual(m["rom_ok"], 1)
        self.assertEqual(eng.digest(), card["digest"])

    def test_run_all_idempotent(self) -> None:
        a = run_all()
        b = run_all()
        self.assertEqual(a["ok"], 1)
        self.assertEqual(b["ok"], 1)
        self.assertEqual(a["failed"], [])
        self.assertEqual(b["failed"], [])

    def test_default_engine_curved(self) -> None:
        eng = SpineEngine()
        curved = eng.curved()
        self.assertTrue(curved.curvature_ok())
        summary = curved.curvature_summary()
        self.assertLess(summary["cervical_cobb"], 0.0)
        self.assertGreater(summary["thoracic_cobb"], 0.0)
        self.assertLess(summary["lumbar_cobb"], 0.0)

    def test_posture_count_matches(self) -> None:
        self.assertEqual(SpineEngine().snapshot()["posture_n"], len(list_postures()))


if __name__ == "__main__":
    unittest.main()
