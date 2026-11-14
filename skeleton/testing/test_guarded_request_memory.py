"""Explicit-consent private memory and retention contract coverage."""
from __future__ import annotations
import unittest
from skeleton.ai.runtime.operational_ai.guarded_request.identities import Scope
from skeleton.ai.runtime.operational_ai.guarded_request.memory_consent import MemoryConsent
from skeleton.ai.runtime.operational_ai.guarded_request.errors import GateDenied


class TestMemoryConsent(unittest.TestCase):
    def setUp(self):
        self.scope = Scope("tenant", "user", "conversation", "a" * 64)
        self.row = MemoryConsent(
            self.scope, "consent_1", "b" * 64, "semantic", True, 100, 1000,
        )

    def test_caller_bound_approval(self):
        self.row.authorize(
            scope=self.scope, source_sha256="b" * 64,
            now_ms=500, caller_approved=True,
        )
        with self.assertRaises(GateDenied):
            self.row.authorize(
                scope=self.scope, source_sha256="b" * 64,
                now_ms=500, caller_approved=False,
            )

    def test_cross_owner_denied(self):
        other = Scope("tenant", "another", "conversation", "a" * 64)
        with self.assertRaises(GateDenied):
            self.row.authorize(
                scope=other, source_sha256="b" * 64,
                now_ms=500, caller_approved=True,
            )

    def test_expired_and_changed_source_denied(self):
        with self.assertRaises(GateDenied):
            self.row.authorize(
                scope=self.scope, source_sha256="b" * 64,
                now_ms=1000, caller_approved=True,
            )
        with self.assertRaises(GateDenied):
            self.row.authorize(
                scope=self.scope, source_sha256="c" * 64,
                now_ms=500, caller_approved=True,
            )

    def test_opt_in_required_at_creation(self):
        with self.assertRaises(GateDenied):
            MemoryConsent(self.scope, "consent_1", "b" * 64, "semantic", False, 100, 1000)

    def test_retention_capped(self):
        with self.assertRaises(GateDenied):
            MemoryConsent(self.scope, "consent_2", "b" * 64,
                          "semantic", True, 0, 31 * 24 * 60 * 60 * 1000)


if __name__ == "__main__":
    unittest.main()
