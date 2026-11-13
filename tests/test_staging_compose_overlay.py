"""Staging overlay must run production images with fail-closed config."""
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


class _Loader(yaml.SafeLoader):
    pass


_Loader.add_constructor("!override", lambda l, n: l.construct_sequence(n))


def _overlay():
    return yaml.load((ROOT / "docker-compose.staging.yml").read_text(), Loader=_Loader)


def test_staging_uses_production_targets_and_staging_env():
    svc = _overlay()["services"]
    assert svc["backend"]["build"]["target"] == "production"
    assert svc["frontend"]["build"]["target"] == "production"
    env = svc["backend"]["environment"]
    assert "ENVIRONMENT=staging" in env and "LOG_JSON=true" in env


def test_staging_requires_secrets_and_origins_without_defaults():
    env = "\n".join(_overlay()["services"]["backend"]["environment"])
    assert "CORS_ORIGINS=${CORS_ORIGINS:?" in env
    assert "OPS_TOKEN=${OPS_TOKEN:?" in env


def test_staging_binds_ports_to_localhost_only():
    for svc in _overlay()["services"].values():
        for port in svc.get("ports", []):
            assert port.startswith("127.0.0.1:")


def test_no_real_env_files_committed():
    env_dir = ROOT / "deploy" / "environments"
    assert all(p.name.endswith(".env.example") for p in env_dir.iterdir())
