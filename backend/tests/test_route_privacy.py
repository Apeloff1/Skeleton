from __future__ import annotations

import pytest

from core.engine_text import EngineTextError, EngineTextRequest, execute_engine_text
from core.route_policy_catalog import default_route_domain_policy
from core.route_privacy import (
    DOMAIN_PRIVACY_POLICIES,
    bind_route_privacy,
    current_route_privacy,
    require_route_provider_transfer,
    require_route_tool_transfer,
    reset_route_privacy,
    resolve_route_privacy,
    validate_domain_privacy_coverage,
)
from services import tool_registry
from skeleton.vault.data_governance import DataGovernanceDenied


def test_every_route_domain_has_exactly_one_privacy_policy() -> None:
    validate_domain_privacy_coverage()
    domains = {
        rule.domain
        for rule in default_route_domain_policy().domain_rules
    }
    assert set(DOMAIN_PRIVACY_POLICIES) == domains


def test_open_routes_are_public_and_cannot_invoke_provider_or_network_tool() -> None:
    token = bind_route_privacy("/api/health")
    try:
        context = current_route_privacy()
        assert context is not None
        assert context.open_route is True
        assert context.max_data_class.label == "public"

        with pytest.raises(
            DataGovernanceDenied,
            match="route_provider_transfer_denied",
        ):
            require_route_provider_transfer(
                provider_id="skeleton-engine",
                data_class="public",
            )

        with pytest.raises(
            DataGovernanceDenied,
            match="route_network_tool_denied",
        ):
            require_route_tool_transfer(
                tool_id="web_search",
                data_policy="public:untrusted",
                network_policy="public-search:bounded-egress",
                data_class="public",
            )
    finally:
        reset_route_privacy(token)

    assert current_route_privacy() is None


def test_vault_route_keeps_restricted_data_local() -> None:
    token = bind_route_privacy("/api/vault/records")
    try:
        context = current_route_privacy()
        assert context is not None
        assert context.domain == "vault"
        assert context.max_data_class.label == "restricted"
        assert context.allow_external_provider is False
        assert context.allow_network_tools is False

        local = require_route_tool_transfer(
            tool_id="vault_query",
            data_policy="restricted:tenant-vault",
            network_policy="none",
            data_class="restricted",
            tenant_id="tenant-a",
        )
        assert local.permitted is True

        with pytest.raises(
            DataGovernanceDenied,
            match="route_provider_transfer_denied",
        ):
            require_route_provider_transfer(
                provider_id="skeleton-engine",
                data_class="internal",
                tenant_id="tenant-a",
            )
    finally:
        reset_route_privacy(token)


def test_product_route_allows_tenant_bound_confidential_provider_transfer() -> None:
    token = bind_route_privacy("/api/gameforge/build/web")
    try:
        decision = require_route_provider_transfer(
            provider_id="skeleton-engine",
            data_class="confidential",
            purpose="model-inference",
            tenant_id="tenant-a",
        )
        assert decision.permitted is True
        assert decision.data_class == "confidential"

        with pytest.raises(
            DataGovernanceDenied,
            match="confidential_requires_tenant",
        ):
            require_route_provider_transfer(
                provider_id="skeleton-engine",
                data_class="confidential",
                purpose="model-inference",
            )
    finally:
        reset_route_privacy(token)


def test_legacy_api_is_capped_at_internal_data() -> None:
    token = bind_route_privacy("/api/unknown-legacy-surface")
    try:
        context = current_route_privacy()
        assert context is not None
        assert context.domain == "legacy_api"
        assert context.max_data_class.label == "internal"

        with pytest.raises(
            DataGovernanceDenied,
            match="route_data_ceiling_exceeded",
        ):
            require_route_provider_transfer(
                provider_id="skeleton-engine",
                data_class="confidential",
                tenant_id="tenant-a",
            )
    finally:
        reset_route_privacy(token)


@pytest.mark.asyncio
async def test_engine_text_route_privacy_denies_before_client_resolution() -> None:
    token = bind_route_privacy("/api/governance/policy")
    try:
        with pytest.raises(
            EngineTextError,
            match="route privacy denied",
        ):
            await execute_engine_text(
                EngineTextRequest(
                    instructions="Do not transfer governance data.",
                    prompt="Summarize the policy.",
                    idempotency_key="route-privacy-provider",
                    tenant_id="tenant-a",
                    data_class="internal",
                )
            )
    finally:
        reset_route_privacy(token)


@pytest.mark.asyncio
async def test_network_tool_is_denied_before_canonical_runtime_initialization(
    monkeypatch,
) -> None:
    called = False

    async def forbidden_runtime_init() -> None:
        nonlocal called
        called = True
        raise AssertionError("canonical runtime must not initialize")

    monkeypatch.setattr(
        tool_registry,
        "_ensure_canonical_runtime",
        forbidden_runtime_init,
    )
    token = bind_route_privacy("/api/vault/search")
    try:
        result = await tool_registry.invoke_canonical(
            "web_search",
            {"query": "must not leave vault route"},
            operation_id="op-route-privacy",
            tenant_id="tenant-a",
            idempotency_key="idem-route-privacy",
            data_class="public",
        )
    finally:
        reset_route_privacy(token)

    assert result == {
        "ok": False,
        "error": "route_privacy_denied",
        "tool": "web_search",
    }
    assert called is False


def test_route_context_tokens_restore_outer_request_scope() -> None:
    outer = bind_route_privacy("/api/gameforge/build")
    try:
        assert current_route_privacy().domain == "gameforge"
        inner = bind_route_privacy("/api/vault/items")
        try:
            assert current_route_privacy().domain == "vault"
        finally:
            reset_route_privacy(inner)
        assert current_route_privacy().domain == "gameforge"
    finally:
        reset_route_privacy(outer)
    assert current_route_privacy() is None


def test_non_api_route_without_written_policy_fails_closed() -> None:
    with pytest.raises(
        DataGovernanceDenied,
        match="route_privacy_unwritten",
    ):
        resolve_route_privacy("/internal/debug")
