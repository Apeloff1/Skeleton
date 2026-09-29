"""Regression coverage for TREE-010 provider-contract namespace migration."""

from __future__ import annotations

import importlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_provider_contract_legacy_surface_reexports_canonical_contract() -> None:
    legacy = importlib.import_module("skeleton.provider_contract")
    canonical = importlib.import_module("skeleton.providers.contract")

    assert legacy.ProviderArchitectureReceipt is canonical.ProviderArchitectureReceipt
    assert legacy.ProviderArchitectureError is canonical.ProviderArchitectureError
    assert legacy.ProviderToolDefinition is canonical.ProviderToolDefinition
    assert legacy.load_provider_architecture is canonical.load_provider_architecture


def test_provider_runtime_imports_canonical_contract_namespace() -> None:
    source = (ROOT / "skeleton/provider_runtime.py").read_text(encoding="utf-8")
    assert "from skeleton.providers.contract import (" in source
    assert "from skeleton.provider_contract import (" not in source
