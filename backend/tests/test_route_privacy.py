from __future__ import annotations

import pytest
import json
from pathlib import Path

from core.route_privacy import (
    bind_route_privacy,
    current_route_privacy,
    require_route_provider_transfer,
    require_route_tool_transfer,
    reset_route_privacy,
    resolve_route_privacy,
    validate_domain_privacy_coverage,
)
from skeleton.vault.data_governance import DataGovernanceDenied


def test_route_privacy_catalog_covers_every_written_domain() -> None:
    validate_domain_privacy_coverage()


def test_declared_private_families_use_existing_confidential_studio_ceiling():
    from core.route_policy_catalog import ROUTE_POLICY_CATALOG_VERSION
    contract = json.loads((Path(__file__).resolve().parents[2] / "machine/ai_app_construction.json").read_text())
    declaration = contract["first_install_continuation_2026_10_15"]["private_model_route_admission"]
    assert declaration["catalog_version"] == ROUTE_POLICY_CATALOG_VERSION
    for prefix in declaration["authenticated_prefixes"]:
        token = bind_route_privacy(prefix + "/private-model-operation")
        try:
            assert current_route_privacy().domain == declaration["existing_domain"] == "studio"
            permitted = require_route_provider_transfer(provider_id="skeleton-engine", data_class="confidential",
                                                        tenant_id="tenant-a", purpose="model-inference")
            assert permitted.permitted is True
            with pytest.raises(DataGovernanceDenied, match="route_data_ceiling_exceeded"):
                require_route_provider_transfer(provider_id="skeleton-engine", data_class="restricted",
                                                tenant_id="tenant-a", purpose="model-inference")
        finally:
            reset_route_privacy(token)
    for path in ["/api/playable-lookalike", "/api/jeeves-core/overview", "/api/assets/unknown-public-surface"]:
        assert resolve_route_privacy(path).domain == "legacy_api"


def test_governance_route_denies_external_provider_transfer() -> None:
    token = bind_route_privacy("/api/governance/policy")
    try:
        route = current_route_privacy()
        assert route is not None
        assert route.domain == "governance"
        assert route.allow_external_provider is False

        with pytest.raises(
            DataGovernanceDenied,
            match="route_provider_transfer_denied",
        ):
            require_route_provider_transfer(
                provider_id="openai",
                data_class="internal",
                purpose="model-inference",
                tenant_id="tenant-a",
            )
    finally:
        reset_route_privacy(token)


def test_code_execution_route_denies_network_tool_before_tool_policy() -> None:
    token = bind_route_privacy("/api/interpreter/run")
    try:
        with pytest.raises(
            DataGovernanceDenied,
            match="route_network_tool_denied",
        ):
            require_route_tool_transfer(
                tool_id="web.search",
                data_policy="public:untrusted",
                network_policy="public-search:bounded-egress",
                data_class="public",
                purpose="tool-execution",
                tenant_id="tenant-a",
            )
    finally:
        reset_route_privacy(token)


def test_tooling_route_allows_public_bounded_network_tool() -> None:
    token = bind_route_privacy("/api/tools/invoke")
    try:
        decision = require_route_tool_transfer(
            tool_id="web.search",
            data_policy="public:untrusted",
            network_policy="public-search:bounded-egress",
            data_class="public",
            purpose="tool-execution",
            tenant_id="tenant-a",
        )
    finally:
        reset_route_privacy(token)

    assert decision.permitted is True
    assert decision.data_class == "public"
    assert decision.network_policy == "public-search:bounded-egress"


def test_legacy_route_ceiling_rejects_confidential_data() -> None:
    token = bind_route_privacy("/api/unknown-legacy-surface")
    try:
        route = current_route_privacy()
        assert route is not None
        assert route.domain == "legacy_api"
        assert route.max_data_class.label == "internal"

        with pytest.raises(
            DataGovernanceDenied,
            match="route_data_ceiling_exceeded",
        ):
            require_route_tool_transfer(
                tool_id="vault.read",
                data_policy="confidential:vault",
                network_policy="none",
                data_class="confidential",
                purpose="retrieval-synthesis",
                tenant_id="tenant-a",
            )
    finally:
        reset_route_privacy(token)


def test_open_route_is_public_and_cannot_call_provider() -> None:
    route = resolve_route_privacy("/api/health/live")
    assert route.open_route is True
    assert route.max_data_class.label == "public"
    assert route.allow_external_provider is False
    assert route.allow_network_tools is False


def test_route_privacy_context_is_reset_after_request_scope() -> None:
    assert current_route_privacy() is None
    token = bind_route_privacy("/api/tools/invoke")
    assert current_route_privacy() is not None
    reset_route_privacy(token)
    assert current_route_privacy() is None
