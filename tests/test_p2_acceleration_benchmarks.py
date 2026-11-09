from __future__ import annotations

import importlib.util
import math
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "profile_p2_acceleration",
    ROOT / "scripts" / "profile_p2_acceleration.py",
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class P2AccelerationBenchmarkTests(unittest.TestCase):
    def test_source_identity_changes_with_source_set_and_is_stable(self) -> None:
        from skeleton.native.profiling import source_identity
        first = source_identity(ROOT, ["skeleton/native/asm_accelerator.py"])
        second = source_identity(ROOT, ["skeleton/native/asm_accelerator.py"])
        combined = source_identity(
            ROOT,
            [
                "skeleton/native/asm_accelerator.py",
                "skeleton/native/asm/x86_64.S",
            ],
        )
        self.assertEqual(first, second)
        self.assertNotEqual(first, combined)
        self.assertEqual(len(first), 64)

    def test_vector_reference_is_stable_and_sorted(self) -> None:
        query, norm, rows = MODULE._vector_fixture(dimensions=16, candidates=32)
        hits = MODULE._reference_vector_top_k(query, norm, rows, 5)
        self.assertEqual(len(hits), 5)
        scores = [item["similarity"] for item in hits]
        self.assertEqual(scores, sorted(scores, reverse=True))
        self.assertTrue(all(math.isfinite(float(score)) for score in scores))

    def test_physics_reference_excludes_static_static(self) -> None:
        bodies = MODULE._physics_fixture(12)
        pairs = MODULE._reference_broadphase(bodies, max_pairs=1000)
        for left, right in pairs:
            self.assertTrue(bodies[left][1] or bodies[right][1])
            self.assertTrue(bodies[left][0].overlaps(bodies[right][0]))

    def test_observability_reference_matches_basic_moments(self) -> None:
        summary = MODULE._reference_summary([1.0, 2.0, 3.0, 4.0])
        self.assertEqual(summary["count"], 4)
        self.assertEqual(summary["minimum"], 1.0)
        self.assertEqual(summary["maximum"], 4.0)
        self.assertEqual(summary["mean"], 2.5)
        self.assertAlmostEqual(summary["sample_variance"], 5.0 / 3.0)
        self.assertEqual(summary["p50"], 2.5)
        self.assertEqual(summary["p90"], 4.0)

    def test_all_policy_candidates_have_benchmark_scenarios(self) -> None:
        import json

        policy = json.loads(
            (ROOT / "machine/acceleration_policy.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            set(MODULE.SCENARIOS),
            {item["id"] for item in policy["candidates"]},
        )


if __name__ == "__main__":
    unittest.main()
