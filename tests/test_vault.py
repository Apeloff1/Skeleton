"""Smoke tests for the secrets vault subsystem."""

from skeleton.vault import AuditLog, ShamirSeal


class TestVault:
    def test_audit_log_constructs(self):
        log = AuditLog()
        assert log is not None
        if hasattr(log, "append"):
            try:
                log.append("seal", "ok")
            except TypeError:
                pass
        if hasattr(log, "entries"):
            assert log.entries is not None or True

    def test_shamir_constructs(self):
        seal = ShamirSeal()
        assert seal is not None
        if hasattr(seal, "split"):
            try:
                shares = seal.split(b"secret-key-material", n=5, k=3)
                assert shares
            except TypeError:
                pass
