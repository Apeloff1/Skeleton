from __future__ import annotations

import copy
import hashlib
import math

import pytest

from skeleton.frontier.runtime.model_routing import ProviderMetadataError
from skeleton.frontier.runtime.model_runtime import ChatResponse, ModelCapability, TokenUsage
from skeleton.contracts.canonical import canonical_json_bytes
from skeleton.intelligence.router_registry import RouterRegistry


class Adapter:
    capabilities = frozenset({ModelCapability.CHAT.value})

    def __init__(self, name: str) -> None:
        self.name = name

    async def chat(self, request):
        return ChatResponse(model=request.model, text="ok", usage=TokenUsage())


def _provider(provider_id: str = "p1", adapter_name: str = "a1", priority: int = 1):
    return {
        "provider_id": provider_id,
        "adapter_name": adapter_name,
        "model": "model-1",
        "capabilities": ["chat"],
        "max_input_tokens": 4096,
        "max_output_tokens": 512,
        "input_cost_per_million": 1.0,
        "output_cost_per_million": 2.0,
        "timeout_seconds": 3.0,
        "priority": priority,
    }


def test_registry_snapshot_is_order_independent_and_content_addressed() -> None:
    left = RouterRegistry([_provider("p2", "a2", 2), _provider()])
    right = RouterRegistry([_provider(), _provider("p2", "a2", 2)])

    assert left.snapshot().as_dict() == right.snapshot().as_dict()
    assert [item.provider_id for item in left.providers()] == ["p1", "p2"]


def test_snapshot_round_trip_and_tamper_rejection() -> None:
    snapshot = RouterRegistry([_provider()]).snapshot().as_dict()
    restored = RouterRegistry.from_snapshot(snapshot)
    assert restored.snapshot().as_dict() == snapshot

    tampered = copy.deepcopy(snapshot)
    tampered["providers"][0]["priority"] = 99
    with pytest.raises(ProviderMetadataError, match="digest mismatch"):
        RouterRegistry.from_snapshot(tampered)


def test_duplicate_provider_and_shared_adapter_fail_closed() -> None:
    with pytest.raises(ProviderMetadataError, match="duplicate provider_id"):
        RouterRegistry([_provider(), _provider()])
    with pytest.raises(ProviderMetadataError, match="shared"):
        RouterRegistry([_provider(), _provider("p2", "a1")])


def test_bind_requires_exact_declared_adapter_set() -> None:
    registry = RouterRegistry([_provider()])
    with pytest.raises(ProviderMetadataError, match="missing adapters"):
        registry.bind({})
    with pytest.raises(ProviderMetadataError, match="undeclared adapters"):
        registry.bind({"a1": Adapter("a1"), "surprise": Adapter("surprise")})

    router = registry.bind({"a1": Adapter("a1")})
    assert set(router.catalog()) == {"p1"}


def test_adapter_identity_mismatch_is_rejected_by_router_boundary() -> None:
    registry = RouterRegistry([_provider()])
    with pytest.raises(ProviderMetadataError, match="adapter name"):
        registry.bind({"a1": Adapter("different")})


def test_snapshot_contains_no_adapter_or_secret_runtime_state() -> None:
    registry = RouterRegistry([_provider()])
    payload = registry.snapshot().as_dict()
    rendered = repr(payload).lower()
    assert "api_key" not in rendered
    assert "password" not in rendered
    assert "authorization" not in rendered


def test_snapshot_rejects_non_finite_numeric_metadata_fail_closed() -> None:
    snapshot = RouterRegistry([_provider()]).snapshot().as_dict()
    snapshot["providers"][0]["input_cost_per_million"] = math.nan
    with pytest.raises(ProviderMetadataError, match="strict canonical JSON"):
        RouterRegistry.from_snapshot(snapshot)


def test_snapshot_digest_uses_shared_canonical_contract_bytes() -> None:
    snapshot = RouterRegistry([_provider()]).snapshot().as_dict()
    body = {
        "schema_version": snapshot["schema_version"],
        "providers": snapshot["providers"],
    }
    assert snapshot["digest"] == hashlib.sha256(canonical_json_bytes(body)).hexdigest()
