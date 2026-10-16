"""Hermetic gate regressions: no external requests or live builds occur."""
from __future__ import annotations

import pytest

from skeleton.testing.live_service_gate import (
    approved_disposable_target,
    require_destructive_build_approval,
    require_provider_job_approval,
)


def test_default_live_e2e_is_denied(monkeypatch):
    monkeypatch.delenv("SKELETON_DISPOSABLE_E2E_APPROVED", raising=False)
    monkeypatch.setenv("SKELETON_DISPOSABLE_E2E_URL", "http://127.0.0.1:8001")
    with pytest.raises(ValueError, match="operator approval"):
        approved_disposable_target()


@pytest.mark.parametrize("target", [
    "https://example.org:443", "http://192.168.1.10:8001",
    "http://169.254.169.254:80", "http://localhost:8001/path",
    "http://localhost:8001/?key=1", "http://user:pass@localhost:8001",
    "ftp://localhost:8001", "http://localhost", "http://localhost:99999",
    "http://localhost:8001/#fragment", "http://127.0.0.1.evil.com:8001",
])
def test_untrusted_or_non_disposable_targets_fail(monkeypatch, target):
    monkeypatch.setenv("SKELETON_DISPOSABLE_E2E_APPROVED", "1")
    monkeypatch.setenv("SKELETON_DISPOSABLE_E2E_URL", target)
    with pytest.raises(ValueError):
        approved_disposable_target()


@pytest.mark.parametrize("url", [
    "http://localhost:8001", "http://127.0.0.1:8001/",
    "https://[::1]:8443",
])
def test_explicit_loopback_target_allowed(monkeypatch, url):
    monkeypatch.setenv("SKELETON_DISPOSABLE_E2E_APPROVED", "1")
    monkeypatch.setenv("SKELETON_DISPOSABLE_E2E_URL", url)
    assert approved_disposable_target() == url.rstrip("/")


@pytest.mark.parametrize("key,gate", [
    ("SKELETON_DESTRUCTIVE_E2E_APPROVED", require_destructive_build_approval),
    ("SKELETON_BILLED_E2E_APPROVED", require_provider_job_approval),
])
def test_dangerous_operations_need_separate_explicit_approval(monkeypatch, key, gate):
    monkeypatch.delenv(key, raising=False)
    with pytest.raises(ValueError):
        gate()
    monkeypatch.setenv(key, "yes")
    with pytest.raises(ValueError):
        gate()
    monkeypatch.setenv(key, "1")
    assert gate() is None
