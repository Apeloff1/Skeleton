from __future__ import annotations

from skeleton.app.bootstrap import public_bootstrap_payload


def test_public_bootstrap_is_dependency_closed_and_sanitized():
    payload = public_bootstrap_payload()

    assert payload["schema_version"] == 1
    assert payload["application"]["name"] == "Skeleton"
    assert payload["application"]["version"] == "16"

    services = {item["name"]: item for item in payload["services"]}
    assert {"frontend", "backend", "skeleton", "mongo"}.issubset(services)
    assert services["backend"]["health_path"] == "/api/health"
    assert services["skeleton"]["health_path"] == "/api/v1/health/live"

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

    assert 'APIRouter(prefix="/api/app"' in route
    assert '@router.get("/bootstrap")' in route
    assert '("routes.app_runtime",' in registry
    assert "'/api/app/bootstrap'" in client
    assert "getAppBootstrap" in health
    assert "bootstrapService" in health


def test_legacy_backend_health_exposes_canonical_identity_compatibly():
    from pathlib import Path

    from skeleton.app.assembly import find_repo_root

    root = find_repo_root(Path(__file__))
    health = (root / "backend/routes/health.py").read_text(encoding="utf-8")

    assert 'SYSTEM_VERSION = "10.0.0"' in health
    assert '"canonical_application": _canonical_application()' in health
    assert "public_bootstrap_payload" in health
