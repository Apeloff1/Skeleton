"""Agent discovery — capability-based lookup across the mesh.

Meshes degrade into swarms; discovery keeps a registry of agents keyed by
capability and returns the strongest match for a query.rides on top of
mesh but is queryable directly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from skeleton.kernel.errors import AgentError


class DiscoveryError(AgentError):
    code = "AGT.DISCOVERY"


@dataclass(frozen=True)
class Advert:
    agent_id: str
    capabilities: tuple  # strings like "code", "critique", "execution"


@dataclass
class Match:
    advert: Advert
    score: float


class AgentDiscovery:
    """Index of capability adverts; queryable by required skills."""

    def __init__(self) -> None:
        self._adverts: Dict[str, Advert] = {}

    def announce(self, agent_id: str, capabilities: Tuple[str, ...]) -> Advert:
        advert = Advert(agent_id=agent_id, capabilities=tuple(capabilities))
        self._adverts[agent_id] = advert
        return advert

    def withdraw(self, agent_id: str) -> bool:
        return self._adverts.pop(agent_id, None) is not None

    def find(self, required: Tuple[str, ...]) -> Optional[Advert]:
        if not required:
            raise DiscoveryError("query must request at least one capability")
        best: Optional[Advert] = None
        best_score = -1.0
        for advert in self._adverts.values():
            score = sum(1 for c in required if c in advert.capabilities)
            if score > best_score:
                best = advert
                best_score = score
        if best is None or best_score == 0:
            return None
        return best

    def all(self) -> Tuple[Advert, ...]:
        return tuple(self._adverts.values())
