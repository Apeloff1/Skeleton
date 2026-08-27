"""Swarm role registry — named defaults over AgentRole + CapabilityVector.

Swarm.types has the taxonomy classes; nothing ships a preset. The
registry maps a role name (\"coder\", \"reviewer\", \"executor\") to its
capabilities so discovery/rouiting asks for them, not opaque strings.

- :class:`RoleRegistry` — role → capability tuple
"""

from __future__ import annotations

from typing import Dict, Tuple

from skeleton.kernel.errors import AgentError
from skeleton.swarm.types import AgentRole, CapabilityVector


class RoleError(AgentError):
    code = "AGT.ROLE"


class RoleRegistry:
    """Registry of role defaults for discovery/routing."""

    def __init__(self) -> None:
        self._roles: Dict[str, Tuple[str, ...]] = {}

    def register(self, role: AgentRole, capabilities: Tuple[str, ...]) -> None:
        self._roles[role.value] = tuple(capabilities)

    def capabilities_of(self, role: str) -> Tuple[str, ...]:
        caps = self._roles.get(role)
        if caps is None:
            raise RoleError("unknown role", context={"role": role})
        return caps

    def roles(self) -> Tuple[str, ...]:
        return tuple(sorted(self._roles))


def default_roles() -> RoleRegistry:
    registry = RoleRegistry()
    registry.register(AgentRole.CODER, ("code", "generation"))
    registry.register(AgentRole.REVIEWER, ("critique", "review"))
    registry.register(AgentRole.EXECUTOR, ("execution", "test"))
    return registry
