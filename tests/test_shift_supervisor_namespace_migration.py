from __future__ import annotations

import importlib
from pathlib import Path

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


def test_shift_supervisor_compat_cli_uses_canonical_state_reader(tmp_path: Path) -> None:
    # The retired shift-supervisor-control workflow is not an authority.
    # The supported compatibility CLI delegates to the canonical runtime.
    legacy = importlib.import_module("core.shift_supervisor.__main__")
    canonical = importlib.import_module("skeleton.automation.shift_supervisor.__main__")
    assert legacy.main is canonical.main

    state_file = tmp_path / "shift-state.json"
    state_file.write_text('{"version": 1, "plan_items": []}', encoding="utf-8")
    assert canonical._read_state(state_file) == {"version": 1, "plan_items": []}

    # Malformed persisted state must continue to fail closed.
    state_file.write_text('{"version":', encoding="utf-8")
    with pytest.raises(ValueError, match="invalid shift-supervisor state"):
        canonical._read_state(state_file)

