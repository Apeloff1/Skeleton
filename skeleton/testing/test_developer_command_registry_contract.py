from __future__ import annotations

import pytest

from skeleton.developer import CommandRegistry, DevCommandRegistry


def test_package_command_registry_preserves_historical_alias() -> None:
    assert CommandRegistry is DevCommandRegistry


def test_command_registry_dispatch_contract() -> None:
    registry = CommandRegistry()
    registry.register("echo", lambda args: list(args))

    assert registry.run("echo", ["one", "two"]) == ["one", "two"]

    with pytest.raises(ValueError, match="Unknown dev command: missing"):
        registry.run("missing", [])
