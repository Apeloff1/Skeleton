"""Fail-closed native acceleration admission regressions."""
import math
import unittest

from skeleton.native.profile_gate import AccelerationProfile, ProfileGate, ProfileGateError


class NativeProfileCustodyTests(unittest.TestCase):
    def setUp(self):
        self.gate = ProfileGate(expected_abi=1, protocol="native-v1")

    def profile(self, **changes):
        values = dict(name="cpu", samples=64, baseline_ns=200, candidate_ns=100,
                      abi_version=1, protocol="native-v1")
        values.update(changes)
        return AccelerationProfile(**values)

    def test_qualified_profile_admits_native(self):
        self.assertEqual(self.gate.decide(self.profile()).backend, "native")

    def test_nonfinite_thresholds_rejected(self):
        for value in (math.nan, math.inf, -math.inf, 10 ** 1000):
            with self.subTest(value=str(value)[:20]):
                with self.assertRaises(ProfileGateError):
                    ProfileGate(expected_abi=1, protocol="native-v1", min_speedup=value)

    def test_malformed_numeric_telemetry_never_admits_native(self):
        for field in ("samples", "baseline_ns", "candidate_ns", "abi_version"):
            for value in (True, False, 1.5, "64", None):
                with self.subTest(field=field, value=value):
                    self.assertEqual(self.gate.decide(self.profile(**{field: value})).backend, "scalar")

    def test_unbounded_telemetry_never_admits_native(self):
        for field in ("samples", "baseline_ns", "candidate_ns"):
            with self.subTest(field=field):
                self.assertEqual(self.gate.decide(self.profile(**{field: 2 ** 1000})).backend, "scalar")

    def test_bad_profile_name_is_not_admitted(self):
        self.assertEqual(self.gate.decide(self.profile(name="")).backend, "scalar")

    def test_native_crash_isolated_to_scalar(self):
        def broken(_):
            raise RuntimeError("native worker died")
        result, decision = self.gate.call(self.profile(), 7, scalar=lambda x: x + 1, native=broken)
        self.assertEqual(result, 8)
        self.assertTrue(decision.isolated)
        self.assertEqual(decision.backend, "scalar")


if __name__ == "__main__":
    unittest.main()
