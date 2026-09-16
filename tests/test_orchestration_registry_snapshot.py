from __future__ import annotations

import pytest

from skeleton.frontier.orchestration import ToolCapability, ToolRegistry


def test_registry_snapshot_is_immutable_and_detached_from_later_registration() -> None:
    tools = ToolRegistry()
    tools.register("echo", lambda arguments: arguments)

    snapshot = tools.snapshot()

    with pytest.raises(TypeError):
        snapshot["late"] = snapshot["echo"]  # type: ignore[index]

    tools.register("late", lambda arguments: arguments)

    assert tuple(snapshot) == ("echo",)
    assert set(tools.snapshot()) == {"echo", "late"}


def test_registry_snapshot_freezes_declared_capability_requirements() -> None:
    tools = ToolRegistry()
    tools.register(
        "fetch",
        lambda arguments: arguments,
        capabilities={ToolCapability.NETWORK, ToolCapability.SECRETS},
    )

    snapshot = tools.snapshot()
    definition = snapshot["fetch"]

    assert definition.name == "fetch"
    assert definition.capabilities == frozenset(
        {ToolCapability.NETWORK, ToolCapability.SECRETS}
    )

    with pytest.raises(AttributeError):
        definition.capabilities = frozenset()  # type: ignore[misc]
