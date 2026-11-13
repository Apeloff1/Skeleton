"""Provider-neutral model catalog guardrails brought forward from AI Chat draft.

These tests exercise the read-only product projection without configuring any
hosted provider, loading model weights, or authorizing an engine request.
"""
from __future__ import annotations

import asyncio

import pytest

from core.engine_client import EngineProtocolError
from core.model_catalog import (
    CATALOG_SCHEMA,
    ModelSelectionError,
    catalog_digest,
    catalog_from_inventory,
    context_budget_for_selection,
    cooperation_context_budget,
    cooperation_context_selection,
    model_catalog,
    readiness,
    resolve_selection,
    unavailable_catalog,
)


def test_unconfigured_engine_is_explicitly_unavailable() -> None:
    result = asyncio.run(model_catalog(None, actor_id="operator", tenant_id="tenant"))
    assert result["schema_version"] == CATALOG_SCHEMA
    assert result["models"] == []
    assert result["available"] is False
    assert result["readiness"]["code"] == "engine_not_configured"
    assert result["local_activation"]["production_promotion_authorized"] is False


def test_untrusted_readiness_code_fails_to_fixed_product_message() -> None:
    result = readiness("exception: token=private")
    assert result["code"] == "provider_configuration_unavailable"
    assert "private" not in str(result)


@pytest.mark.parametrize("code", ("local_guard_unavailable", "local_guard_configuration_invalid"))
def test_local_guard_failure_has_an_explicit_safe_product_message(code: str) -> None:
    result = readiness(code)
    assert result["code"] == code
    assert "local" in result["message"].lower()
    assert result["action"]


def test_unconfigured_guard_surfaces_through_local_engine_inventory(monkeypatch) -> None:
    from skeleton.provider_runtime import ProviderRegistry

    monkeypatch.setenv("AI_PROVIDER", "local")
    monkeypatch.setenv("AI_LOCAL_MODEL_PATH", "/not-opened/model.json")
    for name in (
        "AI_LOCAL_GUARD_REQUIRED", "AI_LOCAL_LEGACY_DEV_ACK", "AI_DEPLOYMENT_ENV",
        "AI_LOCAL_DEPLOYMENT_PATH", "AI_LOCAL_MODEL_CATALOG_PATH",
        "AI_SECONDARY_API_KEY", "AI_SECONDARY_BASE_URL", "AI_SECONDARY_MODEL",
        "AI_VERIFICATION_MODEL",
    ):
        monkeypatch.delenv(name, raising=False)
    registry = ProviderRegistry.from_env(retain_unavailable=True)
    result = catalog_from_inventory({"available": False, "active": "local", "providers": registry.statuses()})
    assert result["available"] is False
    assert result["readiness"]["code"] == "local_guard_unavailable"
    assert "safety components" in result["readiness"]["message"]


def test_model_selection_rejects_partial_identity() -> None:
    with pytest.raises(ModelSelectionError) as exc:
        resolve_selection(unavailable_catalog("engine_not_configured"), provider_id="local")
    assert exc.value.code == "model_selection_invalid"


def test_empty_inventory_is_fail_closed() -> None:
    with pytest.raises(EngineProtocolError):
        catalog_from_inventory({"available": True, "active": "local", "providers": []})


def test_digest_is_canonical_across_json_key_order() -> None:
    first = {"schema_version": CATALOG_SCHEMA, "models": [], "available": False}
    second = {"available": False, "models": [], "schema_version": CATALOG_SCHEMA}
    assert catalog_digest(first) == catalog_digest(second)
    assert len(catalog_digest(first)) == 64


def test_invalid_actor_identity_does_not_query_engine() -> None:
    with pytest.raises(EngineProtocolError):
        asyncio.run(model_catalog(None, actor_id="", tenant_id="tenant"))


def _review_selection():
    return {
        "default_output_tokens": 3072,
        "max_output_tokens": 4096,
        "context_window": 16384,
        "context_tokenizer": "utf8_bytes",
        "tokenizer": "utf8_bytes",
        "supports_temperature": True,
    }


@pytest.mark.parametrize("drafts,rounds", [(1, 1), (2, 1), (3, 1), (3, 3)])
def test_catalog_requires_output_for_every_draft_and_review_stage(drafts, rounds):
    policy = {"schema_version": "skeleton.ai.cooperation.v1", "draft_count": drafts, "review_rounds": rounds}
    stages = 1 + drafts + 2 * rounds
    selection = _review_selection()
    assert cooperation_context_selection({}, selection, policy, output_tokens=64 * stages) == selection
    with pytest.raises(ModelSelectionError) as exc:
        cooperation_context_selection({}, selection, policy, output_tokens=64 * stages - 1)
    assert exc.value.code == "cooperation_budget_insufficient"


def test_multidraft_compilation_reserves_candidate_material_without_enlarging_context():
    budget = context_budget_for_selection(_review_selection())
    legacy = cooperation_context_budget(budget, {"schema_version": "skeleton.ai.cooperation.v1"})
    multiple = cooperation_context_budget(
        budget, {"schema_version": "skeleton.ai.cooperation.v1", "draft_count": 3}
    )
    assert legacy.reserved_policy_tokens == budget.reserved_policy_tokens + 1536
    assert multiple.reserved_policy_tokens > legacy.reserved_policy_tokens
    assert multiple.max_context_tokens == budget.max_context_tokens
    assert multiple.reserved_output_tokens == budget.reserved_output_tokens
    # Reserving three candidates cannot make a previously tight context larger.
    from dataclasses import replace

    tight = replace(budget, max_context_tokens=8192)
    with pytest.raises(ModelSelectionError) as exc:
        cooperation_context_budget(tight, {"schema_version": "skeleton.ai.cooperation.v1", "draft_count": 3})
    assert exc.value.code == "cooperation_context_too_small"
