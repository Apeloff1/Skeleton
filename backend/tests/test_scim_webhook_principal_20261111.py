"""Machine SCIM secret authority must not require a separate bearer token."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from gameforge.api import scim


def test_valid_webhook_secret_admits_service_identity_without_bearer(monkeypatch):
    monkeypatch.setenv("GAMEFORGE_SCIM_WEBHOOK_SECRET", "test-secret-credential")

    async def bearer_forbidden(**_kwargs):
        raise AssertionError("valid signed webhook must not require bearer")

    monkeypatch.setattr(scim, "get_principal", bearer_forbidden)
    principal = asyncio.run(scim.get_scim_webhook_principal(
        x_scim_secret="test-secret-credential",
        authorization=None, x_user_id=None,
    ))
    assert principal.user_id == "scim-webhook"
    assert principal.auth_method == "scim_secret"


def test_wrong_webhook_secret_cannot_fall_back_to_other_credentials(monkeypatch):
    monkeypatch.setenv("GAMEFORGE_SCIM_WEBHOOK_SECRET", "expected-secret")
    called = []

    async def bearer(*_args, **_kwargs):
        called.append("called")
        return SimpleNamespace(user_id="forged", auth_method="dev_open")

    monkeypatch.setattr(scim, "get_principal", bearer)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(scim.get_scim_webhook_principal(
            x_scim_secret="wrong-secret",
            authorization="Bearer known-token", x_user_id="owner",
        ))
    assert exc.value.status_code == 401
    assert not called


def test_webhook_without_machine_secret_retains_standard_bearer_auth(monkeypatch):
    monkeypatch.delenv("GAMEFORGE_SCIM_WEBHOOK_SECRET", raising=False)
    calls = []

    async def bearer(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(user_id="viewer", auth_method="oidc")

    monkeypatch.setattr(scim, "get_principal", bearer)
    principal = asyncio.run(scim.get_scim_webhook_principal(
        x_scim_secret=None, authorization="Bearer oidc-token", x_user_id=None,
    ))
    assert principal.user_id == "viewer"
    assert calls == [{"authorization": "Bearer oidc-token", "x_user_id": None}]


def test_signed_webhook_processes_events_without_caller_identity(monkeypatch):
    monkeypatch.setenv("GAMEFORGE_SCIM_WEBHOOK_SECRET", "valid-machine-secret")
    recorded = []

    class FakeEvent:
        tenant_id = "red"
        user_id = "scim-user"
        op = SimpleNamespace(value="update")

    class Processor:
        def normalize_payload(self, payload):
            assert payload["events"] == 1
            return [FakeEvent()]

        async def apply(self, event, *, actor_user_id):
            recorded.append((event.tenant_id, actor_user_id))
            return {"status": "ok"}

    monkeypatch.setattr(scim, "processor", Processor())
    principal = asyncio.run(scim.get_scim_webhook_principal(
        x_scim_secret="valid-machine-secret", authorization=None, x_user_id=None,
    ))
    result = asyncio.run(scim.scim_webhook(
        {"events": 1},
        x_scim_secret="valid-machine-secret",
        principal=principal,
    ))
    assert result["processed"] == 1
    assert recorded == [("red", "scim-webhook")]
