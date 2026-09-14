from __future__ import annotations

import pytest

from core.security_config import SecurityConfigError, clear_security_config_caches
from middleware.security import RateLimitMiddleware, SizeLimitMiddleware


async def _noop_app(scope, receive, send):
    return None


def test_rate_limit_invalid_rps_fails_closed_in_production(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("CODEDOCK_RATE_LIMIT_RPS", "not-a-number")
    clear_security_config_caches()

    with pytest.raises(SecurityConfigError):
        RateLimitMiddleware(_noop_app)


def test_rate_limit_invalid_bucket_cap_fails_closed_in_production(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("CODEDOCK_RATE_LIMIT_MAX_BUCKETS", "0")
    clear_security_config_caches()

    with pytest.raises(SecurityConfigError):
        RateLimitMiddleware(_noop_app)


def test_body_limit_invalid_value_fails_closed_in_production(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("CODEDOCK_MAX_BODY_MB", "unbounded")
    clear_security_config_caches()

    with pytest.raises(SecurityConfigError):
        SizeLimitMiddleware(_noop_app)


def test_valid_production_security_limits_are_applied(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("CODEDOCK_RATE_LIMIT_RPS", "4.5")
    monkeypatch.setenv("CODEDOCK_RATE_LIMIT_BURST", "25")
    monkeypatch.setenv("CODEDOCK_RATE_LIMIT_MAX_BUCKETS", "4096")
    monkeypatch.setenv("CODEDOCK_RATE_LIMIT_BUCKET_TTL_SECONDS", "600")
    monkeypatch.setenv("CODEDOCK_MAX_BODY_MB", "8")
    clear_security_config_caches()

    rate = RateLimitMiddleware(_noop_app)
    size = SizeLimitMiddleware(_noop_app)

    assert rate._rps == 4.5
    assert rate._burst == 25
    assert rate._max_buckets == 4096
    assert rate._bucket_ttl == 600
    assert size.max_bytes == 8 * 1024 * 1024
