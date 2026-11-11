"""Production SCIM and enterprise token admission must never inherit dev mode."""
from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException

from gameforge.enterprise import auth as auth_mod
from gameforge.api import scim as api


@pytest.fixture(autouse=True)
def no_environment_leaks(monkeypatch):
    for name in ("ENVIRONMENT", "APP_ENV", "GAMEFORGE_DEV_OPEN", "GAMEFORGE_API_TOKEN", "GAMEFORGE_SCIM_WEBHOOK_SECRET"):
        monkeypatch.delenv(name, raising=False)


@pytest.mark.parametrize("environment", ["production", "prod", "staging", "stage", "preview"])
def test_production_environment_disables_anonymous_admin_and_default_dev_token(
    monkeypatch, environment,
):
    monkeypatch.setenv("ENVIRONMENT", environment)
    monkeypatch.setenv("GAMEFORGE_DEV_OPEN", "1")
    monkeypatch.setenv("GAMEFORGE_API_TOKEN", "dev")
    service = auth_mod.AuthService()
    assert service.dev_open is False
    assert service.api_token is None
    for bearer in (None, "Bearer dev", "Bearer wrong"):
        with pytest.raises(HTTPException) as error:
            asyncio.run(service.resolve(bearer, "admin-spoof"))
        assert error.value.status_code == 401


def test_production_real_service_token_cannot_spoof_user_id(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("GAMEFORGE_API_TOKEN", "long-private-service-secret")
    service = auth_mod.AuthService()
    principal = asyncio.run(service.resolve(
        "Bearer long-private-service-secret", "system-root-owner"
    ))
    assert principal.auth_method == "api_token"
    assert principal.user_id == "api-token-user"
    assert principal.user_id != "system-root-owner"
    with pytest.raises(HTTPException) as error:
        asyncio.run(service.resolve("Bearer long-private-service-secret-invalid"))
    assert error.value.status_code == 401


def test_development_preserves_explicit_local_workflow(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "development")
    service = auth_mod.AuthService()
    assert service.dev_open
    principal = asyncio.run(service.resolve(x_user_id="local"))
    assert principal.auth_method == "dev_open"
    assert principal.user_id == "local"


def test_production_oidc_claims_require_stable_subject(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    service = auth_mod.AuthService()

    class FakeOIDC:
        async def validate(self, _token):
            return {"roles": ["viewer"], "sub": None}

    service.oidc = FakeOIDC()
    with pytest.raises(HTTPException) as error:
        asyncio.run(service.resolve("Bearer external-token"))
    assert error.value.status_code == 401


def test_scim_secret_is_checked_in_constant_time_and_never_downgrades(monkeypatch):
    monkeypatch.setenv("GAMEFORGE_SCIM_WEBHOOK_SECRET", "operator-secret")
    assert api._secret_ok("operator-secret") is True
    assert api._secret_ok(None) is False
    with pytest.raises(HTTPException) as error:
        api._secret_ok("wrong")
    assert error.value.status_code == 401


def test_missing_scim_key_refuses_supplied_credentials():
    assert api._secret_ok(None) is False
    with pytest.raises(HTTPException) as error:
        api._secret_ok("dev")
    assert error.value.status_code == 401


def test_scim_never_serializes_backend_exception_into_api_response(monkeypatch):
    class FailingDirectory:
        async def create_or_upsert_user(self, *_args, **_kwargs):
            raise RuntimeError("private database credential leak")

    class Principal:
        user_id = "admin"

    monkeypatch.setattr(api, "directory", FailingDirectory())
    monkeypatch.setattr(api, "_authorize_scim_write", lambda *_: "operator")
    with pytest.raises(HTTPException) as error:
        asyncio.run(api.scim_create_user(
            {"tenant_id": "blue", "userName": "alice"},
            x_scim_secret=None, principal=Principal(),
        ))
    assert error.value.status_code == 400
    assert "private" not in str(error.value.detail)
