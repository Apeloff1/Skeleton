"""Regression tests for security-sensitive environment parsing."""

import pytest

from core.security_config import SecurityConfigError, clear_security_config_caches, env_bool, env_cidrs, env_float, env_int


def _set_env(monkeypatch, **values):
    monkeypatch.setenv("ENVIRONMENT", "development")
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    clear_security_config_caches()


def test_development_invalid_integer_uses_conservative_default(monkeypatch):
    _set_env(monkeypatch, CODEDOCK_RATE_LIMIT_BURST="not-an-int")
    assert env_int("CODEDOCK_RATE_LIMIT_BURST", 120, minimum=1, maximum=100_000) == 120


def test_production_invalid_integer_fails_closed(monkeypatch):
    _set_env(monkeypatch, ENVIRONMENT="production", CODEDOCK_RATE_LIMIT_BURST="not-an-int")
    with pytest.raises(SecurityConfigError):
        env_int("CODEDOCK_RATE_LIMIT_BURST", 120, minimum=1, maximum=100_000)


def test_production_out_of_range_integer_fails_closed(monkeypatch):
    _set_env(monkeypatch, ENVIRONMENT="prod", CODEDOCK_MAX_BODY_MB="0")
    with pytest.raises(SecurityConfigError):
        env_int("CODEDOCK_MAX_BODY_MB", 25, minimum=1, maximum=1024)


def test_production_non_finite_float_fails_closed(monkeypatch):
    _set_env(monkeypatch, ENVIRONMENT="production", CODEDOCK_RATE_LIMIT_RPS="nan")
    with pytest.raises(SecurityConfigError):
        env_float("CODEDOCK_RATE_LIMIT_RPS", 2.0, minimum=0.01, maximum=10_000.0)


def test_boolean_parser_accepts_explicit_values(monkeypatch):
    for raw, expected in (("1", True), ("true", True), ("yes", True), ("on", True),
                          ("0", False), ("false", False), ("no", False), ("off", False)):
        _set_env(monkeypatch, ACCESS_LOG=raw)
        assert env_bool("ACCESS_LOG", True) is expected


def test_production_ambiguous_boolean_fails_closed(monkeypatch):
    _set_env(monkeypatch, ENVIRONMENT="production", ACCESS_LOG="maybe")
    with pytest.raises(SecurityConfigError):
        env_bool("ACCESS_LOG", True)


def test_production_empty_integer_fails_closed(monkeypatch):
    _set_env(monkeypatch, ENVIRONMENT="production", CODEDOCK_RATE_LIMIT_BURST=" ")
    with pytest.raises(SecurityConfigError):
        env_int("CODEDOCK_RATE_LIMIT_BURST", 120, minimum=1, maximum=100_000)


def test_valid_cidrs_are_normalized(monkeypatch):
    _set_env(monkeypatch, TRUSTED_PROXY_CIDRS="192.0.2.10,2001:db8::/64")
    networks = env_cidrs("TRUSTED_PROXY_CIDRS", "")
    assert [str(network) for network in networks] == ["192.0.2.10/32", "2001:db8::/64"]


def test_production_invalid_cidr_fails_closed(monkeypatch):
    _set_env(monkeypatch, ENVIRONMENT="production", TRUSTED_PROXY_CIDRS="not-a-cidr")
    with pytest.raises(SecurityConfigError):
        env_cidrs("TRUSTED_PROXY_CIDRS", "192.0.2.0/24")


def test_development_invalid_cidr_uses_default(monkeypatch):
    _set_env(monkeypatch, TRUSTED_PROXY_CIDRS="not-a-cidr")
    networks = env_cidrs("TRUSTED_PROXY_CIDRS", "192.0.2.0/24")
    assert [str(network) for network in networks] == ["192.0.2.0/24"]


def test_production_empty_cidr_fails_closed(monkeypatch):
    _set_env(monkeypatch, ENVIRONMENT="production", TRUSTED_PROXY_CIDRS="")
    with pytest.raises(SecurityConfigError):
        env_cidrs("TRUSTED_PROXY_CIDRS", "192.0.2.0/24")


def test_parser_does_not_expose_raw_invalid_values(monkeypatch):
    _set_env(monkeypatch, ENVIRONMENT="production", ACCESS_LOG="bad\nsecret")
    with pytest.raises(SecurityConfigError) as exc_info:
        env_bool("ACCESS_LOG", True)
    assert "bad" not in str(exc_info.value)
    assert "secret" not in str(exc_info.value)
