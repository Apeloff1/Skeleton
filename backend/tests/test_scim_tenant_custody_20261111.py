"""SCIM least-privilege regressions: shared user IDs cannot cross tenant scopes."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from gameforge.api import scim as route
from gameforge.enterprise.scim_users import ScimUserDirectory
from gameforge.enterprise.tenancy import MemberRole, Tenant, TenantRegistry


@pytest.fixture
def tenants(monkeypatch):
    registry = TenantRegistry()
    registry.upsert(Tenant(
        tenant_id="blue",
        name="Blue",
        members={"alice": MemberRole.ADMIN, "shared": MemberRole.VIEWER},
    ))
    registry.upsert(Tenant(
        tenant_id="red",
        name="Red",
        members={
            "bob": MemberRole.ADMIN,
            "shared": MemberRole.OPERATOR,
            "red-secret-user": MemberRole.VIEWER,
        },
    ))
    monkeypatch.setattr(route, "TENANT_REGISTRY", registry)
    directory = ScimUserDirectory(registry)
    monkeypatch.setattr(route, "directory", directory)
    monkeypatch.delenv("GAMEFORGE_SCIM_WEBHOOK_SECRET", raising=False)
    return directory, registry


def test_user_read_isolated_when_same_user_exists_in_multiple_tenants(tenants):
    directory, _ = tenants
    blue = directory.get_user("shared", tenant_id="blue")
    red = directory.get_user("shared", tenant_id="red")
    assert blue["tenants"] == ["blue"]
    assert red["tenants"] == ["red"]
    assert blue["roles"][0]["value"] == "viewer"
    assert red["roles"][0]["value"] == "operator"
    assert directory.get_user("red-secret-user", tenant_id="blue") is None


def test_nonsecret_scim_access_requires_explicit_authorized_tenant(tenants):
    identity = SimpleNamespace(user_id="alice")
    assert route._authorize_scim_write(None, identity, "blue") == "alice"
    for tenant_id in (None, "", "red", "does-not-exist"):
        with pytest.raises(HTTPException) as error:
            route._authorize_scim_write(None, identity, tenant_id)
        assert error.value.status_code == 403


def test_scim_users_list_and_get_do_not_expose_other_tenant_members(tenants):
    identity = SimpleNamespace(user_id="alice")
    users = asyncio.run(route.scim_list_users(
        tenant_id="blue",
        x_scim_secret=None,
        principal=identity,
        count=100,
        startIndex=1,
        filter=None,
    ))
    assert "red-secret-user" not in str(users)
    assert users["totalResults"] == 2
    blue_user = asyncio.run(route.scim_get_user(
        "shared",
        tenant_id="blue",
        x_scim_secret=None,
        principal=identity,
    ))
    assert blue_user["tenants"] == ["blue"]
    with pytest.raises(HTTPException) as error:
        asyncio.run(route.scim_get_user(
            "red-secret-user",
            tenant_id="blue",
            x_scim_secret=None,
            principal=identity,
        ))
    assert error.value.status_code == 404


def test_scim_mutations_cannot_implicitly_pick_a_users_other_tenant(tenants):
    directory, _ = tenants
    with pytest.raises(ValueError, match="tenant_id"):
        asyncio.run(directory.patch_user(
            "red-secret-user",
            {"active": False},
            actor="alice",
        ))
    with pytest.raises(ValueError, match="tenant_id"):
        asyncio.run(directory.create_or_upsert_user(
            {"id": "new-user"},
            actor="alice",
        ))


def test_cross_tenant_patch_fails_before_entering_directory(tenants, monkeypatch):
    called = []

    async def forbidden(*args, **kwargs):
        called.append((args, kwargs))
        return {"ok": True}

    monkeypatch.setattr(route.directory, "patch_user", forbidden)
    with pytest.raises(HTTPException) as error:
        asyncio.run(route.scim_patch_user(
            "shared",
            payload={"tenant_id": "red", "active": False},
            principal=SimpleNamespace(user_id="alice"),
            x_scim_secret=None,
        ))
    assert error.value.status_code == 403
    assert called == []
