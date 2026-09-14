"""Regression tests for centralized security configuration parsing."""
from __future__ import annotations

import ipaddress

import pytest

from core import security_config


def test_development_invalid_integer_uses_conservative_default(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("TEST_SECURITY_LIMIT", "not-an-int")

    assert security_config.env_int("TEST_SECURITY_LIMIT", 25, minimum=1, maximum=100) == 25


def test_production_invalid_integer_fails_closed(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("TEST_SECURITY_LIMIT", "not-an-int")

    with pytest.raises(security_config.SecurityConfigError):
        security_config.env_int("TEST_SECURITY_LIMIT", 25, minimum=1, maximum=100)


def test_production_out_of_range_integer_fails_closed(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "prod")
    monkeypatch.setenv("TEST_SECURITY_LIMIT", "0")

    with pytest.raises(security_config.SecurityConfigError):
        security_config.env_int("TEST_SECURITY_LIMIT", 25, minimum=1, maximum=100)


def test_nonfinite_float_fails_closed_in_production(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("TEST_SECURITY_RPS", "nan")

    with pytest.raises(security_config.SecurityConfigError):
        security_config.env_float("TEST_SECURITY_RPS", 2.0, minimum=0.01, maximum=100.0)


def test_boolean_parser_accepts_explicit_values(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("TEST_SECURITY_BOOL", "off")
    assert security_config.env_bool("TEST_SECURITY_BOOL", True) is False

    monkeypatch.setenv("TEST_SECURITY_BOOL", "YES")
    assert security_config.env_bool("TEST_SECURITY_BOOL", False) is True


def test_ambiguous_boolean_fails_closed_in_production(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("TEST_SECURITY_BOOL", "sometimes")

    with pytest.raises(security_config.SecurityConfigError):
        security_config.env_bool("TEST_SECURITY_BOOL", True)


def test_valid_cidrs_are_normalized(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("TEST_TRUSTED_CIDRS", "10.0.0.5/8, 2001:db8::1/64")
    security_config.clear_security_config_caches()

    networks = security_config.env_cidrs("TEST_TRUSTED_CIDRS", "127.0.0.0/8")

    assert networks == (
        ipaddress.ip_network("10.0.0.0/8"),
        ipaddress.ip_network("2001:db8::/64"),
    )


def test_invalid_proxy_cidr_fails_closed_in_production(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("TEST_TRUSTED_CIDRS", "0.0.0.0/0,not-a-network")
    security_config.clear_security_config_caches()

    with pytest.raises(security_config.SecurityConfigError):
        security_config.env_cidrs("TEST_TRUSTED_CIDRS", "127.0.0.0/8")


def test_invalid_proxy_cidr_falls_back_to_default_in_development(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("TEST_TRUSTED_CIDRS", "not-a-network")
    security_config.clear_security_config_caches()

    assert security_config.env_cidrs("TEST_TRUSTED_CIDRS", "127.0.0.0/8") == (
        ipaddress.ip_network("127.0.0.0/8"),
    )
