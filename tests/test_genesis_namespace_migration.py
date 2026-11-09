"""Regression coverage for TREE-009 Genesis namespace migration."""

from __future__ import annotations

import importlib


def test_genesis_legacy_surface_reexports_canonical_bootstrap() -> None:
    legacy = importlib.import_module("skeleton.genesis")
    canonical = importlib.import_module("skeleton.bootstrap.genesis")

    assert legacy.Genesis is canonical.Genesis
    assert legacy.GenesisReport is canonical.GenesisReport
