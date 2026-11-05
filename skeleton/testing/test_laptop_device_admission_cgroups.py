"""Fail-closed cgroup effective-memory floors for native laptop admission."""
from __future__ import annotations

import unittest

from skeleton.ai.runtime.operational_ai.laptop_runtime.device_admission import admit
from skeleton.ai.runtime.operational_ai.laptop_runtime.contracts import ContractViolation


def observation(*, host=1_000, cap=200, used=100, effective=100, version=2):
    return {
        "memory_available_bytes": host,
        "state_storage_available_bytes": 2_000,
        "qualified_device": False,
        "measurement_only": True,
        "cgroup_version_observed": version,
        "cgroup_memory_limit_bytes": cap,
        "cgroup_memory_used_bytes": used,
        "effective_memory_available_bytes": effective,
    }


def check(snapshot, *, memory=50, disk=100):
    return admit(
        snapshot,
        minimum_available_memory=memory,
        minimum_state_bytes=disk,
    )


class CgroupAdmissionTests(unittest.TestCase):
    def test_bounded_memory_headroom_is_used_instead_of_host_ram(self):
        approved = check(observation(), memory=80)
        self.assertEqual(approved["memory_headroom_bytes"], 20)
        with self.assertRaises(ContractViolation):
            check(observation(), memory=150)

    def test_legacy_no_cgroup_fields_keeps_observed_host_floor(self):
        legacy = {
            "memory_available_bytes": 1_000,
            "state_storage_available_bytes": 2_000,
            "qualified_device": False,
        }
        self.assertEqual(check(legacy, memory=900)["memory_headroom_bytes"], 100)

    def test_full_cgroup_is_zero_capacity_even_with_free_host_ram(self):
        with self.assertRaises(ContractViolation):
            check(observation(cap=100, used=100, effective=0), memory=1)

    def test_forged_effective_capacity_above_cgroup_headroom_fails_closed(self):
        with self.assertRaises(ContractViolation):
            check(observation(effective=150))

    def test_effective_capacity_may_not_exceed_host_availability(self):
        with self.assertRaises(ContractViolation):
            check(observation(host=50, effective=100))

    def test_missing_partial_observation_is_denied(self):
        incomplete = observation()
        del incomplete["cgroup_memory_used_bytes"]
        with self.assertRaises(ContractViolation):
            check(incomplete)

    def test_cgroup_usage_above_limit_is_denied(self):
        with self.assertRaises(ContractViolation):
            check(observation(cap=100, used=150, effective=0))

    def test_invalid_version_is_denied(self):
        for version in ("2", True, 3):
            with self.subTest(version=version):
                with self.assertRaises(ContractViolation):
                    check(observation(version=version))

    def test_unlimited_cgroup_cannot_inflate_host_capacity(self):
        self.assertEqual(
            check(observation(cap=None, used=5, effective=1_000), memory=900)[
                "memory_headroom_bytes"
            ],
            100,
        )
        with self.assertRaises(ContractViolation):
            check(observation(cap=None, used=5, effective=1_001))

    def test_unknown_cgroup_requires_consistent_absent_usage(self):
        self.assertEqual(
            check(observation(version=None, cap=None, used=None, effective=1_000))[
                "status"
            ],
            "resource-floors-observed",
        )
        with self.assertRaises(ContractViolation):
            check(observation(version=None, cap=None, used=5, effective=1_000))

    def test_cgroup_limit_requires_known_version(self):
        with self.assertRaises(ContractViolation):
            check(observation(version=None))

    def test_device_qualification_cannot_be_forged(self):
        forged = observation()
        forged["qualified_device"] = True
        with self.assertRaises(ContractViolation):
            check(forged)


if __name__ == "__main__":
    unittest.main()
