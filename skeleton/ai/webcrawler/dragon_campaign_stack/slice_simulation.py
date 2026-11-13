"""Counterfactual host-fair crawl-slice modeling with strict safety ceilings.

The canonical CrawlRun already owns real dispatch admission, robots handling,
DNS/socket validation, pending request custody, physical worker fencing and
Mongo checkpoints. This module never invokes fetch_once or stores a commit.
It projects at most one finite batch of hypothetical future tasks using
only immutable retained frontier URLs, real per-host cool-down clocks,
full response-byte caps, and robots preflight uncertainty.

An unknown robots response permits only a hypothetical robots fetch, not a
page fetch. A canceled/failed/paused/completed run, in-flight unknown request,
insufficient resource data or expired grant cannot acquire a proposed slot.
Even a proposed slot requires a new canonical runner admission before I/O.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from typing import Iterable
from urllib.parse import urlsplit

from ..operations import CrawlRun
from .budget import BudgetProjection, verify_projected_budget
from .contracts import CampaignMandate, digest, ensure_snapshot_scope, finite, integer
from .frontier_route_map import CrawlRouteTopology
from .pressure import PressureDecision


@dataclass(frozen=True)
class HypotheticalSliceStep:
    ordinal: int
    url: str
    host: str
    origin: str
    action: str
    projected_ready_at: float
    conservative_reserve_bytes: int
    accounted_requests: int
    requires_live_robots_authority: bool
    requires_live_dns_socket_admission: bool = True
    actual_network_executed: bool = False


@dataclass(frozen=True)
class HypotheticalSlicePlan:
    mandate_digest: str
    source_snapshot_digest: str
    routes_digest: str
    planned_at: float
    steps: tuple[HypotheticalSliceStep, ...]
    held_urls: tuple[tuple[str, str], ...]
    projected_request_slots: int
    projected_byte_reserve: int
    request_budget_remaining_after: int
    byte_budget_remaining_after: int
    state: str
    terminal_blockers: tuple[str, ...]
    simulation_digest: str
    actual_network_executed: bool = False
    reservation_committed: bool = False
    worker_lease_authenticated: bool = False
    robots_evaluated_live: bool = False


def simulate_canonical_slice(
    mandate: CampaignMandate,
    snapshot: dict[str, object],
    routes: CrawlRouteTopology,
    budget: BudgetProjection,
    *,
    now: float,
    authorized: bool,
    pressure: PressureDecision | None,
    max_steps: int = 4,
    host_quota: int = 2,
    max_horizon_seconds: float = 600,
) -> HypotheticalSlicePlan:
    mandate.admit(now=now, authorized=authorized)
    ensure_snapshot_scope(snapshot, mandate)
    integer(max_steps, "hypothetical slice length", 1, 4)
    integer(host_quota, "hypothetical host concurrency", 1, 4)
    finite(max_horizon_seconds, "hypothetical horizon", 0, 3600)
    if routes.mandate_digest != mandate.fingerprint:
        raise PermissionError("foreign route graph")
    if not isinstance(budget, BudgetProjection):
        raise TypeError("canonical budget receipt required")
    if pressure is not None and not isinstance(pressure, PressureDecision):
        raise TypeError("measured resource-pressure receipt required")
    run = CrawlRun.from_snapshot(snapshot)
    current = run.snapshot()
    verify_projected_budget(current, mandate, budget)
    if routes.source_snapshot_digest != current["snapshot_digest"]:
        raise PermissionError("route graph snapshot revision changed")
    blocking = list(budget.blockers)
    if pressure is None:
        blocking.append("live_resource_telemetry_not_supplied")
    elif pressure.recommend_pause:
        blocking.extend(pressure.reasons)
    if budget.pending_dispatch:
        blocking.append("unknown_in_flight_remote_effect")
    if current["state"] not in ("ready", "running"):
        blocking.append("crawler_state_" + current["state"])
    if not current["frontier"]:
        blocking.append("canonical_frontier_empty")
    caps = (
        0 if pressure is None else
        min(pressure.recommend_max_slice_steps,
            pressure.recommend_max_parallel_workers)
    )
    max_count = min(max_steps, caps,
                    budget.requests_remaining,
                    budget.documents_remaining)
    if blocking:
        max_count = 0
    rows = tuple(current["frontier"])
    host_ready = dict(current["host_ready"])
    host_usage = Counter()
    scheduled = set()
    preflight_origins = set()
    output = []
    held = {}
    charged = 0
    for _ in range(max_count):
        candidates = []
        for entry in rows:
            url = entry["url"]
            if url in scheduled or url in held:
                continue
            host = urlsplit(url).hostname
            if host_usage[host] >= host_quota:
                held[url] = "per_slice_host_quota"
                continue
            due = max(entry["ready_at"], host_ready.get(host, 0), now)
            if due > now + max_horizon_seconds:
                held[url] = "outside_bounded_hypothetical_horizon"
                continue
            if due >= mandate.scope.expires_at:
                held[url] = "consent_expires_before_due_time"
                continue
            origin = urlsplit(url)
            origin_url = origin.scheme + "://" + origin.netloc
            robots = current["robots"].get(origin_url)
            unknown = (
                robots is None or robots["text"] is None
                or due - robots["fetched_at"] >= 86400
            )
            if unknown and origin_url in preflight_origins:
                held[url] = "same_origin_robots_preflight_already_projected"
                continue
            if unknown:
                action = "robots_preflight_only"
                byte_count = min(65536, mandate.request.max_response_bytes)
            else:
                cached = run._robots_cache(origin_url)
                if not cached.allowed(url):
                    held[url] = "canonical_cached_robots_denied"
                    continue
                action = "page_fetch_candidate"
                byte_count = mandate.request.max_response_bytes
            candidates.append((
                due, host_usage[host], entry["attempts"],
                entry["depth"], url, host, origin_url, action, byte_count, unknown,
            ))
        candidates.sort()
        selected = None
        for item in candidates:
            if charged + item[8] <= budget.bytes_remaining:
                selected = item
                break
            held[item[4]] = "conservative_byte_cap_unavailable"
        if selected is None:
            break
        due, _, _, depth, url, host, origin, action, bytes_reserved, unknown = selected
        step = HypotheticalSliceStep(
            ordinal=len(output), url=url, host=host, origin=origin,
            action=action, projected_ready_at=due,
            conservative_reserve_bytes=bytes_reserved,
            accounted_requests=1, requires_live_robots_authority=unknown,
        )
        output.append(step)
        scheduled.add(url)
        if unknown:
            preflight_origins.add(origin)
        charged += bytes_reserved
        host_usage[host] += 1
        host_ready[host] = due + mandate.request.min_host_delay_seconds
        # An unknown robots result remains a preflight, never a grant for
        # another page request in this simulated batch.
    for entry in rows:
        if entry["url"] not in scheduled:
            held.setdefault(entry["url"],
                            "requires_live_runner_or_next_fair_slice")
    if not output:
        blocking.append("no_admitted_hypothetical_slice_capacity")
    payload = {
        "mandate": mandate.fingerprint,
        "snapshot": current["snapshot_digest"],
        "routes": routes.route_digest,
        "at": now, "pressure": pressure.decision_digest if pressure else None,
        "steps": [asdict(x) for x in output],
        "held": sorted(held.items()),
        "blocking": sorted(set(blocking)),
        "limits": (max_steps, host_quota, max_horizon_seconds),
    }
    return HypotheticalSlicePlan(
        mandate_digest=mandate.fingerprint,
        source_snapshot_digest=current["snapshot_digest"],
        routes_digest=routes.route_digest,
        planned_at=now, steps=tuple(output),
        held_urls=tuple(sorted(held.items())),
        projected_request_slots=len(output),
        projected_byte_reserve=charged,
        request_budget_remaining_after=budget.requests_remaining - len(output),
        byte_budget_remaining_after=budget.bytes_remaining - charged,
        state=current["state"],
        terminal_blockers=tuple(sorted(set(blocking))),
        simulation_digest=digest(payload),
    )
