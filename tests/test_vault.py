"""Smoke tests for the secrets vault subsystem."""

from skeleton.vault import AuditLog, ShamirSeal


class TestVault:
    def test_audit_log_constructs(self):
        assert AuditLog() is not None

    def test_shamir_constructs(self):
        assert ShamirSeal() is not None
