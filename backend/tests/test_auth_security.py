import ast
from pathlib import Path

import pytest

from core.auth_security import (
    AuthConfigurationError,
    auth_enforced,
    resolve_jwt_secret,
    resolve_seed_admin,
    resolve_session_api,
    security_summary,
)


STRONG_SECRET = "s" * 48
STRONG_PASSWORD = "Correct-Horse-Battery-Staple-2026"


def test_auth_enforcement_defaults_closed_in_production_but_open_in_local_dev():
    assert auth_enforced({}) is False
    assert auth_enforced({"APP_ENV": "development"}) is False
    assert auth_enforced({"APP_ENV": "production"}) is True
    assert auth_enforced({"ENVIRONMENT": "prod"}) is True


def test_explicit_enforcement_flag_overrides_environment_and_rejects_typos():
    assert auth_enforced({"APP_ENV": "production", "GAMEFORGE_AUTH_ENFORCE": "0"}) is False
    assert auth_enforced({"APP_ENV": "development", "GAMEFORGE_AUTH_ENFORCE": "yes"}) is True
    with pytest.raises(AuthConfigurationError, match="boolean flag"):
        auth_enforced({"GAMEFORGE_AUTH_ENFORCE": "sometimes"})


def test_production_requires_configured_strong_jwt_secret():
    with pytest.raises(AuthConfigurationError, match="required"):
        resolve_jwt_secret({"APP_ENV": "production"})
    with pytest.raises(AuthConfigurationError, match="at least"):
        resolve_jwt_secret(
            {"APP_ENV": "production", "GAMEFORGE_JWT_SECRET": "weak"}
        )
    assert (
        resolve_jwt_secret(
            {"APP_ENV": "production", "GAMEFORGE_JWT_SECRET": STRONG_SECRET}
        )
        == STRONG_SECRET
    )


def test_development_uses_ephemeral_secret_instead_of_public_fallback():
    first = resolve_jwt_secret({}, development_secret="a" * 48)
    second = resolve_jwt_secret({}, development_secret="b" * 48)
    assert first != second
    assert first == "a" * 48
    assert second == "b" * 48
    with pytest.raises(AuthConfigurationError, match="unexpectedly weak"):
        resolve_jwt_secret({}, development_secret="short")


def test_seed_admin_is_opt_in_paired_and_strong():
    assert resolve_seed_admin({}) is None
    with pytest.raises(AuthConfigurationError, match="set together"):
        resolve_seed_admin({"GAMEFORGE_SEED_ADMIN_EMAIL": "admin@example.com"})
    with pytest.raises(AuthConfigurationError, match="set together"):
        resolve_seed_admin({"GAMEFORGE_SEED_ADMIN_PASSWORD": STRONG_PASSWORD})
    with pytest.raises(AuthConfigurationError, match="valid bootstrap email"):
        resolve_seed_admin(
            {
                "GAMEFORGE_SEED_ADMIN_EMAIL": "not-an-email",
                "GAMEFORGE_SEED_ADMIN_PASSWORD": STRONG_PASSWORD,
            }
        )
    with pytest.raises(AuthConfigurationError, match="at least"):
        resolve_seed_admin(
            {
                "GAMEFORGE_SEED_ADMIN_EMAIL": "admin@example.com",
                "GAMEFORGE_SEED_ADMIN_PASSWORD": "short",
            }
        )

    seed = resolve_seed_admin(
        {
            "GAMEFORGE_SEED_ADMIN_EMAIL": "Admin@Example.COM",
            "GAMEFORGE_SEED_ADMIN_PASSWORD": STRONG_PASSWORD,
        }
    )
    assert seed is not None
    assert seed.email == "admin@example.com"
    assert seed.password == STRONG_PASSWORD
    assert STRONG_PASSWORD not in repr(seed)


def test_session_exchange_requires_https_when_auth_is_enforced():
    assert resolve_session_api({}).startswith("https://")
    assert (
        resolve_session_api(
            {"APP_ENV": "development", "EMERGENT_SESSION_API": "http://localhost/session"}
        )
        == "http://localhost/session"
    )
    with pytest.raises(AuthConfigurationError, match="must use HTTPS"):
        resolve_session_api(
            {"APP_ENV": "production", "EMERGENT_SESSION_API": "http://localhost/session"}
        )
    with pytest.raises(AuthConfigurationError, match="must not embed credentials"):
        resolve_session_api(
            {"EMERGENT_SESSION_API": "https://user:pass@example.com/session"}
        )


def test_security_summary_never_exposes_secret_or_seed_password():
    environ = {
        "APP_ENV": "production",
        "GAMEFORGE_JWT_SECRET": STRONG_SECRET,
        "GAMEFORGE_SEED_ADMIN_EMAIL": "admin@example.com",
        "GAMEFORGE_SEED_ADMIN_PASSWORD": STRONG_PASSWORD,
    }
    summary = security_summary(environ)
    assert summary == {
        "enforced": True,
        "jwt_secret_configured": True,
        "development_secret_ephemeral": False,
        "seed_admin_configured": True,
        "session_api_scheme": "https",
    }
    rendered = repr(summary)
    assert STRONG_SECRET not in rendered
    assert STRONG_PASSWORD not in rendered


def test_active_auth_route_uses_shared_fail_closed_configuration_contract():
    route_path = Path(__file__).parents[1] / "routes" / "gameforge_auth.py"
    source = route_path.read_text(encoding="utf-8")

    assert "from core.auth_security import" in source
    assert "resolve_jwt_secret" in source
    assert "resolve_seed_admin" in source
    assert "resolve_session_api" in source
    assert "auth_enforced" in source

    # The active HTTP surface must never regress to the retired public defaults.
    assert "dev-insecure-secret-change-me" not in source
    assert "GameForge#Admin2026" not in source
    assert 'SEED_ADMIN_EMAIL = "admin@gameforge.io"' not in source


def test_active_auth_route_retires_persisted_legacy_bootstrap_state():
    route_path = Path(__file__).parents[1] / "routes" / "gameforge_auth.py"
    source = route_path.read_text(encoding="utf-8")

    assert '_LEGACY_PUBLIC_SEED_EMAIL = "admin@gameforge.io"' in source
    assert '"security_migration": "legacy_public_seed_disabled"' in source
    assert "verify_password(" in source
    assert "seed.password" in source
    assert '"$setOnInsert"' in source
    assert 'detail=f"Auth provider unreachable' not in source
    assert 'detail="Auth provider unreachable"' in source


def _decorated_route_roles(source: str) -> dict[str, str]:
    """Extract role dependencies from router.get/post decorators without imports."""
    roles: dict[str, str] = {}
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call):
                continue
            if not isinstance(decorator.func, ast.Attribute):
                continue
            if decorator.func.attr not in {"get", "post"}:
                continue
            if not decorator.args or not isinstance(decorator.args[0], ast.Constant):
                continue
            route = decorator.args[0].value
            if not isinstance(route, str):
                continue
            for child in ast.walk(decorator):
                if not isinstance(child, ast.Call):
                    continue
                if not isinstance(child.func, ast.Name) or child.func.id != "require_role":
                    continue
                if not child.args or not isinstance(child.args[0], ast.Constant):
                    continue
                role = child.args[0].value
                if isinstance(role, str):
                    roles[route] = role
    return roles


def test_sensitive_telemetry_routes_use_shared_role_policy():
    telemetry_path = Path(__file__).parents[1] / "routes" / "telemetry.py"
    source = telemetry_path.read_text(encoding="utf-8")
    roles = _decorated_route_roles(source)

    expected = {
        "/telemetry/event": "viewer",
        "/telemetry/batch": "viewer",
        "/telemetry/last-crash": "viewer",
        "/telemetry/critical/recent": "admin",
        "/telemetry/recent": "admin",
        "/telemetry/sessions": "admin",
        "/telemetry/summary": "admin",
        "/security/audit": "admin",
        "/security/audit-summary": "admin",
        "/security/rate-limits": "admin",
        "/security/health": "admin",
    }
    assert {route: roles.get(route) for route in expected} == expected
