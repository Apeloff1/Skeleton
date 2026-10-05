"""Authority-preserving agent economics for VOL-204."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Iterable


class AgentEconomicsError(ValueError):
    pass


@dataclass(frozen=True)
class AgentCost:
    agent_id: str
    task_id: str
    delegation_id: str
    amount: Decimal
    currency: str
    evidence_ref: str

    def __post_init__(self) -> None:
        if any(not value.strip() for value in (self.agent_id, self.task_id, self.delegation_id, self.currency, self.evidence_ref)):
            raise AgentEconomicsError("cost identity and evidence fields are required")
        if not self.amount.is_finite() or self.amount < 0:
            raise AgentEconomicsError("cost must be finite and non-negative")


@dataclass(frozen=True)
class AgentEconomicDecision:
    task_id: str
    selected_agent: str
    estimated_cost: Decimal
    quality_floor: Decimal
    authority_profile: str
    verification_profile: str
    rationale: str

    def __post_init__(self) -> None:
        if any(not v.strip() for v in (self.task_id, self.selected_agent, self.authority_profile, self.verification_profile, self.rationale)):
            raise AgentEconomicsError("decision fields must be non-empty")
        if not self.estimated_cost.is_finite() or self.estimated_cost < 0:
            raise AgentEconomicsError("estimated cost must be finite and non-negative")
        if not self.quality_floor.is_finite() or not Decimal("0") <= self.quality_floor <= Decimal("1"):
            raise AgentEconomicsError("quality floor must be within [0,1]")


class AgentCostLedger:
    def __init__(self) -> None:
        self._entries: list[AgentCost] = []
        self._keys: set[tuple[str, str, str, str]] = set()

    def record(self, cost: AgentCost) -> None:
        key = (cost.agent_id, cost.task_id, cost.delegation_id, cost.evidence_ref)
        if key in self._keys:
            raise AgentEconomicsError("duplicate cost evidence")
        self._keys.add(key)
        self._entries.append(cost)

    def total_for_task(self, task_id: str, currency: str) -> Decimal:
        return sum((e.amount for e in self._entries if e.task_id == task_id and e.currency == currency), Decimal("0"))

    def total_for_delegation(self, delegation_id: str, currency: str) -> Decimal:
        return sum((e.amount for e in self._entries if e.delegation_id == delegation_id and e.currency == currency), Decimal("0"))


@dataclass(frozen=True)
class AgentOffer:
    agent_id: str
    estimated_cost: Decimal
    expected_quality: Decimal
    authority_profile: str
    verification_profile: str


def choose_offer(
    task_id: str,
    offers: Iterable[AgentOffer],
    *,
    quality_floor: Decimal,
    required_authority_profile: str,
    required_verification_profile: str,
) -> AgentEconomicDecision:
    eligible = [
        o for o in offers
        if o.expected_quality >= quality_floor
        and o.authority_profile == required_authority_profile
        and o.verification_profile == required_verification_profile
        and o.estimated_cost.is_finite() and o.estimated_cost >= 0
    ]
    if not eligible:
        raise AgentEconomicsError("no offer satisfies quality, authority, verification, and cost constraints")
    selected = min(eligible, key=lambda o: (o.estimated_cost, -o.expected_quality, o.agent_id))
    return AgentEconomicDecision(
        task_id=task_id,
        selected_agent=selected.agent_id,
        estimated_cost=selected.estimated_cost,
        quality_floor=quality_floor,
        authority_profile=required_authority_profile,
        verification_profile=required_verification_profile,
        rationale="lowest eligible cost without weakening quality, authority, or verification",
    )
