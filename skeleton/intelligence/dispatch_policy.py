"""Deterministic, authority-free scheduling decisions for shared pressure.

All times are caller-supplied integer milliseconds. Resource units are
opaque positive integer reservations, never claimed hardware measurements.
This module selects proposals only; the existing pressure/engine owners
must revalidate every admission and physical resource reservation.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from collections.abc import Mapping, Sequence

MAX_CANDIDATES = 4096
MAX_DIMENSIONS = 32
MAX_VALUE = 10**15


class DispatchPolicyError(ValueError):
    """Invalid or unbounded scheduling observation."""


def bounded_int(value: int, name: str, minimum: int = 0, maximum: int = MAX_VALUE) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise DispatchPolicyError(f"invalid {name}")
    return value


def identifier(value: str) -> str:
    if type(value) is not str or not 1 <= len(value) <= 256 or any(
        ord(char) < 33 or ord(char) > 126 for char in value
    ):
        raise DispatchPolicyError("invalid scheduling identity")
    return value


@dataclass(frozen=True, slots=True)
class DispatchCandidate:
    ticket_id: str
    tenant_id: str
    priority: int
    enqueued_ms: int
    estimated_ms: int = 1
    deadline_ms: int | None = None
    critical_path_ms: int = 0
    locality_bytes: int = 0

    def __post_init__(self) -> None:
        identifier(self.ticket_id)
        identifier(self.tenant_id)
        bounded_int(self.priority, "priority", 0, 1000)
        bounded_int(self.enqueued_ms, "enqueue time")
        bounded_int(self.estimated_ms, "estimated duration", 1)
        bounded_int(self.critical_path_ms, "critical path")
        bounded_int(self.locality_bytes, "locality")
        if self.deadline_ms is not None:
            bounded_int(self.deadline_ms, "deadline", self.enqueued_ms)


@dataclass(frozen=True, slots=True)
class DispatchRanking:
    ticket_id: str
    effective_priority: int
    slack_ms: int | None
    tenant_share: Fraction
    wait_ms: int


def rank_candidates(
    candidates: Sequence[DispatchCandidate],
    *,
    now_ms: int,
    tenant_active: Mapping[str, int],
    tenant_weights: Mapping[str, int] | None = None,
    aging_interval_ms: int = 30_000,
    protected_priority: int = 10,
) -> tuple[DispatchRanking, ...]:
    """Rank eligible work with protected lanes, aging, EDF and weighted fairness.

    Aging cannot cross the protected boundary. The same immutable observation
    always produces the same order; input ordering is irrelevant.
    """
    bounded_int(now_ms, "time")
    bounded_int(aging_interval_ms, "aging interval", 1)
    bounded_int(protected_priority, "protected priority", 0, 1000)
    if len(candidates) > MAX_CANDIDATES:
        raise DispatchPolicyError("candidate limit exceeded")
    if len(tenant_active) > MAX_CANDIDATES or (
        tenant_weights is not None and len(tenant_weights) > MAX_CANDIDATES
    ):
        raise DispatchPolicyError("tenant observation limit exceeded")
    weights = tenant_weights or {}
    for tenant, count in tenant_active.items():
        identifier(tenant)
        bounded_int(count, "active count")
    for tenant, weight in weights.items():
        identifier(tenant)
        bounded_int(weight, "weight", 1, 1000)
    seen: set[str] = set()
    scored: list[tuple[tuple, DispatchRanking]] = []
    for candidate in candidates:
        if not isinstance(candidate, DispatchCandidate):
            raise DispatchPolicyError("invalid candidate")
        if candidate.ticket_id in seen or candidate.enqueued_ms > now_ms:
            raise DispatchPolicyError("duplicate or future ticket")
        seen.add(candidate.ticket_id)
        wait = now_ms - candidate.enqueued_ms
        protected = candidate.priority <= protected_priority
        floor = 0 if protected else protected_priority + 1
        effective = max(floor, candidate.priority - wait // aging_interval_ms)
        slack = (
            None if candidate.deadline_ms is None else
            candidate.deadline_ms - now_ms - max(candidate.estimated_ms, candidate.critical_path_ms)
        )
        share = Fraction(tenant_active.get(candidate.tenant_id, 0), weights.get(candidate.tenant_id, 1))
        # Protected authority remains above every ordinary lane. Within an
        # effective class, urgent work is first, then the least-loaded tenant.
        key = (
            not protected, effective, slack is None,
            0 if slack is None else slack, share, -wait,
            -candidate.critical_path_ms, -candidate.locality_bytes,
            candidate.estimated_ms, candidate.ticket_id,
        )
        scored.append((key, DispatchRanking(candidate.ticket_id, effective, slack, share, wait)))
    return tuple(row for _, row in sorted(scored, key=lambda item: item[0]))


@dataclass(frozen=True, slots=True)
class ResourceVector:
    units: tuple[tuple[str, int], ...]

    def __post_init__(self) -> None:
        if type(self.units) is not tuple or len(self.units) > MAX_DIMENSIONS:
            raise DispatchPolicyError("invalid resource vector")
        names: list[str] = []
        for pair in self.units:
            if type(pair) is not tuple or len(pair) != 2:
                raise DispatchPolicyError("invalid resource dimension")
            name, value = pair
            names.append(identifier(name))
            bounded_int(value, "resource amount")
        if names != sorted(set(names)):
            raise DispatchPolicyError("resource dimensions must be sorted and unique")

    def fits(self, capacity: ResourceVector) -> bool:
        available = dict(capacity.units)
        return all(name in available and amount <= available[name] for name, amount in self.units)

    def subtract(self, demand: ResourceVector) -> ResourceVector:
        if not demand.fits(self):
            raise DispatchPolicyError("insufficient resource capacity")
        used = dict(demand.units)
        return ResourceVector(tuple((name, amount - used.get(name, 0)) for name, amount in self.units))


@dataclass(frozen=True, slots=True)
class PlacementNode:
    node_id: str
    capacity: ResourceVector
    capabilities: frozenset[str]
    cached_artifacts: frozenset[str] = frozenset()
    failure_domain: str = "local"

    def __post_init__(self) -> None:
        identifier(self.node_id)
        identifier(self.failure_domain)
        if not isinstance(self.capacity, ResourceVector):
            raise DispatchPolicyError("invalid node capacity")
        for values in (self.capabilities, self.cached_artifacts):
            if type(values) is not frozenset or len(values) > 256:
                raise DispatchPolicyError("invalid node metadata")
            for value in values:
                identifier(value)


@dataclass(frozen=True, slots=True)
class PlacementRequest:
    task_id: str
    demand: ResourceVector
    required: frozenset[str] = frozenset()
    artifacts: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        identifier(self.task_id)
        if not isinstance(self.demand, ResourceVector) or not self.demand.units or not any(
            amount > 0 for _, amount in self.demand.units
        ):
            raise DispatchPolicyError("nonempty resource demand required")
        for values in (self.required, self.artifacts):
            if type(values) is not frozenset or len(values) > 256:
                raise DispatchPolicyError("invalid request metadata")
            for value in values:
                identifier(value)


def place_gang(
    requests: Sequence[PlacementRequest], nodes: Sequence[PlacementNode],
    *, spread: bool = False, search_budget: int = 20_000,
) -> tuple[tuple[str, str], ...] | None:
    """Bounded all-or-nothing search over a snapshot; never allocates resources.

    Most constrained members are placed first. Prefer cached artifacts and
    either compact placement or distinct failure domains. A budget-exhausted
    search raises instead of misreporting proof of infeasibility.
    """
    bounded_int(search_budget, "search budget", 1, 1_000_000)
    if type(spread) is not bool or not 1 <= len(requests) <= 64 or not 1 <= len(nodes) <= 256:
        raise DispatchPolicyError("invalid gang size or mode")
    if len({r.task_id for r in requests}) != len(requests) or len({n.node_id for n in nodes}) != len(nodes):
        raise DispatchPolicyError("duplicate placement identity")
    remaining = {n.node_id: n.capacity for n in nodes}
    eligible = {
        r.task_id: tuple(n for n in nodes if r.required <= n.capabilities and r.demand.fits(n.capacity))
        for r in requests
    }
    ordered = sorted(requests, key=lambda r: (len(eligible[r.task_id]), r.task_id))
    choices: dict[str, str] = {}
    domain_load: dict[str, int] = {}
    node_load: dict[str, int] = {}
    visits = 0

    def search(index: int) -> bool:
        nonlocal visits
        if index == len(ordered):
            return True
        request = ordered[index]
        options = sorted(
            eligible[request.task_id],
            key=lambda n: (
                -len(request.artifacts & n.cached_artifacts),
                domain_load.get(n.failure_domain, 0) if spread else -node_load.get(n.node_id, 0),
                n.node_id,
            ),
        )
        for node in options:
            visits += 1
            if visits > search_budget:
                raise DispatchPolicyError("placement search budget exhausted")
            old = remaining[node.node_id]
            if not request.demand.fits(old):
                continue
            remaining[node.node_id] = old.subtract(request.demand)
            choices[request.task_id] = node.node_id
            domain_load[node.failure_domain] = domain_load.get(node.failure_domain, 0) + 1
            node_load[node.node_id] = node_load.get(node.node_id, 0) + 1
            if search(index + 1):
                return True
            remaining[node.node_id] = old
            del choices[request.task_id]
            domain_load[node.failure_domain] -= 1
            node_load[node.node_id] -= 1
        return False

    return tuple(sorted(choices.items())) if search(0) else None


def safe_backfill(
    *, now_ms: int, reservation_ms: int, estimated_ms: int, uncertainty_ms: int,
) -> bool:
    """Do not consume a predicted reserved start; caller must enforce actual stop."""
    bounded_int(now_ms, "time")
    bounded_int(reservation_ms, "reservation")
    bounded_int(estimated_ms, "estimate", 1)
    bounded_int(uncertainty_ms, "uncertainty")
    return now_ms + estimated_ms + uncertainty_ms <= reservation_ms


def critical_paths(
    durations: Mapping[str, int], dependencies: Mapping[str, tuple[str, ...]],
) -> dict[str, int]:
    """Compute downstream critical duration with a bounded iterative DAG pass."""
    if not 1 <= len(durations) <= MAX_CANDIDATES or set(durations) != set(dependencies):
        raise DispatchPolicyError("invalid dependency graph")
    from collections import deque
    children: dict[str, list[str]] = {key: [] for key in durations}
    degree: dict[str, int] = {}
    edges = 0
    for key, cost in durations.items():
        identifier(key)
        bounded_int(cost, "duration", 1)
        parents = dependencies[key]
        if type(parents) is not tuple or len(parents) > 256 or len(set(parents)) != len(parents):
            raise DispatchPolicyError("invalid predecessor list")
        degree[key] = len(parents)
        edges += len(parents)
        if edges > 65_536:
            raise DispatchPolicyError("dependency edge limit exceeded")
        for parent in parents:
            if parent not in children:
                raise DispatchPolicyError("unknown dependency")
            children[parent].append(key)
    ready = deque(sorted(k for k, v in degree.items() if v == 0))
    order: list[str] = []
    while ready:
        key = ready.popleft()
        order.append(key)
        for child in sorted(children[key]):
            degree[child] -= 1
            if degree[child] == 0:
                ready.append(child)
    if len(order) != len(durations):
        raise DispatchPolicyError("dependency cycle")
    result: dict[str, int] = {}
    for key in reversed(order):
        result[key] = durations[key] + max((result[child] for child in children[key]), default=0)
    return result
