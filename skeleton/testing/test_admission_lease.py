"""Regression fixtures for fail-closed admission lease."""
import tempfile
from pathlib import Path
import time

from skeleton.admission.lease import AdmissionLease, MAX_PUSHES_LAST_MINUTE


def test_acquire_and_release_under_limit():
    with tempfile.TemporaryDirectory() as d:
        lease = AdmissionLease(Path(d) / "ledger.json")
        token = lease.acquire("A", "abc123", "bot")
        assert token is not None
        lease.release(token, "abc123")
        assert lease.count_recent() == 1


def test_exhaust_headroom():
    with tempfile.TemporaryDirectory() as d:
        lease = AdmissionLease(Path(d) / "ledger.json")
        for i in range(MAX_PUSHES_LAST_MINUTE):
            t = lease.acquire("lane", f"sha{i}", "bot")
            assert t is not None
            lease.release(t, f"sha{i}")
        assert lease.acquire("lane", "extra", "bot") is None


def test_concurrent_sha_fails_closed():
    with tempfile.TemporaryDirectory() as d:
        lease = AdmissionLease(Path(d) / "ledger.json")
        t1 = lease.acquire("A", "same", "bot1")
        assert t1 is not None
        try:
            lease.acquire("B", "same", "bot2")
            assert False, "should have failed closed"
        except RuntimeError:
            pass
