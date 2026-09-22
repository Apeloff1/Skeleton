"""Task routing — pick the best agent for a job using reputation and capabilities.

The scheduler asks "who should take this?" Routing weighs capability
coverage first, then current reputation, producing a ranked candidate list.
This closes the loop between discovery, reputation, and scheduling.

- :class:`RouteRequest` — required capabilities + context
- :class:`TaskRouter` — match Discovery with ReputationTable
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from skeleton.kernel.errors import AgentError
from skeleton.agents.discovery import Advert, AgentDiscovery
from skeleton.agents.reputation import ReputationTable


class RoutingError(AgentError):
    code = "AGT.ROUTING"


@dataclass(frozen=True)
class RouteRequest:
    capabilities: tuple  # required capability strings
    prefer_reputation: bool = True


@dataclass
class RouteCandidate:
    agent_id: str
    match_score: float
    reputation: float
    combined: float


class TaskRouter:
    """Scores agents across discovery + reputation."""

    def __init__(self, discovery: AgentDiscovery, reputation: ReputationTable) -> None:
        self._discovery = discovery
        self._reputation = reputation

    def route(self, request: RouteRequest) -> Tuple[RouteCandidate, ...]:
        adverts = self._discovery.all()
        if not adverts:
            raise RoutingError("no agents advertised")
        out: List[RouteCandidate] = []
        for advert in adverts:
            match_score = sum(1 for c in request.capabilities if c in advert.capabilities)
            if match_score == 0:
                continue
            try:
                rep = self._reputation.score(advert.agent_id)
            except Exception:
                rep = 0.0
            combined = float(match_score) + (rep if request.prefer_reputation else 0.0)
            out.append(
                RouteCandidate(
                    agent_id=advert.agent_id,
                    match_score=float(match_score),
                    reputation=rep,
                    combined=combined,
                )
            )
        if not out:
            raise RoutingError("no agent has the required capabilities")
        out.sort(key=lambda c: -c.combined)
        return tuple(out)

    def best(self, request: RouteRequest) -> RouteCandidate:
        return self.route(request)[0]
