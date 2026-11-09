"""Focused reconciliation guards for exact model selection.

No provider network invocation is required: only the configured registry
identity and application request contracts are exercised.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from skeleton.provider_runtime import ProviderRegistry, ProviderUnavailableError


class _Adapter:
    def __init__(self, provider_id: str, model: str, available: bool = True):
        self.provider_id = provider_id
        self.model = model
        self.available = available


def _registry(*, secondary_available: bool = True) -> ProviderRegistry:
    return ProviderRegistry(
        [
            _Adapter("primary", "model-a"),
            _Adapter("secondary", "model-b", secondary_available),
        ],
        active="primary",
        fallback_ids=("secondary",),
        architecture_loader=lambda provider_id: SimpleNamespace(provider_id=provider_id),
    )


def test_explicit_selection_never_uses_active_default_or_fallback():
    registry = _registry()
    chosen = registry.require_selected("secondary", "model-b")
    assert chosen.provider_id == "secondary"
    assert chosen.model == "model-b"
    assert chosen is not registry.active
    with pytest.raises(ProviderUnavailableError, match="selected"):
        registry.require_selected("secondary", "model-a")
    with pytest.raises(ProviderUnavailableError, match="selected"):
        registry.require_selected("missing", "model-b")


def test_unavailable_selection_is_not_automatically_replaced():
    registry = _registry(secondary_available=False)
    with pytest.raises(ProviderUnavailableError, match="unavailable"):
        registry.require_selected("secondary", "model-b")


@pytest.mark.parametrize("provider_id,model_id", (
    ("", "model-a"), ("primary ", "model-a"), ("primary", ""),
    ("primary", " model-a"), (None, "model-a"),
))
def test_model_identity_requires_nonempty_normalized_pair(provider_id, model_id):
    with pytest.raises(ProviderUnavailableError):
        _registry().require_selected(provider_id, model_id)
