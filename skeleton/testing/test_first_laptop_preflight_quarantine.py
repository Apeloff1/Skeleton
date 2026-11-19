"""Negative-first source-only qualification for the quarantined local preflight.

A trusted verifier in these tests is a stub, not a physical model, device,
weights, independent rights approval, release or installer acceptance.
"""
from __future__ import annotations

import math
import unittest
from copy import deepcopy
from unittest.mock import Mock

from skeleton.ai.runtime.operational_ai.offline_cognition.first_laptop_preflight_sota import (
    FirstLaptopPreflightSOTA,
)


def source(epoch: int = 7) -> dict:
    return {
        "installed": True,
        "rights_ok": True,
        "epoch": epoch,
        "model_sha256": "a" * 64,
        "tokenizer_sha256": "b" * 64,
        "source_tree_sha256": "c" * 64,
    }


def rights(epoch: int = 7) -> dict:
    return {
        "approved": True,
        "approval_epoch": epoch,
        "reviewer_sha256": "d" * 64,
    }


def hardware() -> dict:
    return {
        "ram_free": 8, "ram_total": 16,
        "cpu_affinity": 0.8,
        "disk_free": 50, "disk_total": 100,
        "entropy": 0.1,
        "capacity_lease": True,
    }


class FirstLaptopQuarantineTests(unittest.TestCase):
    def test_without_independent_verifier_is_held_not_certified(self):
        gate = FirstLaptopPreflightSOTA()
        result = gate.run(hardware(), source(), rights(), epoch=7)
        self.assertFalse(result["passed"])
        self.assertEqual(result["reason"], "trusted-provenance-unverified")
        self.assertIsNone(gate.provenance)
        self.assertEqual(len(gate.results), 6)
        self.assertEqual(gate.results[-1].stage, "provenance")
        self.assertFalse(gate.results[-1].passed)

    def test_strict_original_source_epoch_and_explicit_rights(self):
        for change, expected_reason in (
            (lambda t, s, r: s.update(epoch=6), "source-identity-unverified"),
            (lambda t, s, r: s.update(model_sha256="not-a-digest"), "source-identity-unverified"),
            (lambda t, s, r: s.update(installed=False), "source-identity-unverified"),
            (lambda t, s, r: s.update(rights_ok=False), "source-identity-unverified"),
            (lambda t, s, r: t.update(capacity_lease=False), "capacity-lease-unverified"),
            (lambda t, s, r: r.update(approved=False), "rights-approval-unverified"),
            (lambda t, s, r: r.update(approval_epoch=6), "rights-approval-unverified"),
            (lambda t, s, r: r.update(reviewer_sha256="0"), "rights-approval-unverified"),
            (lambda t, s, r: t.update(entropy=0.95), "entropy-pressure-exceeded"),
        ):
            with self.subTest(reason=expected_reason, case=change.__code__.co_firstlineno):
                telemetry, candidate, approval = hardware(), source(), rights()
                change(telemetry, candidate, approval)
                observer = Mock(return_value=True)
                gate = FirstLaptopPreflightSOTA()
                result = gate.run(telemetry, candidate, approval, epoch=7,
                                  provenance_verifier=observer)
                self.assertFalse(result["passed"])
                self.assertEqual(result["reason"], expected_reason)
                observer.assert_not_called()
                self.assertIsNone(gate.provenance)

    def test_bounded_broken_telemetry_and_malformed_epoch_fail_before_verifier(self):
        for candidate in (
            {**hardware(), "ram_total": 0},
            {**hardware(), "ram_free": 100},
            {**hardware(), "cpu_affinity": 1.1},
            {**hardware(), "entropy": math.nan},
            {**hardware(), "disk_total": 0},
            {**hardware(), "ram_free": True},
        ):
            with self.subTest(candidate=candidate):
                result = FirstLaptopPreflightSOTA().run(
                    candidate, source(), rights(), epoch=7,
                    provenance_verifier=Mock(return_value=True),
                )
                self.assertFalse(result["passed"])
        for epoch in (True, -1, 2**31, "7"):
            with self.subTest(epoch=epoch):
                gate = FirstLaptopPreflightSOTA()
                report = gate.run(hardware(), source(), rights(), epoch=epoch,
                                  provenance_verifier=lambda *_: True)
                self.assertFalse(report["passed"])
                self.assertEqual(report["reason"], "invalid-epoch")

    def test_independent_verifier_is_required_to_return_literal_true(self):
        for answer in (None, False, 1, "verified"):
            with self.subTest(value=answer):
                report = FirstLaptopPreflightSOTA().run(
                    hardware(), source(), rights(), epoch=7,
                    provenance_verifier=lambda *_: answer,
                )
                self.assertFalse(report["passed"])
                self.assertEqual(report["reason"], "trusted-provenance-unverified")

    def test_source_only_trusted_stub_receives_isolated_copies(self):
        gate = FirstLaptopPreflightSOTA()
        telemetry, original_source, original_rights = hardware(), source(), rights()
        snapshot_source, snapshot_rights = deepcopy(original_source), deepcopy(original_rights)
        seen = []

        def stub(s, r, epoch):
            self.assertEqual(epoch, 7)
            self.assertEqual(s, snapshot_source)
            self.assertEqual(r, snapshot_rights)
            seen.append(epoch)
            s.clear()
            r["approved"] = False
            return True

        report = gate.run(telemetry, original_source, original_rights,
                          epoch=7, provenance_verifier=stub)
        self.assertTrue(report["passed"])
        self.assertEqual(report["stages"], 6)
        self.assertEqual(seen, [7])
        self.assertEqual(original_source, snapshot_source)
        self.assertEqual(original_rights, snapshot_rights)
        self.assertRegex(report["provenance"], r"^[0-9a-f]{64}$")
        self.assertEqual(gate.provenance, report["provenance"])
        self.assertNotIn("device_certified", report)
        self.assertNotIn("model_quality_certified", report)
        self.assertNotIn("release_certified", report)
        # An invalid later call must never inherit an earlier success.
        held = gate.run(telemetry, source(epoch=6), rights(), epoch=7,
                        provenance_verifier=stub)
        self.assertFalse(held["passed"])
        self.assertIsNone(gate.provenance)
        self.assertEqual(seen, [7])

    def test_refuses_unrecognized_stage_inventory(self):
        for stages in (0, 5, 7, True, 6.0):
            with self.subTest(stages=stages):
                with self.assertRaises(ValueError):
                    FirstLaptopPreflightSOTA(stages=stages)


if __name__ == "__main__":
    unittest.main()
