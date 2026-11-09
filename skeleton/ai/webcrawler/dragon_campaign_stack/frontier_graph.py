"""Deterministic topology and host pressure for the authoritative crawl frontier.

No graph item is a new seed; every URL is checked against the canonical
persisted snapshot and the exact immutable mandate.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from collections import Counter
from urllib.parse import urlsplit

from ..operations import CrawlRun
from .contracts import CampaignMandate, digest, ensure_snapshot_scope, finite, integer, validate_public_url


@dataclass(frozen=True)
class HostFrontier:
    host: str
    pending: int
    unique_parents: int
    max_depth: int
    attempted: int
    ready_now: int
    delayed: int
    soonest_ready_at: float | None


@dataclass(frozen=True)
class FrontierArc:
    child_url: str
    parent_url: str | None
    depth: int
    attempts: int
    ready_at: float


@dataclass(frozen=True)
class FrontierTopology:
    run_id: str
    snapshot_digest: str
    frontier_count: int
    pending_by_depth: tuple[tuple[int, int], ...]
    hosts: tuple[HostFrontier, ...]
    arcs: tuple[FrontierArc, ...]
    saturated_hosts: tuple[str, ...]
    topology_digest: str


def analyze_frontier_topology(
    snapshot: dict[str, object], mandate: CampaignMandate, *,
    now: float,
    authorized: bool,
    saturation_threshold: int = 12,
) -> FrontierTopology:
    mandate.admit(now=now, authorized=authorized)
    integer(saturation_threshold, "host saturation threshold", 1, 512)
    ensure_snapshot_scope(snapshot, mandate)
    run = CrawlRun.from_snapshot(snapshot)
    actual = run.snapshot()
    fronts = actual["frontier"]
    host_ready = actual["host_ready"]
    seen_urls = set()
    arcs = []
    for row in fronts:
        url = validate_public_url(row["url"], mandate)
        parent = row["parent_url"]
        if parent is not None:
            validate_public_url(parent, mandate)
        if url in seen_urls:
            raise ValueError("repeated frontier item")
        seen_urls.add(url)
        integer(row["depth"], "frontier depth", 0, mandate.request.max_depth)
        integer(row["attempts"], "retry attempt", 0, 3)
        finite(row["ready_at"], "ready time")
        arcs.append(FrontierArc(
            url, parent, row["depth"], row["attempts"], row["ready_at"],
        ))
    # Every edge can point to an already-captured/seen parent (outside
    # current frontier), so do not invent an orphan error from absent parents.
    hosts: dict[str, list[FrontierArc]] = {}
    for row in arcs:
        hostname = urlsplit(row.child_url).hostname
        hosts.setdefault(hostname, []).append(row)
    host_reports = []
    for host, entries in sorted(hosts.items()):
        floor = finite(host_ready.get(host, 0), "host cooldown")
        ready = [max(x.ready_at, floor) for x in entries]
        host_reports.append(HostFrontier(
            host=host, pending=len(entries),
            unique_parents=len({x.parent_url for x in entries if x.parent_url}),
            max_depth=max(x.depth for x in entries),
            attempted=sum(x.attempts > 0 for x in entries),
            ready_now=sum(x <= now for x in ready),
            delayed=sum(x > now for x in ready),
            soonest_ready_at=min(ready),
        ))
    by_depth = Counter(x.depth for x in arcs)
    saturated = tuple(
        x.host for x in host_reports if x.pending >= saturation_threshold
    )
    payload = {
        "snapshot": actual["snapshot_digest"],
        "depths": sorted(by_depth.items()),
        "hosts": [asdict(x) for x in host_reports],
        "arcs": [asdict(x) for x in arcs],
        "saturated": saturated,
    }
    return FrontierTopology(
        run_id=actual["run_id"],
        snapshot_digest=actual["snapshot_digest"],
        frontier_count=len(arcs),
        pending_by_depth=tuple(sorted(by_depth.items())),
        hosts=tuple(host_reports),
        arcs=tuple(sorted(arcs, key=lambda x: (x.depth, x.child_url))),
        saturated_hosts=saturated,
        topology_digest=digest(payload),
    )
