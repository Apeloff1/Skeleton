"""Real typed planner schemas count against local prompt capacity before dispatch."""
import copy

import pytest

from core import game_studio_agent as studio
from core import model_catalog as catalog_module
from core.engine_client import EngineClient
from core.engine_text import EngineTextContextError, EngineTextRequest, execute_engine_text
from skeleton.ai.runtime.inference.llama_cpp import llama_cpp_prompt_tokens_upper_bound
from skeleton.ai.runtime.inference.local import LocalInferenceRequest


def _inventory():
    route = {"provider_id": "local", "model_id": "coder", "active": True, "selectable": True,
             "fallback": False, "execution_mode": "local", "activation": {"runtime_kind": "llama.cpp-cli"},
             "tokenizer": "utf8_bytes", "context_window": 12288, "max_output_tokens": 6144,
             "default_output_tokens": 2048, "supports_temperature": False}
    return {"schema_version": catalog_module.CATALOG_SCHEMA, "automatic_available": True,
            "available": True, "models": [route]}


def _setup(monkeypatch):
    client = object()
    monkeypatch.setattr(EngineClient, "from_env", classmethod(lambda cls: client))
    async def inventory(*args, **kwargs):
        return _inventory()
    monkeypatch.setattr(catalog_module, "model_catalog", inventory)
    return client


def _schema(allowed):
    forms = studio.studio_application_schemas()
    return forms, studio._planner_response_schema(
        allowed, payload_schemas=studio._planner_payload_schemas(forms, allowed, {}))


def _row():
    return {"goal": "Inspect and improve the current project", "execution_mode": "manual",
            "max_steps": 8, "cursor": 0, "max_model_calls": 4, "model_calls": 0,
            "max_jobs": 2, "jobs_started": 0, "project_id": "project", "head_version": 1,
            "max_output_tokens": 4096, "steps": []}


@pytest.mark.asyncio
async def test_large_real_schema_fails_before_planner_can_issue_a_model_request(monkeypatch):
    _setup(monkeypatch)
    allowed = {"lessons.search", "world.edit", "project.review", "project.export", "job.inspect"}
    forms, schema = _schema(allowed)
    request = LocalInferenceRequest(prompt="small goal", instructions=studio.PLANNER_SYSTEM,
                                    structured_output_schema=schema, max_output_tokens=4096)
    assert llama_cpp_prompt_tokens_upper_bound(request) + 4096 > 12288
    with pytest.raises(studio.GameLearningError) as failure:
        await studio._fit_planner_context({"tenant_id": "tenant", "owner_id": "owner"}, _row(),
                                          {"project": {}}, forms, allowed, "small goal",
                                          response_schema=schema)
    assert failure.value.code == "studio_planner_capacity"


@pytest.mark.asyncio
async def test_projection_respects_schema_bound_and_keeps_all_granted_operations(monkeypatch):
    _setup(monkeypatch)
    allowed = {"lessons.search"}
    forms, schema = _schema(allowed)
    original_schema = copy.deepcopy(schema)
    prompt, retained, receipt = await studio._fit_planner_context(
        {"tenant_id": "tenant", "owner_id": "owner"}, _row(), {"project": {}},
        forms, allowed, "x" * 5000, response_schema=schema)
    assert retained == allowed and receipt["projected"] is True
    assert schema == original_schema
    actual = llama_cpp_prompt_tokens_upper_bound(LocalInferenceRequest(
        prompt=prompt, instructions=studio.PLANNER_SYSTEM, structured_output_schema=schema))
    assert receipt["native_framed_input_upper_bound"] == actual
    assert actual <= receipt["input_capacity"]


@pytest.mark.asyncio
async def test_engine_text_rejects_schema_overflow_before_engine_execute(monkeypatch):
    import core.engine_text as engine_text
    class Client:
        config = type("Config", (), {"service_principal": "backend", "execution_timeout_s": 5})()
        async def execute(self, command):
            pytest.fail("oversized native request must not dispatch")
    async def inventory(*args, **kwargs):
        return _inventory()
    monkeypatch.setattr(engine_text, "model_catalog", inventory)
    schema = {"type": "object", "description": "x" * 7000}
    request = EngineTextRequest(instructions="Policy", prompt="Goal", idempotency_key="schema-bound",
                                structured_output_schema=schema, max_output_tokens=4096)
    with pytest.raises(EngineTextContextError):
        await execute_engine_text(request, client=Client())


def test_automatic_routing_accounts_for_declared_local_fallback_without_relabeling_hosted_selection():
    local = _inventory()["models"][0]
    local = {**local, "active": False, "fallback": True}
    hosted = {"provider_id": "openai", "model_id": "hosted", "active": True,
              "execution_mode": "hosted", "activation": None}
    catalog = {"models": [hosted, local]}
    assert catalog_module.selection_may_use_llama_cpp(catalog, {**hosted, "selection_mode": "automatic"})
    assert not catalog_module.selection_may_use_llama_cpp(catalog, {**hosted, "selection_mode": "explicit"})
    assert catalog_module.selection_may_use_llama_cpp(catalog, {**local, "selection_mode": "explicit"})


def test_explicit_hosted_primary_still_bounds_exact_local_cooperation_role():
    local = {**_inventory()["models"][0], "active": False}
    hosted = {**local, "provider_id": "openai", "model_id": "hosted", "active": True,
              "execution_mode": "hosted", "activation": None, "tokenizer": "approximate_text"}
    catalog = {**_inventory(), "models": [hosted, local]}
    primary = catalog_module.resolve_selection(catalog, provider_id="openai", model_id="hosted")
    policy = {"schema_version": "skeleton.ai.cooperation.v1", "roles": {
        "critique": {"provider_id": "local", "model_id": "coder"}}}
    projected = catalog_module.cooperation_context_selection(catalog, primary, policy, output_tokens=4096)
    assert catalog_module.selection_may_use_llama_cpp(catalog, projected, cooperation=policy)
    hosted_only = {**policy, "roles": {"critique": {"provider_id": "openai", "model_id": "hosted"}}}
    assert not catalog_module.selection_may_use_llama_cpp(catalog, primary, cooperation=hosted_only)


@pytest.mark.asyncio
async def test_engine_text_hosted_primary_local_review_bounds_schema_before_dispatch(monkeypatch):
    import core.engine_text as engine_text
    local = {**_inventory()["models"][0], "active": False}
    hosted = {**local, "provider_id": "openai", "model_id": "hosted", "active": True,
              "execution_mode": "hosted", "activation": None, "tokenizer": "approximate_text"}
    catalog = {**_inventory(), "models": [hosted, local]}
    class Client:
        config = type("Config", (), {"service_principal": "backend", "execution_timeout_s": 5})()
        async def execute(self, command):
            pytest.fail("oversized local review request must not dispatch")
    async def inventory(*args, **kwargs):
        return catalog
    monkeypatch.setattr(engine_text, "model_catalog", inventory)
    policy = {"schema_version": "skeleton.ai.cooperation.v1", "roles": {
        "critique": {"provider_id": "local", "model_id": "coder"}}}
    request = EngineTextRequest(instructions="Policy", prompt="Goal", idempotency_key="mixed-schema-bound",
                                provider_id="openai", model_id="hosted", cooperation=policy,
                                structured_output_schema={"type": "object", "description": "x" * 7000},
                                max_output_tokens=4096)
    with pytest.raises(EngineTextContextError):
        await execute_engine_text(request, client=Client())


@pytest.mark.asyncio
async def test_hosted_estimation_keeps_existing_behavior_without_claiming_native_frame(monkeypatch):
    _setup(monkeypatch)
    hosted = {**_inventory()["models"][0], "provider_id": "openai", "model_id": "hosted",
              "execution_mode": "hosted", "activation": None, "tokenizer": "approximate_text"}
    async def inventory(*args, **kwargs):
        return {**_inventory(), "models": [hosted]}
    monkeypatch.setattr(catalog_module, "model_catalog", inventory)
    allowed = {"lessons.search", "world.edit", "project.review", "project.export", "job.inspect"}
    forms, schema = _schema(allowed)
    prompt, retained, receipt = await studio._fit_planner_context(
        {"tenant_id": "tenant", "owner_id": "owner"}, _row(), {"project": {}},
        forms, allowed, "small goal", response_schema=schema)
    assert prompt == "small goal" and retained == allowed
    assert "native_framed_input_upper_bound" not in receipt
