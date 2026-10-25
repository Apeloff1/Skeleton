"""Provider and background publication keep the captured project authority."""
import asyncio
from types import SimpleNamespace

from fastapi import HTTPException
import pytest

from routes import playable
from core import engine_chat


SCOPE = {"tenant_id": "tenant-a", "owner_id": "alice@example.test"}


class _Jobs:
    def __init__(self):
        self.calls = []
    async def update_one(self, *args, **kwargs):
        self.calls.append((args, kwargs))


@pytest.mark.asyncio
async def test_each_model_fallback_reauthorizes_and_binds_engine_identity(monkeypatch):
    admissions, constructed = [], []
    monkeypatch.setattr(playable, "project_identity", lambda: dict(SCOPE))
    monkeypatch.setattr(playable, "reauthorize_project_principal", lambda **kwargs: admissions.append(kwargs))
    class Chat:
        def __init__(self, **kwargs):
            constructed.append(kwargs)
        def with_model(self, provider, model):
            self.model = model
            return self
        async def send_message(self, message):
            if self.model == "first":
                raise RuntimeError("provider unavailable")
            return "bounded result"
    monkeypatch.setattr(engine_chat, "EngineChat", Chat)
    result = await playable._llm_async("private project", "Bounded project instruction", ["first", "second"])
    assert result["content"] == "bounded result"
    assert admissions == [{"mutate": True, "sources": True}] * 3
    assert len(constructed) == 2
    for kwargs in constructed:
        assert kwargs["tenant_id"] == SCOPE["tenant_id"]
        assert kwargs["actor_id"] == SCOPE["owner_id"]
        assert kwargs["data_class"] == "confidential"
        assert kwargs["instruction_policy"].policy_id == "backend.playable.generation"


@pytest.mark.asyncio
@pytest.mark.parametrize("revoke_on", [1, 2])
async def test_revoked_model_attempt_is_not_converted_into_provider_fallback(monkeypatch, revoke_on):
    attempts, constructed = [], []
    monkeypatch.setattr(playable, "project_identity", lambda: dict(SCOPE))
    def reauthorize(**kwargs):
        attempts.append(kwargs)
        if len(attempts) == revoke_on:
            raise HTTPException(403, "Authority revoked")
    monkeypatch.setattr(playable, "reauthorize_project_principal", reauthorize)
    class Chat:
        def __init__(self, **kwargs):
            constructed.append(kwargs)
        def with_model(self, *args):
            return self
        async def send_message(self, message):
            raise RuntimeError("provider unavailable")
    monkeypatch.setattr(engine_chat, "EngineChat", Chat)
    with pytest.raises(HTTPException) as error:
        await playable._llm_async("private", "Bounded instruction", ["first", "second", "third"])
    assert error.value.status_code == 403
    assert len(constructed) == revoke_on - 1


@pytest.mark.asyncio
@pytest.mark.parametrize("revoke_on", [1, 2])
async def test_background_job_does_not_run_or_publish_after_authority_revocation(monkeypatch, revoke_on):
    jobs, checkpoints, ran = _Jobs(), [], []
    monkeypatch.setattr(playable, "_db", SimpleNamespace(playable_jobs=jobs))
    async def reauthorize(**kwargs):
        checkpoints.append(kwargs)
        if len(checkpoints) == revoke_on:
            raise HTTPException(403, "Authority revoked")
    monkeypatch.setattr(playable, "reauthorize_project_context", reauthorize)
    async def work():
        ran.append(True)
        return {"playable_id": "new", "content": "PRIVATE-CANARY"}
    pending = work()
    with pytest.raises(HTTPException):
        await playable._run_job("owned-job", pending)
    assert ran == ([] if revoke_on == 1 else [True])
    assert jobs.calls == []
    assert pending.cr_frame is None


@pytest.mark.asyncio
async def test_background_job_completion_cannot_create_a_missing_job(monkeypatch):
    jobs = _Jobs()
    monkeypatch.setattr(playable, "_db", SimpleNamespace(playable_jobs=jobs))
    async def reauthorize(**kwargs):
        return dict(SCOPE)
    monkeypatch.setattr(playable, "reauthorize_project_context", reauthorize)
    async def work():
        return {"playable_id": "new"}
    await playable._run_job("owned-job", work())
    assert jobs.calls == [(({"job_id": "owned-job"}, {"$set": {"playable_id": "new", "job_id": "owned-job", "job_status": "done"}}), {})]


@pytest.mark.asyncio
async def test_revocation_during_codegen_prevents_artifact_persistence(monkeypatch):
    checks, persisted = [], []
    async def reauthorize(**kwargs):
        checks.append(kwargs)
        if len(checks) == 2:
            raise HTTPException(403, "Authority revoked")
    async def codegen(*args):
        return {"html": "PRIVATE-CANARY"}
    async def insert(row):
        persisted.append(row)
    monkeypatch.setattr(playable, "reauthorize_project_context", reauthorize)
    monkeypatch.setattr(playable, "_codegen_quality_loop", codegen)
    monkeypatch.setattr(playable, "_db", SimpleNamespace(playables=SimpleNamespace(insert_one=insert)))
    with pytest.raises(HTTPException):
        await playable._persist("private", "title", "genre", "brief", "", "", "")
    assert persisted == []


@pytest.mark.asyncio
async def test_creator_spoof_fails_before_preferences_or_codegen(monkeypatch):
    async def reauthorize(**kwargs):
        return dict(SCOPE)
    monkeypatch.setattr(playable, "reauthorize_project_context", reauthorize)
    monkeypatch.setattr(playable, "project_identity", lambda: dict(SCOPE))
    async def forbidden(*args):
        pytest.fail("spoofed creator reached private source retrieval")
    monkeypatch.setattr(playable, "_resolve_brief", forbidden)
    with pytest.raises(HTTPException) as error:
        await playable._do_generate("valid brief", "", "", creator_id="bob@example.test")
    assert error.value.status_code == 403


@pytest.mark.asyncio
async def test_import_refreshes_captured_source_before_codegen(monkeypatch):
    async def reauthorize(**kwargs):
        return dict(SCOPE)
    async def missing_source(bid):
        assert bid == "removed-build"
        return {}
    monkeypatch.setattr(playable, "reauthorize_project_context", reauthorize)
    monkeypatch.setattr(playable, "_get_build", missing_source)
    async def forbidden(*args):
        pytest.fail("removed source reached codegen")
    monkeypatch.setattr(playable, "_persist", forbidden)
    with pytest.raises(HTTPException) as error:
        await playable._do_import({"build_id": "removed-build", "description": "PRIVATE-CANARY"}, "fast")
    assert error.value.status_code == 404
