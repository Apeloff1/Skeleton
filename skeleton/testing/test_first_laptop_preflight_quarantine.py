"""Negative-first custody tests for the isolated, nonrelease laptop preflight."""
from __future__ import annotations

import copy
import math
import unittest

from skeleton.ai.runtime.operational_ai.offline_cognition.first_laptop_preflight_sota import (
    FirstLaptopPreflightSOTA,
)

TELEMETRY = {
    "ram_free": 8, "ram_total": 10, "cpu_affinity": 1.0,
    "disk_free": 8, "disk_total": 10, "entropy": 0.1,
    "capacity_lease": True,
}
SOURCE = {
    "installed": True, "rights_ok": True, "epoch": 3,
    "model_sha256": "a" * 64, "tokenizer_sha256": "b" * 64,
    "source_tree_sha256": "c" * 64,
}
RIGHTS = {"approved": True, "approval_epoch": 3, "reviewer_sha256": "d" * 64}


class FirstLaptopPreflightQuarantine(unittest.TestCase):
    def setUp(self):
        self.preflight = FirstLaptopPreflightSOTA()

    def run_preflight(self, telemetry=None, source=None, rights=None, *, verifier=None, epoch=3):
        return self.preflight.run(
            copy.deepcopy(TELEMETRY if telemetry is None else telemetry),
            copy.deepcopy(SOURCE if source is None else source),
            copy.deepcopy(RIGHTS if rights is None else rights),
            epoch=epoch, provenance_verifier=verifier,
        )

    def test_no_attestor_cannot_claim_ready(self):
        outcome = self.run_preflight()
        self.assertFalse(outcome["passed"])
        self.assertEqual(outcome["reason"], "trusted-provenance-unverified")
        self.assertIsNone(self.preflight.provenance)
        self.assertEqual(len(self.preflight.results), 6)
        self.assertFalse(self.preflight.results[-1].passed)

    def test_true_attestor_bound_to_exact_snapshot(self):
        observed = []
        def trusted(source, rights, epoch):
            observed.append((source, rights, epoch))
            return source == SOURCE and rights == RIGHTS and epoch == 3
        outcome = self.run_preflight(verifier=trusted)
        self.assertTrue(outcome["passed"])
        self.assertEqual(outcome["stages"], 6)
        self.assertEqual(outcome["schema"], "first-laptop-preflight.v3-sota")
        self.assertEqual(len(outcome["provenance"]), 64)
        self.assertEqual(len(observed), 1)
        self.assertIsNone(outcome["recovery"])

    def test_attestor_never_accepts_truthy_non_boolean_or_exception(self):
        for verifier in (lambda *_: 1, lambda *_: "yes", lambda *_: None,
                         lambda *_: False, lambda *_: (_ for _ in ()).throw(RuntimeError())):
            with self.subTest(verifier=verifier):
                outcome = self.run_preflight(verifier=verifier)
                self.assertFalse(outcome["passed"])
                self.assertEqual(outcome["reason"], "trusted-provenance-unverified")

    def test_a_subsequent_bad_run_revokes_prior_success(self):
        self.assertTrue(self.run_preflight(verifier=lambda *_: True)["passed"])
        self.assertTrue(self.preflight.provenance)
        outcome = self.run_preflight(telemetry={"ram_free": float("nan")})
        self.assertFalse(outcome["passed"])
        self.assertEqual(outcome["reason"], "invalid-hardware-telemetry")
        self.assertEqual(self.preflight.results, [])
        self.assertIsNone(self.preflight.provenance)
        self.assertEqual(len(self.preflight.recovery_log), 1)

    def test_capacity_lease_is_exact_boolean_and_fails_closed(self):
        for lease in (False, None, 1, "true", []):
            with self.subTest(lease=lease):
                data = dict(TELEMETRY, capacity_lease=lease)
                result = self.run_preflight(telemetry=data, verifier=lambda *_: True)
                self.assertFalse(result["passed"])
                self.assertEqual(result["reason"], "capacity-lease-unverified")

    def test_provenance_requires_source_model_tokenizer_tree_epoch_and_reviewer(self):
        changes = (
            (dict(SOURCE, installed=1), RIGHTS, "source-identity-unverified"),
            (dict(SOURCE, rights_ok="yes"), RIGHTS, "source-identity-unverified"),
            (dict(SOURCE, model_sha256="X"*64), RIGHTS, "source-identity-unverified"),
            (dict(SOURCE, tokenizer_sha256="b"*63), RIGHTS, "source-identity-unverified"),
            (dict(SOURCE, source_tree_sha256="bad"), RIGHTS, "source-identity-unverified"),
            (dict(SOURCE, epoch=True), RIGHTS, "source-identity-unverified"),
            (dict(SOURCE, epoch=2), RIGHTS, "source-identity-unverified"),
            (SOURCE, dict(RIGHTS, approved=1), "rights-approval-unverified"),
            (SOURCE, dict(RIGHTS, approval_epoch=2), "rights-approval-unverified"),
            (SOURCE, dict(RIGHTS, reviewer_sha256="0"), "rights-approval-unverified"),
        )
        for source, rights, expected in changes:
            with self.subTest(expected=expected, source=source, rights=rights):
                result = self.run_preflight(source=source, rights=rights,
                                            verifier=lambda *_: True)
                self.assertFalse(result["passed"])
                self.assertEqual(result["reason"], expected)

    def test_bad_hardware_numbers_never_become_success(self):
        overrides = (
            {"ram_total": 0}, {"disk_total": -1}, {"ram_free": 100},
            {"disk_free": 20}, {"entropy": -0.1}, {"entropy": 1.1},
            {"cpu_affinity": 1.2}, {"cpu_affinity": True},
            {"disk_total": float("inf")}, {"ram_free": float("nan")},
            {"ram_total": 10**100}, {"disk_total": 10**100},
        )
        for change in overrides:
            with self.subTest(change=change):
                telemetry = dict(TELEMETRY, **change)
                outcome = self.run_preflight(telemetry=telemetry,
                                             verifier=lambda *_: True)
                self.assertFalse(outcome["passed"])

    def test_low_hardware_score_and_high_entropy_denied(self):
        low = dict(TELEMETRY, ram_free=0, disk_free=0, cpu_affinity=0)
        result = self.run_preflight(telemetry=low, verifier=lambda *_: True)
        self.assertEqual(result["reason"], "hardware-score-below-threshold")
        result = self.run_preflight(telemetry=dict(TELEMETRY, entropy=0.95),
                                    verifier=lambda *_: True)
        self.assertEqual(result["reason"], "entropy-pressure-exceeded")

    def test_epoch_and_evidence_budgets_rejected(self):
        for epoch in (True, -1, 2**31, "3", 2.5):
            with self.subTest(epoch=epoch):
                self.assertEqual(self.run_preflight(epoch=epoch)["reason"],
                                 "invalid-epoch")
        oversize = dict(SOURCE, notes="x" * 40_000)
        outcome = self.run_preflight(source=oversize, verifier=lambda *_: True)
        self.assertEqual(outcome["reason"], "invalid-bounded-evidence")
        self.assertIsNone(self.preflight.provenance)

    def test_overlapping_runs_are_denied_without_mutation(self):
        self.preflight._run_lock.acquire()
        try:
            outcome = self.run_preflight(verifier=lambda *_: True)
            self.assertFalse(outcome["passed"])
            self.assertEqual(outcome["reason"], "preflight-busy")
            self.assertFalse(self.preflight.results)
        finally:
            self.preflight._run_lock.release()

    def test_stages_cannot_be_reconfigured_to_skip_guards(self):
        for stages in (0, 5, 7, True, "6"):
            with self.subTest(stages=stages), self.assertRaises(ValueError):
                FirstLaptopPreflightSOTA(stages=stages)


if __name__ == "__main__":
    unittest.main()
