from __future__ import annotations

import json
from pathlib import Path

import pytest

from skeleton.app.assembly import (
    checks_ok,
    compose_command,
    find_repo_root,
    load_manifest,
    manifest_payload,
    preflight,
)


def test_manifest_is_self_consistent():
    manifest = load_manifest()

    assert manifest.schema_version == 1
    assert manifest.name == "Skeleton"
    assert manifest.compose_file == "docker-compose.yml"
    assert {"frontend", "backend", "skeleton", "mongo"}.issubset(manifest.service_names)
    assert set(manifest.default_services).issubset(manifest.service_names)
    assert set(manifest.full_services).issubset(manifest.service_names)

    for service in manifest.services:
        assert set(service.depends_on).issubset(manifest.service_names)


def test_manifest_payload_is_json_serializable():
    payload = manifest_payload()
    encoded = json.dumps(payload, sort_keys=True)

    assert '"schema_version": 1' in encoded
    assert '"frontend"' in encoded
    assert '"backend"' in encoded
    assert '"skeleton"' in encoded


def test_structural_preflight_passes_for_repository_checkout():
    root = find_repo_root(Path(__file__))
    checks = preflight(root)

    assert checks
    assert checks_ok(checks), [check.message for check in checks if not check.ok]


def test_runtime_preflight_reports_missing_environment_without_mutating_process(monkeypatch):
    root = find_repo_root(Path(__file__))
    monkeypatch.setattr("skeleton.app.assembly.shutil.which", lambda _name: "/usr/bin/docker")
    monkeypatch.setattr("skeleton.app.assembly._read_dotenv", lambda _path: {})

    checks = preflight(root, runtime=True, environ={})
    failures = {check.code for check in checks if not check.ok}

    assert "env:MONGO_URL" in failures
    assert "env:SKL_MONGO_URI" in failures
    assert "env:MONGO_INITDB_ROOT_PASSWORD" in failures
    assert "env:JWT_SECRET" in failures
    assert "runtime:docker" not in failures


def test_up_command_is_deterministic_and_shell_free():
    command = compose_command("up", build=True)

    assert command[:4] == ("docker", "compose", "-f", "docker-compose.yml")
    assert command[4:7] == ("up", "-d", "--build")
    assert "frontend" in command
    assert "backend" in command
    assert "skeleton" in command


def test_full_up_command_enables_optional_profile():
    command = compose_command("up", full=True, build=False)

    assert command[:6] == (
        "docker",
        "compose",
        "-f",
        "docker-compose.yml",
        "--profile",
        "full",
    )
    assert command[6:8] == ("up", "-d")
    assert "chroma" in command


def test_logs_reject_unknown_service():
    with pytest.raises(ValueError, match="unknown service"):
        compose_command("logs", service="not-a-service")
