"""Exact canonical URL reachability, host backlogs and cycle diagnostics.

The graph is formed only from CrawlRun's committed seeds, seen URLs, saved
source URLs and queued parent links. Arbitrary HTML links cannot inject nodes,
and an absent edge does not imply a page was never discovered: the canonical
run does not retain all historical link relationships.

This is a read-only topology with deterministic nonrecursive SCC discovery,
not a new crawler frontier store or request dispatcher.
"""
from __future__ import annotations

from collections import Counter, defaultdict, deque
from dataclasses import asdict, dataclass
from urllib.parse import urlsplit

from ..operations import CrawlRun
from .contracts import CampaignMandate, digest, ensure_snapshot_scope, integer


@dataclass(frozen=True)
class CanonicalRouteNode:
    url: str
    host: str
    depth: int | None
    seed: bool
    visited: bool
    pending: bool
    source_count: int
    attempts: int
    ready_at: float | None
    indegree: int
    outdegree: int
    reachable_from_seed: bool
    source_text_trusted: bool = False


@dataclass(frozen=True)
class CanonicalRouteArc:
    parent_url: str
    child_url: str
    crosses_host_boundary: bool
    evidence: str = "committed_frontier_parent_reference"
    creates_network_authority: bool = False


@dataclass(frozen=True)
class HostRouteLoad:
    host: str
    discovered_nodes: int
    retained_sources: int
    pending_urls: int
    ready_urls: int
    attempted_urls: int
    max_depth: int
    pending_fairness_share: float
    robots_status: str


@dataclass(frozen=True)
class CrawlRouteTopology:
    mandate_digest: str
    source_snapshot_digest: str
    run_id: str
    nodes: tuple[CanonicalRouteNode, ...]
    edges: tuple[CanonicalRouteArc, ...]
    strongly_connected_components: tuple[tuple[str, ...], ...]
    isolated_pending_urls: tuple[str, ...]
    unreachable_pending_urls: tuple[str, ...]
    unknown_parent_urls: tuple[str, ...]
    host_load: tuple[HostRouteLoad, ...]
    max_observed_depth: int
    captured_unique_sources: int
    network_requests_started: bool
    route_digest: str
    unobserved_links_recovered: bool = False
    runnable_now: bool = False


def _nonrecursive_components(
    nodes: tuple[str, ...], arcs: tuple[CanonicalRouteArc, ...],
) -> tuple[tuple[str, ...], ...]:
    # Iterative Kosaraju: deterministic, stack-safe for <=2048 nodes.
    forward = {x: set() for x in nodes}
    backward = {x: set() for x in nodes}
    for edge in arcs:
        if edge.parent_url not in forward or edge.child_url not in forward:
            raise PermissionError("frontier edge has unseen endpoint")
        forward[edge.parent_url].add(edge.child_url)
        backward[edge.child_url].add(edge.parent_url)
    visited = set()
    order = []
    for root in nodes:
        if root in visited:
            continue
        # Discover neighbors one at a time in a true depth-first
        # traversal. Marking *all* children visited before descending can
        # give an incorrect postorder for converging DAG edges and causes
        # distinct noncyclic nodes to be reported in the same component.
        visited.add(root)
        stack = [(root, iter(sorted(forward[root])))]
        while stack:
            key, neighbors = stack[-1]
            child = next(neighbors, None)
            if child is None:
                order.append(key)
                stack.pop()
                continue
            if child not in visited:
                visited.add(child)
                stack.append((child, iter(sorted(forward[child]))))
    visited.clear()
    components = []
    for root in reversed(order):
        if root in visited:
            continue
        visited.add(root)
        stack = [root]
        members = []
        while stack:
            item = stack.pop()
            members.append(item)
            for target in sorted(backward[item], reverse=True):
                if target not in visited:
                    visited.add(target)
                    stack.append(target)
        members.sort()
        components.append(tuple(members))
    return tuple(sorted(components, key=lambda x: (x[0], len(x))))


def project_canonical_routes(
    mandate: CampaignMandate,
    snapshot: dict[str, object],
    *,
    now: float,
    authorized: bool,
    max_nodes: int = 2048,
    max_edges: int = 1024,
) -> CrawlRouteTopology:
    mandate.admit(now=now, authorized=authorized)
    ensure_snapshot_scope(snapshot, mandate)
    integer(max_nodes, "route graph node cap", 1, 4096)
    integer(max_edges, "route graph edge cap", 0, 4096)
    canonical = CrawlRun.from_snapshot(snapshot).snapshot()
    if len(canonical["frontier"]) > mandate.limits.max_candidates:
        raise ValueError("frontier exceeds bounded operator mandate")
    pending = {x["url"]: x for x in canonical["frontier"]}
    sources = defaultdict(set)
    for source in canonical["sources"].values():
        sources[source["canonical_url"]].add(source["source_id"])
    captured_source_urls = frozenset(sources)
    seeds = set(mandate.request.seed_urls)
    seen = set(canonical["seen"])
    universe = seeds | seen | set(pending) | set(sources)
    parents = set()
    edges = set()
    for child in canonical["frontier"]:
        parent = child["parent_url"]
        if parent is None:
            continue
        parents.add(parent)
        if parent == child["url"]:
            raise ValueError("canonical frontier contains self-parent relation")
        edges.add((parent, child["url"]))
    universe |= parents
    if len(universe) > max_nodes or len(edges) > max_edges:
        raise ValueError("canonical route topology exceeds bounds")
    # Canonical from_snapshot validates every URL and all allowed hosts, and
    # source snapshots are immutable data here, not active fetch permissions.
    arcs = tuple(sorted((
        CanonicalRouteArc(
            a, b,
            urlsplit(a).hostname != urlsplit(b).hostname,
        ) for a, b in edges
    ), key=lambda x: (x.parent_url, x.child_url)))
    indegree = Counter(x.child_url for x in arcs)
    outdegree = Counter(x.parent_url for x in arcs)
    forward = defaultdict(list)
    for item in arcs:
        forward[item.parent_url].append(item.child_url)
    roots = tuple(sorted(seeds))
    visited = set(roots)
    queue = deque(roots)
    while queue:
        source = queue.popleft()
        for child in forward[source]:
            if child not in visited:
                visited.add(child)
                queue.append(child)
    nodes = []
    hosts = defaultdict(list)
    for url in sorted(universe):
        row = pending.get(url)
        hostname = urlsplit(url).hostname
        if not hostname or hostname not in mandate.scope.allowed_hosts:
            raise PermissionError("route graph includes foreign host")
        item = CanonicalRouteNode(
            url=url, host=hostname,
            depth=row["depth"] if row else None,
            seed=url in seeds, visited=url in seen, pending=row is not None,
            source_count=len(sources.get(url, ())),
            attempts=row["attempts"] if row else 0,
            ready_at=(
                max(row["ready_at"], canonical["host_ready"].get(hostname, 0))
                if row else None
            ),
            indegree=indegree[url], outdegree=outdegree[url],
            reachable_from_seed=url in visited,
        )
        nodes.append(item)
        hosts[hostname].append(item)
    pending_total = len(pending)
    observations = []
    for host, rows in sorted(hosts.items()):
        count = sum(x.pending for x in rows)
        origins = tuple(origin for origin in canonical["robots"]
                        if urlsplit(origin).hostname == host)
        robot_status = (
            "uncached" if not origins else
            "cached" if all(canonical["robots"][origin]["text"] is not None
                            for origin in origins) else "requires_preflight"
        )
        observations.append(HostRouteLoad(
            host=host,
            discovered_nodes=len(rows),
            retained_sources=sum(x.source_count for x in rows),
            pending_urls=count,
            ready_urls=sum(x.pending and x.ready_at <= now for x in rows),
            attempted_urls=sum(x.pending and x.attempts > 0 for x in rows),
            max_depth=max((x.depth for x in rows if x.depth is not None),
                          default=0),
            pending_fairness_share=round(count / max(1, pending_total), 8),
            robots_status=robot_status,
        ))
    components = _nonrecursive_components(
        tuple(sorted(universe)), arcs,
    )
    unknown_parents = tuple(sorted(
        parents - seen - set(pending) - seeds - captured_source_urls
    ))
    isolated_pending = tuple(sorted(x.url for x in nodes
                                    if x.pending and not x.seed
                                    and x.indegree == 0))
    unreachable_pending = tuple(sorted(x.url for x in nodes
                                       if x.pending and not x.reachable_from_seed))
    body = {
        "mandate": mandate.fingerprint,
        "snapshot": canonical["snapshot_digest"],
        "nodes": [asdict(x) for x in nodes],
        "arcs": [asdict(x) for x in arcs],
        "components": components,
        "parents_untracked": unknown_parents,
        "hosts": [asdict(x) for x in observations],
    }
    return CrawlRouteTopology(
        mandate_digest=mandate.fingerprint,
        source_snapshot_digest=canonical["snapshot_digest"],
        run_id=canonical["run_id"],
        nodes=tuple(nodes), edges=arcs,
        strongly_connected_components=components,
        isolated_pending_urls=isolated_pending,
        unreachable_pending_urls=unreachable_pending,
        unknown_parent_urls=unknown_parents,
        host_load=tuple(observations),
        max_observed_depth=max((row["depth"] for row in pending.values()),
                               default=0),
        captured_unique_sources=len(canonical["sources"]),
        network_requests_started=canonical["usage"]["requests"] > 0,
        route_digest=digest(body),
    )
