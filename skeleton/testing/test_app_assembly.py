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


def test_product_control_client_matches_mounted_backend_routes():
    root = find_repo_root(Path(__file__))
    client = (root / "frontend/src/product/productControlClient.ts").read_text(encoding="utf-8")
    ops = (root / "backend/routes/ops.py").read_text(encoding="utf-8")
    registry = (root / "backend/core/routes_registry.py").read_text(encoding="utf-8")

    assert "const ROOT = '/api/admin/ops/product-control';" in client
    assert 'router = APIRouter(prefix="/api/admin/ops"' in ops
    assert '("routes.ops",' in registry

    required_routes = (
        "/product-control/status",
        "/product-control/deployment-preflight",
        "/product-control/deployments",
        "/product-control/pending",
        "/product-control/audit",
        "/product-control/receipts",
        "/product-control/receipt/{operation_id}/result",
        "/product-control/execute/{seq}",
        "/product-control/execute-pending",
        "/product-control/admit",
    )
    for route in required_routes:
        assert route in ops, f"frontend product control contract is missing backend route {route}"


def test_safe_mode_recovers_into_canonical_product_shell():
    root = find_repo_root(Path(__file__))
    safe_mode = (root / "frontend/app/safe-mode.tsx").read_text(encoding="utf-8")

    assert "router.replace('/product')" in safe_mode
    assert "Try Product" in safe_mode


def test_wait_for_application_retries_until_healthy(monkeypatch):
    from skeleton.app.health import ProbeResult, wait_for_application

    calls = []
    sleeps = []

    def fake_probe_application(*, manifest, full, timeout):
        calls.append((full, timeout))
        ok = len(calls) >= 3
        return (
            ProbeResult(
                service="backend",
                url="http://localhost:8001/api/health",
                ok=ok,
                status=200 if ok else None,
                detail="healthy" if ok else "not ready",
            ),
        )

    monkeypatch.setattr("skeleton.app.health.probe_application", fake_probe_application)
    monkeypatch.setattr("skeleton.app.health.time.sleep", lambda delay: sleeps.append(delay))

    results = wait_for_application(attempts=5, delay=0.25, timeout=1.5)

    assert results[0].ok is True
    assert calls == [(False, 1.5), (False, 1.5), (False, 1.5)]
    assert sleeps == [0.25, 0.25]


def test_wait_for_application_rejects_invalid_budget():
    from skeleton.app.health import wait_for_application

    with pytest.raises(ValueError, match="attempts"):
        wait_for_application(attempts=0)
    with pytest.raises(ValueError, match="timeout"):
        wait_for_application(timeout=0)
    with pytest.raises(ValueError, match="delay"):
        wait_for_application(delay=-1)


def test_all_launcher_paths_converge_on_product_shell():
    root = find_repo_root(Path(__file__))
    launch = (root / "frontend/components/LaunchCascade.tsx").read_text(encoding="utf-8")
    welcome = (root / "frontend/app/welcome.tsx").read_text(encoding="utf-8")
    safe_mode = (root / "frontend/app/safe-mode.tsx").read_text(encoding="utf-8")

    assert "router.replace('/product')" in launch
    assert "router.replace('/product')" in welcome
    assert "router.replace('/product')" in safe_mode
    assert "Enter Product" in launch
    assert "Enter Product" in welcome


def test_production_web_ingress_routes_both_application_apis():
    root = find_repo_root(Path(__file__))
    nginx = (root / "frontend/nginx.conf").read_text(encoding="utf-8")

    directives = [line.strip() for line in nginx.splitlines()]
    engine_location = directives.index("location ^~ /api/v1/ {")
    backend_location = directives.index("location ^~ /api/ {")
    assert engine_location < backend_location
    assert "proxy_pass http://skeleton:8001;" in nginx
    assert "proxy_pass http://backend:8001;" in nginx


def test_frontend_security_probe_supplies_compose_upstream_names():
    root = find_repo_root(Path(__file__))
    workflow = (root / ".github/workflows/dependency-security.yml").read_text(encoding="utf-8")

    assert "--add-host skeleton:127.0.0.1" in workflow
    assert "--add-host backend:127.0.0.1" in workflow


def test_backend_does_not_claim_skeleton_api_v1_prefix():
    root = find_repo_root(Path(__file__))
    registry = (root / "backend/core/routes_registry.py").read_text(encoding="utf-8")
    server = (root / "backend/server.py").read_text(encoding="utf-8")

    assert "/api/v1" not in registry
    assert "/api/v1" not in server


def test_manifest_declares_explicit_runtime_modes():
    manifest = load_manifest()

    assert manifest.hot_compose_file == "docker-compose.hot.yml"
    assert manifest.mode_env("development")["BUILD_TARGET"] == "development"
    production = manifest.mode_env("production")
    assert production["BUILD_TARGET"] == "production"
    assert production["FRONTEND_BUILD_TARGET"] == "production"
    assert production["FRONTEND_CONTAINER_PORT"] == "8080"


def test_hot_compose_command_adds_only_explicit_overlay():
    command = compose_command("up", hot=True, build=False)

    assert command[:6] == (
        "docker",
        "compose",
        "-f",
        "docker-compose.yml",
        "-f",
        "docker-compose.hot.yml",
    )
    assert command[6:8] == ("up", "-d")


def test_base_compose_is_image_based_and_hot_overlay_owns_source_mounts():
    root = find_repo_root(Path(__file__))
    base = (root / "docker-compose.yml").read_text(encoding="utf-8")
    hot = (root / "docker-compose.hot.yml").read_text(encoding="utf-8")

    assert "./backend:/app" not in base
    assert "./skeleton:/app/skeleton" not in base
    assert "./frontend:/app" not in base

    assert "./backend:/app:ro" in hot
    assert "./skeleton:/app/skeleton:ro" in hot
    assert "./frontend:/app" in hot


def test_cli_rejects_production_hot_combination_before_preflight(capsys):
    from skeleton.app.cli import run_app_cli

    exit_code = run_app_cli(["up", "--production", "--hot"])

    assert exit_code == 2
    assert "mutually exclusive" in capsys.readouterr().out


def test_product_shell_health_client_matches_assembly_manifest():
    root = find_repo_root(Path(__file__))
    client = (root / "frontend/src/product/appHealthClient.ts").read_text(encoding="utf-8")
    shell = (root / "frontend/app/product.tsx").read_text(encoding="utf-8")
    manifest = load_manifest()

    backend = manifest.service("backend")
    skeleton = manifest.service("skeleton")
    assert "getAppBootstrap" in client
    assert "getAppRuntimeStatus" in client
    assert f"backend: '{backend.health_path}'" in client
    assert f"skeleton: '{skeleton.health_path}'" in client
    assert "bootstrapService(bootstrap, 'backend')" in client
    assert "bootstrapService(bootstrap, 'skeleton')" in client
    assert "probeAppHealth" in shell
    assert "Application runtime" in shell
    assert "Runtime" in shell


def test_expo_dev_ports_are_hot_mode_only():
    root = find_repo_root(Path(__file__))
    base = (root / "docker-compose.yml").read_text(encoding="utf-8")
    hot = (root / "docker-compose.hot.yml").read_text(encoding="utf-8")

    for port in ("8081:8081", "19000:19000", "19001:19001", "19002:19002"):
        assert port not in base
        assert port in hot


def test_live_status_reports_runtime_health_and_fails_closed(monkeypatch, capsys):
    from skeleton.app.cli import run_app_cli
    from skeleton.app.health import ProbeResult

    def fake_probe_application(*, manifest, full, timeout):
        assert full is False
        assert timeout == 1.25
        return (
            ProbeResult(
                service="backend",
                url="http://localhost:8001/api/health",
                ok=True,
                status=200,
                detail="healthy",
            ),
            ProbeResult(
                service="skeleton",
                url="http://localhost:8010/api/v1/health/live",
                ok=False,
                status=503,
                detail="HTTP error 503",
            ),
        )

    monkeypatch.setattr("skeleton.app.health.probe_application", fake_probe_application)

    exit_code = run_app_cli(["status", "--live", "--timeout", "1.25", "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert payload["runtime_health"]["ok"] is False
    assert [item["service"] for item in payload["runtime_health"]["results"]] == [
        "backend",
        "skeleton",
    ]


def test_live_status_rejects_non_positive_timeout(capsys):
    from skeleton.app.cli import run_app_cli

    exit_code = run_app_cli(["status", "--live", "--timeout", "0"])

    assert exit_code == 2
    assert "timeout must be greater than zero" in capsys.readouterr().out


def test_public_product_readiness_route_is_registered():
    root = find_repo_root(Path(__file__))
    route = (root / "backend/routes/product_runtime.py").read_text(encoding="utf-8")
    registry = (root / "backend/core/routes_registry.py").read_text(encoding="utf-8")
    client = (root / "frontend/src/product/productControlClient.ts").read_text(encoding="utf-8")
    capability = (root / "frontend/app/capability.tsx").read_text(encoding="utf-8")

    assert 'APIRouter(prefix="/api/product"' in route
    assert '@router.get("/readiness")' in route
    assert '("routes.product_runtime",' in registry
    assert "const PUBLIC_ROOT = '/api/product';" in client
    assert "getProductReadiness" in capability
    assert "getProductControlStatus(''," not in capability


def test_product_routes_are_registered_in_canonical_route_registry():
    root = find_repo_root(Path(__file__))
    registry = (root / "frontend/utils/routeRegistry.ts").read_text(encoding="utf-8")

    for route in (
        "/product",
        "/capability",
        "/operation",
        "/control-plane",
        "/jeeves-workbench",
    ):
        assert f"path: '{route}'" in registry


def test_application_probe_includes_aggregate_readiness(monkeypatch):
    from skeleton.app.assembly import load_manifest
    from skeleton.app.health import ProbeResult, probe_application

    seen = []

    def fake_probe_url(service, *, timeout):
        seen.append((service.name, service.health_path, timeout))
        return ProbeResult(service.name, service.public_url, True, 200, "healthy")

    def fake_probe_http(name, url, *, timeout):
        seen.append((name, url, timeout))
        return ProbeResult(name, url, True, 200, "healthy")

    monkeypatch.setattr("skeleton.app.health.probe_url", fake_probe_url)
    monkeypatch.setattr("skeleton.app.health.probe_http", fake_probe_http)

    manifest = load_manifest()
    results = probe_application(manifest=manifest, timeout=1.5)

    assert [item.service for item in results][-1] == "application"
    assert (
        "application",
        "http://localhost:8001/api/app/ready",
        1.5,
    ) in seen
