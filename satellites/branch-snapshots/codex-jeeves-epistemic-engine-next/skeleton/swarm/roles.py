"""Swarm role registry — preset capabilities per AgentRole.

Swarm.types defines SCOUT / WORKER / GUARDIAN / ORACLE but nothing
says which capabilities each role claims by default. The registry maps
role name to a capability tuple; discovery/routing string ask, not
opaque strings.

- :class:`RoleRegistry` — role → capability tuple
"""

from __future__ import annotations

from typing import Dict, Tuple

from skeleton.kernel.errors import AgentError
from skeleton.swarm.types import AgentRole


class RoleError(AgentError):
    code = "AGT.ROLE"


class RoleRegistry:
    """Registry of role defaults for discovery/routing."""

    def __init__(self) -> None:
        self._roles: Dict[str, Tuple[str, ...]] = {}

    def register(self, role: AgentRole, capabilities: Tuple[str, ...]) -> None:
        self._roles[role.name] = tuple(capabilities)

    def capabilities_of(self, role: str) -> Tuple[str, ...]:
        caps = self._roles.get(role)
        if caps is None:
            raise RoleError("unknown role", context={"role": role})
        return caps

    def roles(self) -> Tuple[str, ...]:
        return tuple(sorted(self._roles))


def default_roles() -> RoleRegistry:
    registry = RoleRegistry()
    registry.register(AgentRole.SCOUT, ("discovery", "information"))
    registry.register(AgentRole.WORKER, ("execution", "computation"))
    registry.register(AgentRole.GUARDIAN, ("validation", "fault-detection"))
    registry.register(AgentRole.ORACLE, ("prediction", "advisory"))
    return registry
