"""Regression coverage for TREE-008 provider-contract cutover."""

from __future__ import annotations

import importlib


def test_provider_contract_legacy_surface_reexports_canonical_contract() -> None:
    legacy = importlib.import_module("skeleton.provider_contract")
    canonical = importlib.import_module("skeleton.ai.providers.contract")

    assert legacy.ProviderArchitectureReceipt is canonical.ProviderArchitectureReceipt
    assert legacy.ProviderArchitectureError is canonical.ProviderArchitectureError
    assert legacy.load_provider_architecture is canonical.load_provider_architecture
    assert legacy.ProviderToolDefinition is canonical.ProviderToolDefinition
