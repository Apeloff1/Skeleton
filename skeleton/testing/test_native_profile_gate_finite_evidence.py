"""Fail-closed profile admission regressions for optional native acceleration."""
import math
import unittest

from skeleton.native.profile_gate import (
    AccelerationProfile,
    ProfileGate,
    ProfileGateError,
)


class NativeProfileEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.gate = ProfileGate(expected_abi=1, protocol="v1")

    def profile(self, **overrides):
        fields = dict(name="cpu", samples=64, baseline_ns=200, candidate_ns=100,
                      abi_version=1, protocol="v1")
        fields.update(overrides)
        return AccelerationProfile(**fields)

    def test_valid_profile_uses_native(self):
        value, decision = self.gate.call(self.profile(), 3, scalar=lambda x: x,
                                         native=lambda x: x * 2)
        self.assertEqual(value, 6)
        self.assertEqual(decision.backend, "native")

    def test_missing_profile_falls_back(self):
        value, decision = self.gate.call(None, 3, scalar=lambda x: x + 1,
                                         native=lambda x: 999)
        self.assertEqual((value, decision.reason), (4, "profile-missing"))

    def test_crashing_native_falls_back(self):
        def crash(_):
            raise RuntimeError("native failure")
        value, decision = self.gate.call(self.profile(), 3, scalar=lambda x: x + 1,
                                         native=crash)
        self.assertEqual(value, 4)
        self.assertTrue(decision.isolated)

    def test_nan_and_infinite_speedup_policy_denied(self):
        for value in (math.nan, math.inf, -math.inf):
            with self.subTest(value=value), self.assertRaises(ProfileGateError):
                ProfileGate(expected_abi=1, protocol="v1", min_speedup=value)

    def test_boolean_and_invalid_profile_fields_denied(self):
        for field in ("samples", "baseline_ns", "candidate_ns", "abi_version"):
            for value in (True, False, 0, -1, 1.0, "2"):
                with self.subTest(field=field, value=value), self.assertRaises(ProfileGateError):
                    self.profile(**{field: value})

    def test_invalid_profile_identity_denied(self):
        for field in ("name", "protocol"):
            for value in ("", " padded ", None, True):
                with self.subTest(field=field, value=value), self.assertRaises(ProfileGateError):
                    self.profile(**{field: value})

    def test_wrong_protocol_and_abi_stay_scalar(self):
        for profile in (self.profile(protocol="v2"), self.profile(abi_version=2)):
            result, decision = self.gate.call(profile, 7, scalar=lambda x: x,
                                              native=lambda x: 999)
            self.assertEqual(result, 7)
            self.assertEqual(decision.backend, "scalar")


if __name__ == "__main__":
    unittest.main()
