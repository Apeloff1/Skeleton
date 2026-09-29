from __future__ import annotations

import importlib

import pytest


def test_shift_supervisor_package_exports_are_canonical_identities() -> None:
    import core.shift_supervisor as legacy
    import skeleton.automation.shift_supervisor as canonical

    assert legacy.SMBShiftManager is canonical.SMBShiftManager
    assert legacy.SecretaryBot is canonical.SecretaryBot
    assert legacy.SquadCoordinator is canonical.SquadCoordinator


@pytest.mark.parametrize(
    "module_name",
    ["runtime", "scheduler", "secretary", "shift_manager", "squads", "plan_store"],
)
def test_shift_supervisor_module_shims_cover_canonical_exports(module_name: str) -> None:
    canonical = importlib.import_module(f"skeleton.automation.shift_supervisor.{module_name}")
    legacy = importlib.import_module(f"core.shift_supervisor.{module_name}")
    exported = tuple(
        getattr(
            canonical,
            "__all__",
            tuple(name for name in vars(canonical) if not name.startswith("_")),
        )
    )
    assert exported
    assert all(hasattr(legacy, name) for name in exported)


def test_activation_security_core_entrypoint_is_canonical_shim() -> None:
    from core.activation_security import ActivationSecurityError as legacy
    from skeleton.security.activation_security import ActivationSecurityError as canonical
    assert legacy is canonical
