"""Regression coverage for TREE-007 architecture namespace migration."""

from __future__ import annotations

import importlib


def test_architecture_index_legacy_surface_reexports_canonical_functions() -> None:
    legacy = importlib.import_module("skeleton.architecture_index")
    canonical = importlib.import_module("skeleton.foundation.architecture.index")

    assert legacy.full_summary is canonical.full_summary
    assert legacy.ROUND_MODULES is canonical.ROUND_MODULES
    assert all(
        module.__name__.startswith("skeleton.foundation.architecture.rounds.round")
        for module in canonical.ROUND_MODULES.values()
    )


def test_architecture_round_legacy_modules_reexport_canonical_summary() -> None:
    for number in range(3, 23):
        legacy = importlib.import_module(f"skeleton.architecture_round{number}")
        canonical = importlib.import_module(
            f"skeleton.foundation.architecture.rounds.round{number}"
        )
        assert legacy.summary is canonical.summary
        assert legacy.summary() == canonical.summary()
