"""Fair bounded dispatch advisories from the *already committed* frontier.

This module cannot create a network request, escalate a physical worker,
alter scheduling leases, change robots permissions or reserve backend bytes.
It narrows an existing campaign plan using observed resource pressure, due
times, host quotas and a deterministic round-robin selection.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from collections import defaultdict
from typing import Iterable

from .budget import BudgetProjection, reserve_advisory
from .contracts import CampaignMandate, ResearchDispatch, digest, integer
from .frontier_graph import FrontierTopology
from .mission_strategy import MissionStrategy
from .pressure import PressureDecision


@dataclass(frozen=True)
class DispatchSlot:
    order: int
    url: str
    host: str
    ready_at: float
    expected_bytes: int
    objective_ids: tuple[str, ...]
    rank: int
    requires_backend_admission: bool = True
    network_executed: bool = False


@dataclass(frozen=True)
class AllocationAdvice:
    mandate_digest: str
    frontier_digest: str
    strategy_digest: str
    pressure_digest: str | None
    proposed_slots: tuple[DispatchSlot, ...]
    deferred_urls: tuple[tuple[str, str], ...]
    bytes_proposed: int
    request_slots: int
    actionable_now: bool
    blockers: tuple[str, ...]
    advice_digest: str
    externally_authorized: bool = False


def allocate_frontier_advisory(
    mandate: CampaignMandate,
    topology: FrontierTopology,
    strategy: MissionStrategy,
    budget: BudgetProjection,
    *,
    now: float,
    authorized: bool,
    pressure: PressureDecision | None = None,
    max_slots: int = 8,
    max_slots_per_host: int = 2,
) -> AllocationAdvice:
    mandate.admit(now=now, authorized=authorized)
    integer(max_slots, "frontier slot capacity", 1, 32)
    integer(max_slots_per_host, "frontier host slot capacity", 1, 16)
    if strategy.mandate_digest != mandate.fingerprint:
        raise PermissionError("cross-mandate strategy")
    if strategy.frontier_digest != topology.topology_digest:
        raise PermissionError("strategy from a different frontier")
    if pressure is not None and not isinstance(pressure, PressureDecision):
        raise TypeError("typed pressure receipt required")
    bound = {arc.child_url: arc for arc in topology.arcs}
    if len(bound) != topology.frontier_count:
        raise ValueError("ambiguous canonical frontier")
    scheduled = tuple(strategy.proposed_plan.dispatches)
    if len(scheduled) > mandate.limits.max_dispatches:
        raise ValueError("strategy exceeds dispatch mandate")
    blockers = list(budget.blockers)
    if pressure is None:
        blockers.append("fresh_resource_telemetry_required")
        permitted = 0
    elif pressure.recommend_pause:
        blockers.extend(pressure.reasons)
        permitted = 0
    else:
        permitted = min(
            max_slots, pressure.recommend_max_slice_steps,
            pressure.recommend_max_parallel_workers,
            budget.requests_remaining, budget.documents_remaining,
        )
    buckets = defaultdict(list)
    deferrals = []
    candidate_by_url = {row.url: row for row in strategy.candidates}
    for row in scheduled:
        if not isinstance(row, ResearchDispatch):
            raise TypeError("strategy contains noncanonical dispatch")
        arc = bound.get(row.url)
        if arc is None or row.host != candidate_by_url[row.url].host:
            raise PermissionError("planned URL not on exact frontier")
        if row.expected_bytes != mandate.request.max_response_bytes:
            raise PermissionError("unreserved network response cap")
        if row.ready_at > now or arc.ready_at > now:
            deferrals.append((row.url, "canonical_host_or_retry_cooldown"))
            continue
        buckets[row.host].append(row)
    for host in buckets:
        buckets[host].sort(key=lambda x: (x.rank, -x.score, x.url))
    chosen = []
    per_host = defaultdict(int)
    charge = 0
    hosts = sorted(buckets)
    while len(chosen) < permitted:
        progress = False
        for host in hosts:
            if per_host[host] >= max_slots_per_host or not buckets[host]:
                continue
            row = buckets[host][0]
            if charge + row.expected_bytes > budget.bytes_remaining:
                deferrals.append((row.url, "conservative_byte_reserve_limit"))
                buckets[host].pop(0)
                progress = True
                continue
            buckets[host].pop(0)
            choice = candidate_by_url[row.url]
            chosen.append(DispatchSlot(
                order=len(chosen), url=row.url, host=host,
                ready_at=row.ready_at, expected_bytes=row.expected_bytes,
                objective_ids=choice.objective_ids, rank=row.rank,
            ))
            per_host[host] += 1
            charge += row.expected_bytes
            progress = True
            if len(chosen) >= permitted:
                break
        if not progress:
            break
    taken = {x.url for x in chosen}
    deferred = {url: reason for url, reason in deferrals}
    for row in scheduled:
        if row.url not in taken and row.url not in deferred:
            deferred[row.url] = (
                "no_fresh_resource_capacity" if permitted == 0 else
                "fairness_or_campaign_budget"
            )
    reservation = reserve_advisory(
        budget, allocations=tuple((x.url, x.expected_bytes) for x in chosen),
    )
    if reservation.projected_bytes != charge:
        raise ValueError("advisory reserve counter mismatch")
    if not chosen:
        blockers.append("no_current_advisory_dispatch_slots")
    payload = {
        "mandate": mandate.fingerprint,
        "topology": topology.topology_digest,
        "strategy": strategy.strategy_digest,
        "pressure": pressure.decision_digest if pressure else None,
        "slots": [asdict(x) for x in chosen],
        "deferred": sorted(deferred.items()),
        "blockers": sorted(set(blockers)),
    }
    return AllocationAdvice(
        mandate_digest=mandate.fingerprint,
        frontier_digest=topology.topology_digest,
        strategy_digest=strategy.strategy_digest,
        pressure_digest=pressure.decision_digest if pressure else None,
        proposed_slots=tuple(chosen),
        deferred_urls=tuple(sorted(deferred.items())),
        bytes_proposed=charge,
        request_slots=len(chosen),
        actionable_now=bool(chosen) and not blockers,
        blockers=tuple(sorted(set(blockers))),
        advice_digest=digest(payload),
    )
