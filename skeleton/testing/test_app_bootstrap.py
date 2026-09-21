from __future__ import annotations

from skeleton.app.bootstrap import public_bootstrap_payload


def test_public_bootstrap_is_dependency_closed_and_sanitized():
    payload = public_bootstrap_payload()

    assert payload["schema_version"] == 1
    assert payload["application"]["name"] == "Skeleton"
    assert payload["application"]["version"] == "16.0.0"
    assert payload["contract"]["bootstrap"] == "/api/app/bootstrap"
    assert payload["contract"]["status"] == "/api/app/status"
    assert payload["contract"]["ready"] == "/api/app/ready"

    services = {item["name"]: item for item in payload["services"]}
    assert {"frontend", "backend", "skeleton", "mongo"}.issubset(services)
    assert services["backend"]["health_path"] == "/api/health"
    assert services["backend"]["ingress_prefix"] == "/api"
    assert services["skeleton"]["health_path"] == "/api/v1/health/live"
    assert services["skeleton"]["ingress_prefix"] == "/api/v1"
    assert services["frontend"]["ingress_prefix"] == "/"

    default = payload["profiles"]["default"]
    assert set(default["services"]) == {"mongo", "backend", "skeleton", "frontend"}
    assert default["layers"][0] == ["mongo"]
    assert default["layers"][-1] == ["frontend"]

    serialized = repr(payload)
    for forbidden in ("required_env", "optional_env", "public_url", "container_port", "entrypoint"):
        assert forbidden not in serialized


def test_public_bootstrap_full_profile_contains_default_profile():
    payload = public_bootstrap_payload()

    default = set(payload["profiles"]["default"]["services"])
    full = set(payload["profiles"]["full"]["services"])

    assert default.issubset(full)
    assert "chroma" in full


def test_three_layer_bootstrap_contract_is_wired():
    from pathlib import Path

    from skeleton.app.assembly import find_repo_root

    root = find_repo_root(Path(__file__))
    route = (root / "backend/routes/app_runtime.py").read_text(encoding="utf-8")
    registry = (root / "backend/core/routes_registry.py").read_text(encoding="utf-8")
    client = (root / "frontend/src/product/appBootstrapClient.ts").read_text(encoding="utf-8")
    health = (root / "frontend/src/product/appHealthClient.ts").read_text(encoding="utf-8")

    assert 'APIRouter(prefix=_MANIFEST.public_contract["prefix"]' in route
    assert '@router.get(_MANIFEST.public_contract["bootstrap"])' in route
    assert '@router.get(_MANIFEST.public_contract["status"])' in route
    assert '@router.get(_MANIFEST.public_contract["ready"])' in route
    assert '("routes.app_runtime",' in registry
    assert "DEFAULT_APP_BOOTSTRAP_PATH = '/api/app/bootstrap'" in client
    assert "getAppBootstrap" in health
    assert "bootstrapService" in health


def test_legacy_backend_health_exposes_canonical_identity_compatibly():
    from pathlib import Path

    from skeleton.app.assembly import find_repo_root

    root = find_repo_root(Path(__file__))
    health = (root / "backend/routes/health.py").read_text(encoding="utf-8")

    assert 'SYSTEM_VERSION = "11.0.0"' in health
    assert '"canonical_application": _canonical_application()' in health
    assert "public_bootstrap_payload" in health


def test_manifest_ingress_prefixes_are_validated():
    import json
    from copy import deepcopy
    from importlib import resources

    import pytest

    from skeleton.app.assembly import parse_manifest

    payload = json.loads(resources.files("skeleton.app").joinpath("manifest.json").read_text())
    parsed = parse_manifest(payload)
    assert parsed.service("backend").ingress_prefix == "/api"
    assert parsed.service("skeleton").ingress_prefix == "/api/v1"

    invalid = deepcopy(payload)
    next(item for item in invalid["services"] if item["name"] == "backend")["ingress_prefix"] = "api"
    with pytest.raises(ValueError, match="must start"):
        parse_manifest(invalid)

    escaped = deepcopy(payload)
    next(item for item in escaped["services"] if item["name"] == "backend")["health_path"] = "/other/health"
    with pytest.raises(ValueError, match="health_path must live under"):
        parse_manifest(escaped)

    duplicate = deepcopy(payload)
    next(item for item in duplicate["services"] if item["name"] == "skeleton")["ingress_prefix"] = "/api"
    with pytest.raises(ValueError, match="shared"):
        parse_manifest(duplicate)


def test_aggregate_runtime_status_includes_engine_and_state():
    from pathlib import Path

    from skeleton.app.assembly import find_repo_root

    root = find_repo_root(Path(__file__))
    route = (root / "backend/routes/app_runtime.py").read_text(encoding="utf-8")
    client = (root / "frontend/src/product/appBootstrapClient.ts").read_text(encoding="utf-8")
    shell = (root / "frontend/app/product.tsx").read_text(encoding="utf-8")

    assert "async def _probe_mongo" in route
    assert 'core_db.command("ping")' in route
    assert "asyncio.gather(" in route
    assert '"name": "mongo"' in route
    assert "'backend' | 'skeleton' | 'mongo'" in client
    assert "Mongo state" in shell


def test_backend_public_identity_converges_on_skeleton():
    from pathlib import Path

    from skeleton.app.assembly import find_repo_root

    root = find_repo_root(Path(__file__))
    health = (root / "backend/routes/health.py").read_text(encoding="utf-8")
    server = (root / "backend/server.py").read_text(encoding="utf-8")

    assert '"name": "Skeleton Application API"' in health
    assert '"legacy_name": "CodeDock Quantum Nexus"' in health
    assert 'title="Skeleton Application API"' in server
    assert 'logging.getLogger("Skeleton.Backend")' in server


def test_manifest_public_contract_is_fail_closed():
    import json
    from copy import deepcopy
    from importlib import resources

    import pytest

    from skeleton.app.assembly import parse_manifest

    payload = json.loads(resources.files("skeleton.app").joinpath("manifest.json").read_text())
    manifest = parse_manifest(payload)
    assert manifest.contract_path("bootstrap") == "/api/app/bootstrap"
    assert manifest.contract_path("status") == "/api/app/status"
    assert manifest.contract_path("ready") == "/api/app/ready"

    outside_backend = deepcopy(payload)
    outside_backend["app"]["public_contract"]["prefix"] = "/control"
    with pytest.raises(ValueError, match="inside backend ingress"):
        parse_manifest(outside_backend)

    duplicate_route = deepcopy(payload)
    duplicate_route["app"]["public_contract"]["ready"] = "/status"
    with pytest.raises(ValueError, match="routes must be unique"):
        parse_manifest(duplicate_route)

    self_dependency = deepcopy(payload)
    next(item for item in self_dependency["services"] if item["name"] == "backend")["depends_on"].append("backend")
    with pytest.raises(ValueError, match="cannot depend on itself"):
        parse_manifest(self_dependency)


def test_frontend_health_fallback_is_fail_closed():
    from pathlib import Path

    from skeleton.app.assembly import find_repo_root

    root = find_repo_root(Path(__file__))
    health = (root / "frontend/src/product/appHealthClient.ts").read_text(encoding="utf-8")
    shell = (root / "frontend/app/product.tsx").read_text(encoding="utf-8")

    assert "whole-application verdict remains fail-closed" in health
    assert "contractSource: bootstrap ? 'bootstrap-fallback' : 'static-fallback'" in health
    assert "ok: false" in health
    assert "'Partial'" in shell


def test_product_shell_uses_single_runtime_readiness_source():
    from pathlib import Path

    from skeleton.app.assembly import find_repo_root

    root = find_repo_root(Path(__file__))
    product = (root / "frontend/app/product.tsx").read_text(encoding="utf-8")
    health = (root / "frontend/src/product/appHealthClient.ts").read_text(encoding="utf-8")
    runtime = (root / "backend/routes/app_runtime.py").read_text(encoding="utf-8")

    assert "getProductReadiness" not in product
    assert "health?.product?.available" in product
    assert "product: runtime.product" in health
    assert "public_readiness()" in runtime
    assert '"product": product_readiness' in runtime
