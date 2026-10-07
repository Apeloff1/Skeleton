from __future__ import annotations

import pytest

from core.security_config import SecurityConfigError, env_bool, env_cidrs, env_float, env_int


def test_invalid_integer_rejected() -> None:
    with pytest.raises(SecurityConfigError):
        env_int("LIMIT", env={"ENVIRONMENT": "production", "LIMIT": "nope"})


def test_out_of_range_integer_rejected() -> None:
    with pytest.raises(SecurityConfigError):
        env_int("LIMIT", minimum=1, maximum=10, env={"ENVIRONMENT": "production", "LIMIT": "11"})


def test_empty_integer_rejected_in_production() -> None:
    with pytest.raises(SecurityConfigError):
        env_int("LIMIT", default=5, env={"ENVIRONMENT": "production", "LIMIT": "   "})


def test_development_integer_default_is_allowed() -> None:
    assert env_int("LIMIT", default=5, env={"ENVIRONMENT": "development"}) == 5


def test_non_finite_float_rejected() -> None:
    with pytest.raises(SecurityConfigError):
        env_float("TTL", env={"ENVIRONMENT": "production", "TTL": "nan"})


def test_explicit_boolean_parsing() -> None:
    assert env_bool("FEATURE", env={"ENVIRONMENT": "production", "FEATURE": "yes"}) is True
    assert env_bool("FEATURE", env={"ENVIRONMENT": "production", "FEATURE": "0"}) is False


def test_ambiguous_boolean_rejected() -> None:
    with pytest.raises(SecurityConfigError):
        env_bool("FEATURE", env={"ENVIRONMENT": "production", "FEATURE": "maybe"})


def test_valid_cidrs_normalized() -> None:
    assert env_cidrs("TRUSTED", env={"ENVIRONMENT": "production", "TRUSTED": "10.0.0.0/24, 2001:db8::/64"}) == (
        "10.0.0.0/24",
        "2001:db8::/64",
    )


def test_invalid_cidr_rejected() -> None:
    with pytest.raises(SecurityConfigError):
        env_cidrs("TRUSTED", env={"ENVIRONMENT": "production", "TRUSTED": "not-a-network"})


def test_empty_cidr_rejected() -> None:
    with pytest.raises(SecurityConfigError):
        env_cidrs("TRUSTED", env={"ENVIRONMENT": "production", "TRUSTED": " , "})


def test_errors_do_not_echo_raw_invalid_values() -> None:
    secret = "production-secret-value"
    with pytest.raises(SecurityConfigError) as excinfo:
        env_bool("FLAG", env={"ENVIRONMENT": "production", "FLAG": secret})
    assert secret not in str(excinfo.value)
