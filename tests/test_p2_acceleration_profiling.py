from __future__ import annotations

import unittest
from pathlib import Path
import tempfile
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]


from skeleton.native.profiling import (
    AcceleratorProfilingError,
    ProfileCase,
    environment_id,
    max_abs_error,
    profile_pair,
    result_digest,
)


class AccelerationProfilingTests(unittest.TestCase):
    def test_environment_id_is_stable_and_nonempty(self) -> None:
        first = environment_id()
        second = environment_id()
        self.assertEqual(first, second)
        self.assertTrue(first)
        self.assertNotIn(" ", first)

    def test_source_identity_rejects_string_iterable(self) -> None:
        from skeleton.native.profiling import (
            AcceleratorProfilingError,
            source_identity,
        )
        with self.assertRaisesRegex(
            AcceleratorProfilingError,
            "iterable of paths, not text",
        ):
            source_identity(ROOT, "skeleton/native/profiling.py")

    def test_source_identity_rejects_symlinked_source(self) -> None:
        from skeleton.native.profiling import source_identity

        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            actual = root / "actual.py"
            actual.write_text("print('ok')\n", encoding="utf-8")
            link = root / "alias.py"
            try:
                link.symlink_to(actual.name)
            except (OSError, NotImplementedError):
                self.skipTest("symlinks are unavailable on this platform")
            with self.assertRaisesRegex(
                AcceleratorProfilingError,
                "must not traverse symlinks",
            ):
                source_identity(root, ["alias.py"])

    def test_result_digest_is_canonical_for_mapping_order(self) -> None:
        self.assertEqual(
            result_digest({"b": 2, "a": 1}),
            result_digest({"a": 1, "b": 2}),
        )

    def test_max_abs_error_preserves_structure(self) -> None:
        self.assertEqual(
            max_abs_error({"x": [1.0, 2.0]}, {"x": [1.0, 2.25]}),
            0.25,
        )
        self.assertEqual(
            max_abs_error({"x": 1.0, "tag": "a"}, {"x": 1.0, "tag": "b"}),
            float("inf"),
        )

    def test_profile_pair_mints_source_bound_evidence(self) -> None:
        ticks = iter([
            0, 1000,   1000, 1400,
            2000, 3000, 3000, 3400,
            4000, 5000, 5000, 5400,
            6000, 7000, 7000, 7400,
        ])
        with mock.patch(
            "skeleton.native.profiling.time.perf_counter_ns",
            side_effect=lambda: next(ticks),
        ):
            run = profile_pair(
                evidence_id="profile-1",
                candidate_id="ACCEL-NATIVE-VECTOR",
                source_identity="abc123",
                reference=lambda value: [value * 2.0],
                candidate=lambda value: [value * 2.0],
                cases=[ProfileCase(args=(1.0,)), ProfileCase(args=(2.0,))],
                repeat_count=2,
                profile_environment_id="test-env",
            )
        evidence = run.evidence
        self.assertEqual(evidence.source_identity, "abc123")
        self.assertEqual(evidence.environment_id, "test-env")
        self.assertEqual(evidence.sample_count, 4)
        self.assertEqual(evidence.reference_median_ns, 1000)
        self.assertEqual(evidence.candidate_median_ns, 400)
        self.assertTrue(evidence.correctness_passed)
        self.assertEqual(evidence.max_abs_error, 0.0)
        self.assertEqual(evidence.crash_count, 0)
        self.assertEqual(evidence.timeout_count, 0)

    def test_correctness_error_is_recorded(self) -> None:
        ticks = iter([0, 100, 100, 150])
        with mock.patch(
            "skeleton.native.profiling.time.perf_counter_ns",
            side_effect=lambda: next(ticks),
        ):
            run = profile_pair(
                evidence_id="profile-error",
                candidate_id="ACCEL-NATIVE-VECTOR",
                source_identity="abc123",
                reference=lambda: {"score": 1.0},
                candidate=lambda: {"score": 1.5},
                cases=[ProfileCase()],
                profile_environment_id="test-env",
            )
        self.assertTrue(run.evidence.correctness_passed)
        self.assertEqual(run.evidence.max_abs_error, 0.5)

    def test_candidate_timeout_is_counted_when_other_samples_succeed(self) -> None:
        calls = {"candidate": 0}

        def candidate(value: int) -> int:
            calls["candidate"] += 1
            if calls["candidate"] == 1:
                raise TimeoutError("bounded timeout")
            return value

        ticks = iter([0, 100, 200, 300, 400, 400, 450])
        with mock.patch(
            "skeleton.native.profiling.time.perf_counter_ns",
            side_effect=lambda: next(ticks),
        ):
            run = profile_pair(
                evidence_id="profile-timeout",
                candidate_id="ACCEL-NATIVE-VECTOR",
                source_identity="abc123",
                reference=lambda value: value,
                candidate=candidate,
                cases=[ProfileCase(args=(1,)), ProfileCase(args=(2,))],
                profile_environment_id="test-env",
            )
        self.assertFalse(run.evidence.correctness_passed)
        self.assertEqual(run.evidence.timeout_count, 1)
        self.assertEqual(run.evidence.crash_count, 0)

    def test_zero_success_refuses_to_mint_receipt(self) -> None:
        ticks = iter([0, 100])
        with mock.patch(
            "skeleton.native.profiling.time.perf_counter_ns",
            side_effect=lambda: next(ticks),
        ):
            with self.assertRaisesRegex(
                AcceleratorProfilingError,
                "refusing to mint profile evidence",
            ):
                profile_pair(
                    evidence_id="profile-zero",
                    candidate_id="ACCEL-NATIVE-VECTOR",
                    source_identity="abc123",
                    reference=lambda: 1,
                    candidate=lambda: (_ for _ in ()).throw(RuntimeError("boom")),
                    cases=[ProfileCase()],
                    profile_environment_id="test-env",
                )


if __name__ == "__main__":
    unittest.main()
