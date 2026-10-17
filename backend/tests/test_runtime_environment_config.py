"""Typed dev/staging/prod runtime configuration contract."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from config.environment import (  # noqa: E402
    SECRET_NAMES, ConfigError, load_runtime_config, normalize_environment,
)

ROOT = BACKEND.parent
S = "x" * 40
STAGING = {
    "ENVIRONMENT": "staging", "MONGO_URL": "mongodb://u:p@mongo:27017/app",
    "CORS_ORIGINS": "https://staging.example.org", "JWT_SECRET": S, "OPS_TOKEN": S,
}


def test_development_defaults_are_permissive_and_typed():
    cfg = load_runtime_config({})
    assert cfg.environment == "development" and cfg.port == 8001
    assert cfg.cors_origins == ("*",) and cfg.log_level == "DEBUG" and cfg.log_json is False
    assert cfg.app_version == "dev" and cfg.metrics_enabled is True


@pytest.mark.parametrize("raw,expected", [("prod", "production"), ("Stage", "staging"), ("dev", "development")])
def test_environment_aliases(raw, expected):
    assert normalize_environment(raw) == expected


def test_staging_valid_config_loads():
    cfg = load_runtime_config({**STAGING, "APP_VERSION": "16.0.0", "PORT": "9000"})
    assert cfg.environment == "staging" and cfg.port == 9000 and cfg.log_json is True
    assert cfg.log_level == "INFO" and cfg.app_version == "16.0.0"


def test_strict_env_reports_every_problem():
    with pytest.raises(ConfigError) as exc:
        load_runtime_config({"ENVIRONMENT": "production", "CORS_ORIGINS": "*", "PORT": "99999"})
    text = "\n".join(exc.value.problems)
    for needle in ("MONGO_URL", "CORS_ORIGINS", "JWT_SECRET", "OPS_TOKEN", "PORT"):
        assert needle in text


def test_production_requires_https_origins():
    with pytest.raises(ConfigError, match="https"):
        load_runtime_config({**STAGING, "ENVIRONMENT": "production", "CORS_ORIGINS": "http://a.example"})


@pytest.mark.parametrize("key,value", [
    ("ENVIRONMENT", "qa"), ("LOG_LEVEL", "LOUD"), ("LOG_JSON", "maybe"),
    ("MONGO_URL", "postgres://x"), ("JWT_SECRET", "short"),
])
def test_invalid_values_rejected(key, value):
    with pytest.raises(ConfigError):
        load_runtime_config({**STAGING, key: value})


def test_redacted_view_never_contains_secrets():
    red = load_runtime_config(STAGING).redacted()
    blob = repr(red)
    assert S not in blob and "u:p" not in blob
    assert red["jwt_secret"] == "set" and red["mongo_url"] == "mongodb://mongo"
    assert S not in repr(load_runtime_config(STAGING))


@pytest.mark.parametrize("name", ["development", "staging", "production"])
def test_env_templates_document_secret_names_without_values(name):
    lines = (ROOT / "deploy" / "environments" / f"backend.{name}.env.example").read_text().splitlines()
    pairs = dict(l.split("=", 1) for l in lines if l and not l.startswith("#"))
    for secret in SECRET_NAMES:
        assert secret in pairs, f"{name}: {secret} undocumented"
        assert pairs[secret] == "", f"{name}: {secret} must not carry a value"
    assert pairs["ENVIRONMENT"] == name
