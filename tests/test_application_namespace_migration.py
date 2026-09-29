from __future__ import annotations

import importlib

import pytest


def test_application_package_exports_are_canonical_identities() -> None:
    import skeleton.app.runtime as canonical
    import skeleton.application as legacy

    assert legacy.CommandService is canonical.CommandService
    assert legacy.UnifiedRequest is canonical.UnifiedRequest
    assert legacy.build_runtime_command_service is canonical.build_runtime_command_service


@pytest.mark.parametrize(
    "module_name",
    [
        "command_contracts",
        "retry_policy",
        "runtime_commands",
        "unified_invoke",
        "capability_runtime",
        "execution_ledger",
        "reconciliation_queue",
    ],
)
def test_application_module_shims_cover_canonical_public_surface(module_name: str) -> None:
    canonical = importlib.import_module(f"skeleton.app.runtime.{module_name}")
    legacy = importlib.import_module(f"skeleton.application.{module_name}")
    public = {name for name in vars(canonical) if not name.startswith("_")}
    assert public
    assert public.issubset(set(vars(legacy)))
