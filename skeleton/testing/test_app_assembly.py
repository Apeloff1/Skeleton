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


def test_http_probe_uses_declared_health_surface(monkeypatch):
    from skeleton.app.health import probe_url

    class _Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self, _size):
            return b"ok"

    seen = {}

    def fake_urlopen(request, timeout):
        seen["url"] = request.full_url
        seen["timeout"] = timeout
        return _Response()

    monkeypatch.setattr("skeleton.app.health.urlopen", fake_urlopen)
    service = load_manifest().service("skeleton")

    result = probe_url(service, timeout=1.25)

    assert result.ok is True
    assert result.status == 200
    assert seen == {
        "url": "http://localhost:8010/api/v1/health/live",
        "timeout": 1.25,
    }


def test_default_smoke_profile_has_frontend_backend_and_engine():
    manifest = load_manifest()
    probed = {
        service.name
        for service in manifest.services
        if service.name in manifest.default_services
        and service.public_url
        and service.health_path
    }

    assert probed == {"frontend", "backend", "skeleton"}


def test_frontend_clients_share_canonical_runtime_endpoints():
    root = find_repo_root(Path(__file__))
    resolver = (root / "frontend/utils/apiBase.ts").read_text(encoding="utf-8")

    assert "export const API_BASE" in resolver
    assert "export const SKELETON_API_BASE" in resolver
    assert "EXPO_PUBLIC_BACKEND_URL" in resolver
    assert "EXPO_PUBLIC_SKELETON_URL" in resolver

    expected_imports = {
        "frontend/services/api.ts": "import { API_BASE } from '../utils/apiBase';",
        "frontend/services/skeleton.ts": "import { SKELETON_API_BASE } from '../utils/apiBase';",
        "frontend/src/utils/apiClient.ts": "import { API_BASE } from '../../utils/apiBase';",
        "frontend/src/utils/bootHealth.ts": "import { API_BASE } from '../../utils/apiBase';",
        "frontend/utils/safeFetch.ts": "import { API_BASE } from './apiBase';",
        "frontend/constants/config.ts": "import { API_BASE } from '../utils/apiBase';",
    }
    for relative, expected in expected_imports.items():
        source = (root / relative).read_text(encoding="utf-8")
        assert expected in source, f"{relative} bypasses canonical runtime endpoints"


def test_frontend_skeleton_health_matches_engine_liveness_contract():
    root = find_repo_root(Path(__file__))
    client = (root / "frontend/services/skeleton.ts").read_text(encoding="utf-8")
    routes = (root / "skeleton/api/routes.py").read_text(encoding="utf-8")

    assert "'/api/v1/health/live'" in client
    assert '@router.get("/health/live")' in routes
