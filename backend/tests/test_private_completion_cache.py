"""Private response projections partition exact scope and classification."""
from types import SimpleNamespace

import pytest

from routes import llm_router


@pytest.fixture
def completion_boundary(monkeypatch):
    dispatched = []
    monkeypatch.setattr(llm_router, "_CACHE", llm_router._LRUCache(64, 3600))
    monkeypatch.setattr(llm_router.EngineClient, "from_env", lambda: object())
    async def catalog(*args, **kwargs):
        return {"catalog": "current"}
    async def journal(*args):
        return None
    monkeypatch.setattr(llm_router, "model_catalog", catalog)
    monkeypatch.setattr(llm_router, "catalog_digest", lambda catalog: "current-digest")
    monkeypatch.setattr(llm_router, "resolve_selection", lambda *args, **kwargs: {})
    monkeypatch.setattr(llm_router, "cooperation_context_selection", lambda *args, **kwargs: {})
    monkeypatch.setattr(llm_router, "context_budget_for_selection", lambda *args, **kwargs: None)
    monkeypatch.setattr(llm_router, "_log_call", journal)
    class Chat:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
        def with_selection(self, *args):
            return self
        def with_cooperation(self, *args):
            return self
        def with_max_tokens(self, *args):
            return self
        async def send_message(self, message):
            dispatched.append(self.kwargs)
            return SimpleNamespace(text=f"PRIVATE RESULT {len(dispatched)}", operation_id="operation",
                                   execution_id="execution", context_id="context", context_digest="digest",
                                   provider_receipts=(), verification="proposed")
    monkeypatch.setattr(llm_router, "EngineChat", Chat)
    return dispatched


@pytest.mark.asyncio
async def test_cache_partitions_actor_tenant_class_and_exact_request(completion_boundary):
    calls = completion_boundary
    request = {"task": "creative", "prompt": "Private Game()", "system": "bounded instruction",
               "tenant_id": "tenant-a", "actor_id": "alice", "data_class": "confidential",
               "session_id": "same-session", "provider_id": "provider", "model_id": "model",
               "max_output_tokens": 128}
    first = await llm_router.route_complete(**request)
    repeated = await llm_router.route_complete(**request)
    assert first["content"] == repeated["content"] and repeated["cached"] is True
    variants = [{"actor_id": "bob"}, {"tenant_id": "tenant-b"}, {"data_class": "internal"},
                {"prompt": "private game()"}, {"session_id": "other-session"},
                {"max_output_tokens": 129}, {"model_id": "other-model"}]
    for index, change in enumerate(variants, 2):
        result = await llm_router.route_complete(**{**request, **change})
        assert not result["cached"] and result["content"] == f"PRIVATE RESULT {index}"
    assert len(calls) == len(variants) + 1
    assert calls[0]["tenant_id"] == "tenant-a" and calls[0]["actor_id"] == "alice"
    assert calls[0]["data_class"] == "confidential"
    assert calls[3]["data_class"] == "internal"


@pytest.mark.asyncio
@pytest.mark.parametrize("classification", ["", "CONFIDENTIAL", "secret", None, 1, []])
async def test_invalid_classification_cannot_dispatch_or_hit_cache(completion_boundary, classification):
    result = await llm_router.route_complete("creative", "Private game", data_class=classification)
    assert result["error_code"] == "request_invalid"
    assert completion_boundary == [] and not llm_router._CACHE._d
