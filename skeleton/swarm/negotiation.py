"""Capability negotiation — contracts between task requirements and agents.

Routing picks an agent; negotiation is what happens *before* routing: the
structured exchange where a task's requirements are matched against what
agents actually advertise, with explicit degradation rather than silent
mismatch.

The unit of exchange is the **offer**: an agent's advertised capability
vector plus the cost/latency it quotes for a class of work. The negotiator
collects offers, scores them against the requirement, and produces a
**contract** — or a **negotiation failure** that names exactly which
capability dimensions no offer could satisfy, so the caller can relax
requirements deliberately instead of discovering the gap mid-task.

Negotiation outcomes are published to the bus, which lets the entanglement
detector see which capabilities are chronically under-provisioned — the
swarm's hiring plan, derived from its own failure history.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from skeleton.kernel.errors import AgentError
from skeleton.kernel.events import DomainEvent, EventBus
from .types import AgentState, CapabilityVector


class NegotiationError(AgentError):
    code = "AGT.NEGOTIATION"
    http_status = 409


@dataclass(frozen=True)
class Offer:
    """What one agent bids for one requirement."""
    agent_id: str
    capability: CapabilityVector
    cost: float = 1.0
    latency_ms: float = 0.0
    valid_until: float = 0.0        # 0 = no expiry

    def expired(self, now: float) -> bool:
        return self.valid_until > 0 and now > self.valid_until


@dataclass(frozen=True)
class Contract:
    """A formed agreement: agent, requirement, terms."""
    contract_id: str
    agent_id: str
    coverage: float                 # capability similarity at formation
    cost: float
    latency_ms: float
    formed_at: float = field(default_factory=time.time)


@dataclass(frozen=True)
class NegotiationFailure:
    """Why no contract formed — per-dimension shortfall."""
    requirement: CapabilityVector
    shortfalls: Dict[str, float]    # dimension -> best available / required
    offers_considered: int


class CapabilityNegotiator:
    """Matches task requirements to agent offers."""

    COVERAGE_FLOOR = 0.5            # minimum similarity to form a contract

    def __init__(self, *, bus: Optional[EventBus] = None) -> None:
        self._bus = bus
        self._contracts = 0
        self._failures = 0

    def negotiate(
        self,
        requirement: CapabilityVector,
        agents: List[AgentState],
        *,
        now: Optional[float] = None,
    ) -> Tuple[Optional[Contract], Optional[NegotiationFailure]]:
        """
        Collect offers from agents, score, and form the best contract.
        Returns (contract, None) or (None, failure) — never both.
        """
        now = now or time.time()
        offers = [self._offer_of(a, now) for a in agents]
        offers = [o for o in offers if o is not None and not o.expired(now)]

        if not offers:
            self._failures += 1
            failure = NegotiationFailure(
                requirement=requirement,
                shortfalls={},
                offers_considered=0,
            )
            self._emit("swarm.negotiation.failed", failure)
            return None, failure

        scored = sorted(
            offers,
            key=lambda o: o.capability.similarity(requirement) / max(o.cost, 1e-9),
            reverse=True,
        )
        best = scored[0]
        coverage = best.capability.similarity(requirement)

        if coverage < self.COVERAGE_FLOOR:
            self._failures += 1
            failure = NegotiationFailure(
                requirement=requirement,
                shortfalls=self._shortfalls(requirement, offers),
                offers_considered=len(offers),
            )
            self._emit("swarm.negotiation.failed", failure)
            return None, failure

        self._contracts += 1
        contract = Contract(
            contract_id=f"ctr_{self._contracts}",
            agent_id=best.agent_id,
            coverage=coverage,
            cost=best.cost,
            latency_ms=best.latency_ms,
        )
        if self._bus:
            self._bus.publish(
                DomainEvent(
                    topic="swarm.negotiation.contract",
                    payload={
                        "contract_id": contract.contract_id,
                        "agent_id": contract.agent_id,
                        "coverage": round(coverage, 3),
                        "cost": contract.cost,
                        "offers": len(offers),
                    },
                    correlation_id=contract.contract_id,
                )
            )
        return contract, None

    # ------------------------------------------------------------------

    def _offer_of(self, agent: AgentState, now: float) -> Optional[Offer]:
        if not agent.is_alive(now):
            return None
        return Offer(
            agent_id=str(agent.agent_id),
            capability=agent.capabilities,
            cost=max(agent.load_factor, 0.01) * 10.0,
            latency_ms=agent.latency_ms,
        )

    def _shortfalls(
        self,
        requirement: CapabilityVector,
        offers: List[Offer],
    ) -> Dict[str, float]:
        """Per-dimension best-available / required ratios below 1.0."""
        req = requirement.to_dict()
        shortfalls: Dict[str, float] = {}
        for dim, needed in req.items():
            if needed <= 0:
                continue
            best = max(getattr(o.capability, dim) for o in offers)
            ratio = best / needed
            if ratio < 1.0:
                shortfalls[dim] = round(ratio, 3)
        return shortfalls

    def _emit(self, topic: str, failure: NegotiationFailure) -> None:
        if not self._bus:
            return
        self._bus.publish(
            DomainEvent(
                topic=topic,
                payload={
                    "shortfalls": failure.shortfalls,
                    "offers_considered": failure.offers_considered,
                },
                correlation_id=f"negfail_{self._failures}",
            )
        )

    def stats(self) -> Dict[str, int]:
        return {"contracts_formed": self._contracts,
                "negotiations_failed": self._failures}
