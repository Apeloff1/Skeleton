"""Regression coverage for TREE-008 JVM registry namespace migration."""

from __future__ import annotations

import importlib


def test_jvm_registry_legacy_surface_reexports_canonical_registry() -> None:
    legacy = importlib.import_module("skeleton.jvm_accelerators")
    canonical = importlib.import_module("skeleton.native.jvm_registry")

    assert legacy.JvmAcceleratorRegistry is canonical.JvmAcceleratorRegistry
    assert legacy.JvmAcceleratorRegistryError is canonical.JvmAcceleratorRegistryError
    assert legacy.JvmAcceleratorPreflight is canonical.JvmAcceleratorPreflight
    assert legacy.JvmAcceleratorRuntimeStatus is canonical.JvmAcceleratorRuntimeStatus
