"""Agent load balancing — pick the least-loaded candidate from routing.

TaskRouter returns candidates; LoadBalancerRuntime tracks in-flight
work per agent and returns (agent, load) tuples so schedulers bias
towards idle agents at dispatch time.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

from skeleton.agents.routing import RouteCandidate, RoutingError
from skeleton.kernel.errors import AgentError


class LoadBalanceError(AgentError):
    code = "AGT.LOAD"


@dataclass(frozen=True)
class LoadView:
    agent_id: str
    in_flight: int


class LoadBalancer:
    """Track in-flight counts; choose(lowest-load candidate)."""

    def __init__(self) -> None:
        self._in_flight: Dict[str, int] = {}

    def acquire(self, agent: str) -> None:
        self._in_flight[agent] = self._in_flight.get(agent, 0) + 1

    def release(self, agent: str) -> None:
        current = self._in_flight.get(agent, 0)
        if current <= 0:
            raise LoadBalanceError("release without acquire", context={"agent": agent})
        self._in_flight[agent] = current - 1

    def current(self, agent: str) -> LoadView:
        return LoadView(agent_id=agent, in_flight=self._in_flight.get(agent, 0))

    def choose(self, candidates: tuple) -> LoadView:
        if not candidates:
            raise LoadBalanceError("no candidates")
        best = min(
            candidates,
            key=lambda c: self._in_flight.get(c.agent_id, 0),
        )
        return LoadView(agent_id=best.agent_id, in_flight=self._in_flight.get(best.agent_id, 0))
