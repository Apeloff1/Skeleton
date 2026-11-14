"""Project access cleanup across normal and cross-task async-generator finalization.

No DB, network or external auth: focused lifecycle regression for FastAPI's
async yield-dependency cleanup. A request must never use a scope from another.
"""
from __future__ import annotations

import asyncio
from contextvars import Context
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from routes import playable_access as access


def _dependency(monkeypatch):
    monkeypatch.setattr(
        access.auth, "require_authenticated_identity",
        lambda user: {"tenant_id": user["tenant_id"], "owner_id": user["owner_id"]},
    )
    request = SimpleNamespace(
        method="GET", path_params={}, query_params={}, headers={},
    )
    response = SimpleNamespace(headers={})
    user = {
        "role": "viewer", "tenant_id": "test-tenant",
        "owner_id": "test-owner",
    }
    return access.project_request_access(
        request, response, user=user, token="test-principal",
    )


@pytest.mark.asyncio
async def test_normal_generator_cleanup_restores_previous_request_context(monkeypatch):
    baseline = access._current.get()
    dependency = _dependency(monkeypatch)
    try:
        await dependency.__anext__()
        assert access.project_identity() == {
            "tenant_id": "test-tenant", "owner_id": "test-owner",
        }
        await dependency.aclose()
        assert access._current.get() is baseline
    finally:
        access._current.set(baseline)


@pytest.mark.asyncio
async def test_async_generator_cleanup_in_fresh_task_context_is_fail_closed(monkeypatch):
    baseline = access._current.get()
    dependency = _dependency(monkeypatch)
    try:
        await dependency.__anext__()
        assert access.project_identity()["owner_id"] == "test-owner"

        async def close_in_isolated_context():
            with pytest.raises(HTTPException) as missing:
                access.project_identity()
            assert missing.value.status_code == 401
            await dependency.aclose()
            assert access._current.get() is None

        # Reproduce the ContextVar.reset(token) cross-context failure seen in
        # worker cancellation / async_generator_athrow cleanup on CI.
        await asyncio.create_task(close_in_isolated_context(), context=Context())
    finally:
        # Closing in another task cannot mutate the originating task's
        # immutable Context; a completed request task is independently ended.
        access._current.set(baseline)
