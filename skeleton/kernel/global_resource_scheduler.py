"""Global cross-plane resource admission scheduler for hostile gap G021.

Local queues remain responsible for executing work.  This module owns the
single physical-capacity view that local schedulers cannot safely reconstruct.

Semantics:
* all planes consume from one resource vector;
* each plane has a reserved floor and a maximum share;
* idle reserves may be borrowed for work conservation;
* queued demand re-protects the owner's unused reserve;
* weighted dominant-share fairness breaks ties across planes;
* deterministic aging prevents indefinite starvation;
* preemption is two-phase: mark revoking, then release only after ack;
* request identifiers are identity-bound and cannot be reused with new cost.

The scheduler never pretends a revoked task stopped before the executor confirms
it.  Revoking grants therefore continue consuming capacity until ack_preempted.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import json
import math
import threading
from typing import Any
from uuid import uuid4
from collections.abc import Callable


ACTIVE = "active"
REVOKING = "revoking"
QUEUED = "queued"
GRANTED = "granted"
COMPLETED = "completed"
CANCELLED = "cancelled"


class GlobalResourceError(RuntimeError):
    """Base global resource scheduling failure."""


class ResourcePolicyError(GlobalResourceError):
    """Global capacity or plane policy is invalid."""


class ResourceConflict(GlobalResourceError):
    """Request/grant identity or state conflicts with the operation."""


class ResourceUnavailable(GlobalResourceError):
    """No globally safe capacity is currently available."""


def _text(value: object, field: str, *, maximum: int = 256) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ResourcePolicyError(f"{field} must be canonical non-empty text")
    if len(value) > maximum:
        raise ResourcePolicyError(f"{field} exceeds maximum length")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise ResourcePolicyError(f"{field} contains control characters")
    return value


def _integer(
    value: object,
    field: str,
    *,
    minimum: int = 0,
    maximum: int = 1_000_000_000_000,
) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < minimum
        or value > maximum
    ):
        raise ResourcePolicyError(
            f"{field} must be an integer in [{minimum}, {maximum}]"
        )
    return value


def _fraction(value: object, field: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or not 0.0 < float(value) <= 1.0
    ):
        raise ResourcePolicyError(f"{field} must be in (0, 1]")
    return float(value)


@dataclass(frozen=True, slots=True)
class ResourceVector:
    cpu_millis: int = 0
    memory_mb: int = 0
    gpu_millis: int = 0
    io_tokens: int = 0
    provider_tokens: int = 0

    def __post_init__(self) -> None:
        for field in (
            "cpu_millis",
            "memory_mb",
            "gpu_millis",
            "io_tokens",
            "provider_tokens",
        ):
            object.__setattr__(
                self,
                field,
                _integer(getattr(self, field), field),
            )

    @property
    def empty(self) -> bool:
        return all(value == 0 for value in self.values())

    def values(self) -> tuple[int, int, int, int, int]:
        return (
            self.cpu_millis,
            self.memory_mb,
            self.gpu_millis,
            self.io_tokens,
            self.provider_tokens,
        )

    def as_dict(self) -> dict[str, int]:
        return {
            "cpu_millis": self.cpu_millis,
            "memory_mb": self.memory_mb,
            "gpu_millis": self.gpu_millis,
            "io_tokens": self.io_tokens,
            "provider_tokens": self.provider_tokens,
        }

    def add(self, other: "ResourceVector") -> "ResourceVector":
        return ResourceVector(
            *(left + right for left, right in zip(self.values(), other.values()))
        )

    def subtract(self, other: "ResourceVector") -> "ResourceVector":
        values = tuple(
            left - right for left, right in zip(self.values(), other.values())
        )
        if any(value < 0 for value in values):
            raise ResourceConflict("resource accounting would become negative")
        return ResourceVector(*values)

    def deficit_from(self, floor: "ResourceVector") -> "ResourceVector":
        return ResourceVector(
            *(max(0, wanted - have) for have, wanted in zip(self.values(), floor.values()))
        )

    def fits_within(self, capacity: "ResourceVector") -> bool:
        return all(
            value <= limit
            for value, limit in zip(self.values(), capacity.values())
        )

    def exceeds_fraction(
        self,
        capacity: "ResourceVector",
        fraction: float,
    ) -> bool:
        for value, total in zip(self.values(), capacity.values()):
            if total == 0:
                if value:
                    return True
                continue
            if value / total > fraction + 1e-12:
                return True
        return False

    def dominant_share(self, capacity: "ResourceVector") -> float:
        shares: list[float] = []
        for value, total in zip(self.values(), capacity.values()):
            if total == 0:
                if value:
                    return math.inf
                continue
            shares.append(value / total)
        return max(shares, default=0.0)


@dataclass(frozen=True, slots=True)
class PlanePolicy:
    name: str
    weight: float
    reserved: ResourceVector
    max_fraction: float = 1.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _text(self.name, "plane.name"))
        if (
            isinstance(self.weight, bool)
            or not isinstance(self.weight, (int, float))
            or not math.isfinite(float(self.weight))
            or float(self.weight) <= 0
        ):
            raise ResourcePolicyError("plane.weight must be positive finite")
        object.__setattr__(self, "weight", float(self.weight))
        if not isinstance(self.reserved, ResourceVector):
            raise ResourcePolicyError("plane.reserved must be ResourceVector")
        object.__setattr__(
            self,
            "max_fraction",
            _fraction(self.max_fraction, "plane.max_fraction"),
        )


@dataclass(frozen=True, slots=True)
class TenantResourcePolicy:
    """Optional cross-plane ceiling. A tenant cannot multiply its cap by plane."""

    tenant_id: str
    maximum: ResourceVector

    def __post_init__(self) -> None:
        object.__setattr__(self, "tenant_id", _text(self.tenant_id, "tenant"))
        if not isinstance(self.maximum, ResourceVector) or self.maximum.empty:
            raise ResourcePolicyError("tenant maximum must be nonempty resources")


@dataclass(frozen=True, slots=True)
class GlobalResourcePolicy:
    total: ResourceVector
    planes: tuple[PlanePolicy, ...]
    aging_interval: int = 8
    tenant_limits: tuple[TenantResourcePolicy, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.total, ResourceVector) or self.total.empty:
            raise ResourcePolicyError("total capacity must be non-empty")
        planes = tuple(self.planes)
        if not planes:
            raise ResourcePolicyError("at least one plane policy is required")
        if len({plane.name for plane in planes}) != len(planes):
            raise ResourcePolicyError("duplicate plane policy")
        if any(not plane.reserved.fits_within(self.total) for plane in planes):
            raise ResourcePolicyError("plane reserve exceeds global capacity")
        reserve_sum = ResourceVector()
        for plane in planes:
            reserve_sum = reserve_sum.add(plane.reserved)
            if plane.reserved.exceeds_fraction(
                self.total, plane.max_fraction
            ):
                raise ResourcePolicyError(
                    f"{plane.name} reserve exceeds its maximum share"
                )
        if not reserve_sum.fits_within(self.total):
            raise ResourcePolicyError(
                "sum of plane reserves exceeds global capacity"
            )
        object.__setattr__(self, "planes", tuple(sorted(planes, key=lambda p: p.name)))
        if type(self.tenant_limits) is not tuple or len(self.tenant_limits) > 4096:
            raise ResourcePolicyError("invalid tenant limits")
        if any(not isinstance(t, TenantResourcePolicy) for t in self.tenant_limits):
            raise ResourcePolicyError("invalid tenant policy")
        if len({t.tenant_id for t in self.tenant_limits}) != len(self.tenant_limits):
            raise ResourcePolicyError("duplicate tenant policy")
        if any(not t.maximum.fits_within(self.total) for t in self.tenant_limits):
            raise ResourcePolicyError("tenant maximum exceeds global resources")
        object.__setattr__(self, "tenant_limits",
                           tuple(sorted(self.tenant_limits, key=lambda t: t.tenant_id)))
        object.__setattr__(
            self,
            "aging_interval",
            _integer(
                self.aging_interval,
                "aging_interval",
                minimum=1,
                maximum=1_000_000,
            ),
        )

    def plane(self, name: str) -> PlanePolicy:
        canonical = _text(name, "plane")
        for plane in self.planes:
            if plane.name == canonical:
                return plane
        raise ResourcePolicyError(f"unknown resource plane: {canonical}")


@dataclass(frozen=True, slots=True)
class ResourceRequest:
    request_id: str
    plane: str
    tenant_id: str
    resources: ResourceVector
    priority: int = 5
    preemptible: bool = True
    deadline_tick: int | None = None
    estimated_ticks: int = 1

    def __post_init__(self) -> None:
        object.__setattr__(self, "request_id", _text(self.request_id, "request_id"))
        object.__setattr__(self, "plane", _text(self.plane, "plane"))
        object.__setattr__(self, "tenant_id", _text(self.tenant_id, "tenant_id"))
        if not isinstance(self.resources, ResourceVector) or self.resources.empty:
            raise ResourcePolicyError("request resources must be non-empty")
        object.__setattr__(
            self,
            "priority",
            _integer(self.priority, "priority", minimum=0, maximum=9),
        )
        if not isinstance(self.preemptible, bool):
            raise ResourcePolicyError("preemptible must be boolean")
        if self.deadline_tick is not None:
            _integer(self.deadline_tick, "deadline_tick", minimum=1)
        _integer(self.estimated_ticks, "estimated_ticks", minimum=1)
        if self.deadline_tick is not None and self.estimated_ticks > self.deadline_tick:
            raise ResourcePolicyError("estimated service exceeds deadline")

    @property
    def identity_digest(self) -> str:
        encoded = json.dumps(
            {
                "request_id": self.request_id,
                "plane": self.plane,
                "tenant_id": self.tenant_id,
                "resources": self.resources.as_dict(),
                "priority": self.priority,
                "preemptible": self.preemptible,
                **({"deadline_tick": self.deadline_tick, "estimated_ticks": self.estimated_ticks}
                   if self.deadline_tick is not None or self.estimated_ticks != 1 else {}),
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class RequestTicket:
    request: ResourceRequest
    submitted_tick: int
    status: str
    grant_id: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request.request_id,
            "plane": self.request.plane,
            "tenant_id": self.request.tenant_id,
            "resources": self.request.resources.as_dict(),
            "priority": self.request.priority,
            "preemptible": self.request.preemptible,
            "deadline_tick": self.request.deadline_tick,
            "estimated_ticks": self.request.estimated_ticks,
            "submitted_tick": self.submitted_tick,
            "status": self.status,
            "grant_id": self.grant_id,
        }


@dataclass(frozen=True, slots=True)
class ResourceGrant:
    grant_id: str
    request_id: str
    plane: str
    tenant_id: str
    resources: ResourceVector
    priority: int
    preemptible: bool
    borrowed: bool
    granted_tick: int
    state: str = ACTIVE
    revoking_for_request_id: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "grant_id": self.grant_id,
            "request_id": self.request_id,
            "plane": self.plane,
            "tenant_id": self.tenant_id,
            "resources": self.resources.as_dict(),
            "priority": self.priority,
            "preemptible": self.preemptible,
            "borrowed": self.borrowed,
            "granted_tick": self.granted_tick,
            "state": self.state,
            "revoking_for_request_id": self.revoking_for_request_id,
        }


@dataclass(frozen=True, slots=True)
class AllocationSublease:
    sublease_id: str
    parent_id: str
    root_grant_id: str
    tenant_id: str
    resources: ResourceVector
    depth: int
    token: str
    state: str = ACTIVE


class GlobalResourceScheduler:
    """Deterministic cross-plane capacity, fairness, and preemption authority."""

    def __init__(self, policy: GlobalResourcePolicy) -> None:
        if not isinstance(policy, GlobalResourcePolicy):
            raise TypeError("policy must be GlobalResourcePolicy")
        self.policy = policy
        self._planes = {plane.name: plane for plane in policy.planes}
        self._tenant_limits = {t.tenant_id: t.maximum for t in policy.tenant_limits}
        self._usage = {plane.name: ResourceVector() for plane in policy.planes}
        self._requests: dict[str, RequestTicket] = {}
        self._grants: dict[str, ResourceGrant] = {}
        self._tick = 0
        self._grant_sequence = 0
        self._group_receipts: dict[str, tuple[tuple[tuple[str, str], ...], tuple[str, ...]]] = {}
        self._subleases: dict[str, AllocationSublease] = {}
        self._children: dict[str, set[str]] = {}
        self._delegated: dict[str, ResourceVector] = {}
        self._lock = threading.RLock()

    @property
    def tick(self) -> int:
        with self._lock:
            return self._tick

    def advance(self, steps: int = 1) -> int:
        count = _integer(steps, "steps", minimum=1, maximum=1_000_000)
        with self._lock:
            self._tick += count
            return self._tick

    def submit(self, request: ResourceRequest) -> RequestTicket:
        if not isinstance(request, ResourceRequest):
            raise TypeError("request must be ResourceRequest")
        plane = self.policy.plane(request.plane)
        if not request.resources.fits_within(self.policy.total):
            raise ResourcePolicyError("request exceeds global physical capacity")
        if request.resources.exceeds_fraction(
            self.policy.total, plane.max_fraction
        ):
            raise ResourcePolicyError("request exceeds plane maximum share")
        maximum = self._tenant_limits.get(request.tenant_id)
        if maximum is not None and not request.resources.fits_within(maximum):
            raise ResourcePolicyError("request exceeds tenant maximum")
        with self._lock:
            prior = self._requests.get(request.request_id)
            if prior is not None:
                if prior.request.identity_digest != request.identity_digest:
                    raise ResourceConflict(
                        "request_id replay changed resource identity"
                    )
                return prior
            self._tick += 1
            ticket = RequestTicket(request, self._tick, QUEUED)
            self._requests[request.request_id] = ticket
            return ticket

    def reserve_group(
        self, group_id: str, requests: tuple[ResourceRequest, ...]
    ) -> tuple[ResourceGrant, ...] | None:
        """Atomically submit AND reserve a bounded same-tenant resource group.

        The caller is the existing resource admission owner, not a model. A
        failed group creates no member tickets, so ordinary dispatch cannot
        accidentally start half of it. Existing queued runnable work and
        protected plane reserves retain precedence. This local authority owns
        declared resource vectors; host allocation and acknowledgement remain
        the responsibility of the existing executor.
        """
        group_id = _text(group_id, "group_id")
        if type(requests) is not tuple or not 1 <= len(requests) <= 64:
            raise ResourcePolicyError("group must contain between 1 and 64 requests")
        if any(not isinstance(request, ResourceRequest) for request in requests):
            raise ResourcePolicyError("invalid group member")
        if len({r.request_id for r in requests}) != len(requests):
            raise ResourceConflict("duplicate group request")
        if len({r.tenant_id for r in requests}) != 1:
            raise ResourceConflict("resource group must have one tenant")
        ordered = tuple(sorted(requests, key=lambda r: (r.priority, r.request_id)))
        identities = tuple((r.request_id, r.identity_digest) for r in ordered)
        for request in ordered:
            plane = self.policy.plane(request.plane)
            if not request.resources.fits_within(self.policy.total):
                raise ResourcePolicyError("group member exceeds global capacity")
            if request.resources.exceeds_fraction(self.policy.total, plane.max_fraction):
                raise ResourcePolicyError("group member exceeds plane share")

        with self._lock:
            existing = self._group_receipts.get(group_id)
            if existing is not None:
                prior_identities, grant_ids = existing
                if identities != prior_identities:
                    raise ResourceConflict("group replay changed resource identity")
                grants = tuple(self._require_grant(grant_id) for grant_id in grant_ids)
                if any(grant.state != ACTIVE for grant in grants):
                    raise ResourceConflict("resource group is no longer fully active")
                return grants
            if len(self._group_receipts) >= 4096:
                raise ResourceUnavailable("resource group receipt capacity exhausted")
            if any(r.request_id in self._requests for r in ordered):
                raise ResourceConflict("group member already has a resource ticket")

            # No queue identities, usage, grants or ticks are modified until all
            # members are proven to fit the same immutable logical snapshot.
            tickets = tuple(RequestTicket(r, self._tick + 1, QUEUED) for r in ordered)
            incumbent = self._select_candidate()
            if incumbent is not None and any(
                self._candidate_score(incumbent) < self._candidate_score(ticket)
                for ticket in tickets
            ):
                return None
            simulated = dict(self._usage)
            simulated_tenant = self._tenant_usage(ordered[0].tenant_id)
            for ticket in tickets:
                if not self._fits_with_usage(ticket, simulated, tenant_usage=simulated_tenant,
                                             at_tick=self._tick + 1):
                    return None
                plane_name = ticket.request.plane
                simulated[plane_name] = simulated[plane_name].add(ticket.request.resources)
                simulated_tenant = simulated_tenant.add(ticket.request.resources)

            # All publication occurs under the same existing reentrant lock.
            # Roll back per-group mutations on an unexpected publication error.
            previous_tick, previous_sequence = self._tick, self._grant_sequence
            previous_usage = dict(self._usage)
            member_ids = {ticket.request.request_id for ticket in tickets}
            grants: list[ResourceGrant] = []
            try:
                self._tick += 1
                for ticket in tickets:
                    self._requests[ticket.request.request_id] = ticket
                    grants.append(self._grant(ticket))
                self._group_receipts[group_id] = (identities, tuple(g.grant_id for g in grants))
            except Exception:
                self._tick, self._grant_sequence = previous_tick, previous_sequence
                self._usage = previous_usage
                for request_id in member_ids:
                    self._requests.pop(request_id, None)
                for grant_id, grant in tuple(self._grants.items()):
                    if grant.request_id in member_ids:
                        del self._grants[grant_id]
                self._group_receipts.pop(group_id, None)
                raise
            return tuple(grants)

    def cancel(self, request_id: str) -> RequestTicket:
        request_id = _text(request_id, "request_id")
        with self._lock:
            ticket = self._require_ticket(request_id)
            if ticket.status == QUEUED:
                ticket = replace(ticket, status=CANCELLED)
                self._requests[request_id] = ticket
                for grant_id, grant in tuple(self._grants.items()):
                    if (
                        grant.state == REVOKING
                        and grant.revoking_for_request_id == request_id
                    ):
                        self._grants[grant_id] = replace(
                            grant,
                            state=ACTIVE,
                            revoking_for_request_id=None,
                        )
                return ticket
            if ticket.status == CANCELLED:
                return ticket
            raise ResourceConflict("only queued resource requests can be cancelled")

    def admit_next(self) -> ResourceGrant | None:
        with self._lock:
            self._tick += 1
            candidate = self._select_candidate()
            if candidate is None:
                return None
            return self._grant(candidate)

    def admit_request(self, request_id: str) -> ResourceGrant | None:
        """Admit only if this request is the globally selected next candidate."""

        request_id = _text(request_id, "request_id")
        with self._lock:
            ticket = self._require_ticket(request_id)
            if ticket.status == GRANTED and ticket.grant_id is not None:
                return self._grants[ticket.grant_id]
            if ticket.status != QUEUED:
                return None
            self._tick += 1
            candidate = self._select_candidate()
            if candidate is None or candidate.request.request_id != request_id:
                return None
            return self._grant(candidate)

    def reserve_sublease(self, parent_id: str, sublease_id: str, tenant_id: str,
                         resources: ResourceVector, *, parent_token: str | None = None
                         ) -> AllocationSublease | None:
        """Partition an existing grant, never allocate additional global capacity.

        Trusted host API: root identity alone is not caller authentication.
        Descendants additionally require the exact parent attempt token.
        Completed identities remain tombstones; no implicit recycling.
        """
        parent_id, sublease_id, tenant_id = (_text(v, "allocation identity")
                                              for v in (parent_id, sublease_id, tenant_id))
        if not isinstance(resources, ResourceVector) or resources.empty:
            raise ResourcePolicyError("empty sublease resources")
        with self._lock:
            parent = self._subleases.get(parent_id)
            if parent is not None:
                if parent.token != parent_token or parent.state != ACTIVE:
                    raise ResourceConflict("stale or stopped parent allocation")
                root = self._require_grant(parent.root_grant_id)
                capacity, depth = parent.resources, parent.depth + 1
            else:
                if parent_token is not None:
                    raise ResourceConflict("unexpected root token")
                root = self._require_grant(parent_id)
                capacity, depth = root.resources, 1
            if root.state != ACTIVE or root.tenant_id != tenant_id or depth > 8:
                raise ResourceConflict("allocation authority unavailable")
            prior = self._subleases.get(sublease_id)
            if prior is not None:
                if (prior.parent_id, prior.tenant_id, prior.resources) != (parent_id, tenant_id, resources):
                    raise ResourceConflict("sublease identity conflict")
                return prior if prior.state == ACTIVE else None
            if sublease_id in self._grants or sublease_id.startswith("grant-"):
                raise ResourceConflict("reserved root identity namespace")
            if len(self._subleases) >= 100000:
                raise ResourceUnavailable("sublease identity retention exhausted")
            delegated = self._delegated.get(parent_id, ResourceVector())
            if not resources.fits_within(capacity.subtract(delegated)):
                return None
            record = AllocationSublease(sublease_id, parent_id, root.grant_id, tenant_id,
                                        resources, depth, uuid4().hex)
            self._subleases[sublease_id] = record
            self._children.setdefault(parent_id, set()).add(sublease_id)
            self._delegated[parent_id] = delegated.add(resources)
            return record

    def allocation_remaining(self, parent_id: str) -> ResourceVector:
        with self._lock:
            child = self._subleases.get(parent_id)
            if child is not None:
                if child.state != ACTIVE:
                    return ResourceVector()
                root = self._require_grant(child.root_grant_id)
                capacity = child.resources
            else:
                root = self._require_grant(parent_id)
                capacity = root.resources
            if root.state != ACTIVE:
                return ResourceVector()
            return capacity.subtract(self._delegated.get(parent_id, ResourceVector()))

    def _mark_subtree_revoking(self, parent_id: str) -> tuple[AllocationSublease, ...]:
        pending = list(self._children.get(parent_id, ()))
        result = []
        while pending:
            key = pending.pop()
            row = self._subleases[key]
            if row.state == COMPLETED:
                continue
            row = replace(row, state=REVOKING)
            self._subleases[key] = row
            result.append(row)
            pending.extend(self._children.get(key, ()))
        return tuple(sorted(result, key=lambda row: (-row.depth, row.sublease_id)))

    def begin_sublease_reclamation(self, sublease_id: str, *, token: str) -> tuple[AllocationSublease, ...]:
        with self._lock:
            row = self._subleases.get(sublease_id)
            if row is None or row.token != token or row.state == COMPLETED:
                raise ResourceConflict("invalid sublease reclamation identity")
            row = replace(row, state=REVOKING)
            self._subleases[sublease_id] = row
            return self._mark_subtree_revoking(sublease_id) + (row,)

    def acknowledge_sublease_stop(self, sublease_id: str, *, token: str, evidence_sha256: str,
                                   verify_stop: Callable[[str, str, str], bool]) -> AllocationSublease:
        """Retain every delegation until independently verified stop and leaf-first ack."""
        if (not callable(verify_stop) or type(evidence_sha256) is not str
                or len(evidence_sha256) != 64 or any(c not in "0123456789abcdef" for c in evidence_sha256)):
            raise ResourcePolicyError("invalid stop evidence")
        with self._lock:
            row = self._subleases.get(sublease_id)
            if row is None or row.token != token:
                raise ResourceConflict("stale sublease token")
            if row.state == COMPLETED:
                return row
            if row.state != REVOKING or self._children.get(sublease_id):
                raise ResourceConflict("reclamation requires stopped descendants")
        if verify_stop(sublease_id, token, evidence_sha256) is not True:
            raise ResourceConflict("stop evidence refused")
        with self._lock:
            current = self._subleases.get(sublease_id)
            if current != row or self._children.get(sublease_id):
                raise ResourceConflict("allocation changed during verification")
            completed = replace(row, state=COMPLETED)
            self._subleases[sublease_id] = completed
            self._children[row.parent_id].discard(sublease_id)
            self._delegated[row.parent_id] = self._delegated[row.parent_id].subtract(row.resources)
            return completed

    def subleases(self, root_grant_id: str) -> tuple[AllocationSublease, ...]:
        with self._lock:
            self._require_grant(root_grant_id)
            return tuple(sorted((r for r in self._subleases.values()
                                 if r.root_grant_id == root_grant_id and r.state != COMPLETED),
                                key=lambda r: (-r.depth, r.sublease_id)))

    def release(self, grant_id: str) -> ResourceGrant:
        grant_id = _text(grant_id, "grant_id")
        with self._lock:
            grant = self._require_grant(grant_id)
            if grant.state not in {ACTIVE, REVOKING}:
                return grant
            if self._children.get(grant_id):
                raise ResourceConflict("delegated allocations must be reconciled before root release")
            self._usage[grant.plane] = self._usage[grant.plane].subtract(
                grant.resources
            )
            released = replace(grant, state=COMPLETED)
            self._grants[grant_id] = released
            ticket = self._require_ticket(grant.request_id)
            self._requests[grant.request_id] = replace(
                ticket,
                status=COMPLETED,
                grant_id=grant_id,
            )
            self._tick += 1
            return released

    def begin_preemption(self, request_id: str) -> tuple[ResourceGrant, ...]:
        """Mark lower-priority grants revoking without freeing their capacity."""

        request_id = _text(request_id, "request_id")
        with self._lock:
            ticket = self._require_ticket(request_id)
            if ticket.status != QUEUED:
                raise ResourceConflict("preemption requires a queued request")
            # A previous revocation wave is still physically occupied. Return
            # the exact outstanding set instead of over-revoking other grants.
            outstanding = tuple(g for g in self._grants.values()
                                if g.state == REVOKING and g.revoking_for_request_id == request_id)
            if outstanding:
                return tuple(sorted(outstanding, key=lambda g: g.grant_id))
            self._tick += 1
            if self._fits_candidate(ticket) or not self._deadline_possible(ticket):
                return ()
            needed = ticket.request
            request_priority = self._effective_priority(ticket)
            candidates = [
                grant
                for grant in self._grants.values()
                if grant.state == ACTIVE
                and grant.preemptible
                and grant.request_id != request_id
                and (
                    grant.priority > request_priority
                    or self._deadline_precedes(ticket, grant)
                    or (grant.borrowed and grant.plane != needed.plane
                        and not self._usage[needed.plane].deficit_from(self._planes[needed.plane].reserved).empty)
                )
            ]
            candidates.sort(
                key=lambda grant: (
                    0 if grant.borrowed else 1,
                    -grant.priority,
                    -grant.granted_tick,
                    grant.grant_id,
                )
            )
            simulated = dict(self._usage)
            simulated_tenant = self._tenant_usage(needed.tenant_id)
            selected: list[ResourceGrant] = []
            for grant in candidates:
                simulated[grant.plane] = simulated[grant.plane].subtract(
                    grant.resources
                )
                if grant.tenant_id == needed.tenant_id:
                    simulated_tenant = simulated_tenant.subtract(grant.resources)
                selected.append(grant)
                if self._fits_with_usage(ticket, simulated, tenant_usage=simulated_tenant):
                    break
            else:
                return ()

            marked: list[ResourceGrant] = []
            for grant in selected:
                revoking = replace(
                    grant,
                    state=REVOKING,
                    revoking_for_request_id=request_id,
                )
                self._grants[grant.grant_id] = revoking
                self._mark_subtree_revoking(grant.grant_id)
                marked.append(revoking)
            return tuple(marked)

    def ack_preempted(self, grant_id: str) -> ResourceGrant:
        grant_id = _text(grant_id, "grant_id")
        with self._lock:
            grant = self._require_grant(grant_id)
            if grant.state != REVOKING:
                raise ResourceConflict("grant is not awaiting preemption ack")
            target_id = grant.revoking_for_request_id
            if target_id is None:
                raise ResourceConflict("revoking grant lacks target request")
            target = self._require_ticket(target_id)
            if target.status != QUEUED:
                raise ResourceConflict(
                    "preemption target is no longer queued"
                )
            # Keep target validation and definitive release under the same lock.
            return self.release(grant_id)

    def queued(self) -> tuple[RequestTicket, ...]:
        with self._lock:
            values = [
                ticket
                for ticket in self._requests.values()
                if ticket.status == QUEUED
            ]
            return tuple(sorted(values, key=self._candidate_score))

    def active_grants(self) -> tuple[ResourceGrant, ...]:
        with self._lock:
            return tuple(
                sorted(
                    (
                        grant
                        for grant in self._grants.values()
                        if grant.state in {ACTIVE, REVOKING}
                    ),
                    key=lambda grant: (grant.granted_tick, grant.grant_id),
                )
            )

    def usage(self, plane: str | None = None) -> ResourceVector | dict[str, ResourceVector]:
        with self._lock:
            if plane is None:
                return dict(self._usage)
            name = self.policy.plane(plane).name
            return self._usage[name]

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "kind": "global_resource_scheduler",
                "tenant_limits": {
                    tenant: {"usage": self._tenant_usage(tenant).as_dict(), "maximum": cap.as_dict()}
                    for tenant, cap in sorted(self._tenant_limits.items())
                },
                "deadline_blocked": sum(
                    ticket.status == QUEUED and not self._deadline_possible(ticket)
                    for ticket in self._requests.values()
                ),
                "subleases_active": sum(r.state == ACTIVE for r in self._subleases.values()),
                "subleases_revoking": sum(r.state == REVOKING for r in self._subleases.values()),
                "gap": "G021",
                "tick": self._tick,
                "total": self.policy.total.as_dict(),
                "planes": {
                    name: {
                        "usage": self._usage[name].as_dict(),
                        "reserved": policy.reserved.as_dict(),
                        "weight": policy.weight,
                        "max_fraction": policy.max_fraction,
                        "dominant_share": self._usage[name].dominant_share(
                            self.policy.total
                        ),
                    }
                    for name, policy in sorted(self._planes.items())
                },
                "queued": sum(
                    1 for ticket in self._requests.values()
                    if ticket.status == QUEUED
                ),
                "active": sum(
                    1 for grant in self._grants.values()
                    if grant.state == ACTIVE
                ),
                "revoking": sum(
                    1 for grant in self._grants.values()
                    if grant.state == REVOKING
                ),
                "completion_checkbox": False,
                "implementation_signature": False,
                "verification_signature": False,
            }

    def _grant(self, ticket: RequestTicket) -> ResourceGrant:
        request = ticket.request
        plane = self._planes[request.plane]
        projected = self._usage[request.plane].add(request.resources)
        borrowed = any(
            value > reserve
            for value, reserve in zip(
                projected.values(), plane.reserved.values()
            )
        )
        self._grant_sequence += 1
        material = (
            request.identity_digest
            + ":"
            + str(self._grant_sequence)
            + ":"
            + str(self._tick)
        ).encode("utf-8")
        grant_id = "grant-" + hashlib.sha256(material).hexdigest()[:24]
        grant = ResourceGrant(
            grant_id=grant_id,
            request_id=request.request_id,
            plane=request.plane,
            tenant_id=request.tenant_id,
            resources=request.resources,
            priority=request.priority,
            preemptible=request.preemptible,
            borrowed=borrowed,
            granted_tick=self._tick,
        )
        self._usage[request.plane] = projected
        self._grants[grant_id] = grant
        self._requests[request.request_id] = replace(
            ticket,
            status=GRANTED,
            grant_id=grant_id,
        )
        return grant

    def _select_candidate(self) -> RequestTicket | None:
        candidates = [
            ticket
            for ticket in self._requests.values()
            if ticket.status == QUEUED and self._fits_candidate(ticket)
        ]
        if not candidates:
            return None
        return min(candidates, key=self._candidate_score)

    def _candidate_score(self, ticket: RequestTicket) -> tuple[Any, ...]:
        plane = self._planes[ticket.request.plane]
        usage = self._usage[ticket.request.plane]
        below_reserve = any(
            have < floor
            for have, floor in zip(usage.values(), plane.reserved.values())
        )
        fairness = usage.dominant_share(self.policy.total) / plane.weight
        return (
            self._effective_priority(ticket),
            ticket.request.deadline_tick is None,
            (ticket.request.deadline_tick - self._tick - ticket.request.estimated_ticks
             if ticket.request.deadline_tick is not None else 0),
            0 if below_reserve else 1,
            fairness,
            ticket.submitted_tick,
            ticket.request.request_id,
        )

    def _effective_priority(self, ticket: RequestTicket) -> int:
        age = max(0, self._tick - ticket.submitted_tick)
        improvement = max(0, (age - 1) // self.policy.aging_interval)
        return max(0, ticket.request.priority - improvement)

    def _deadline_possible(self, ticket: RequestTicket, at_tick: int | None = None) -> bool:
        deadline = ticket.request.deadline_tick
        return deadline is None or (self._tick if at_tick is None else at_tick) + ticket.request.estimated_ticks <= deadline

    def _deadline_precedes(self, ticket: RequestTicket, grant: ResourceGrant) -> bool:
        # Deadline promotion stays inside the same or lower original urgency.
        # Never preempt a more protected original priority class for a deadline.
        incoming = ticket.request
        if incoming.deadline_tick is None or incoming.priority > grant.priority:
            return False
        incumbent = self._require_ticket(grant.request_id).request
        if incumbent.deadline_tick is None:
            return True
        # Conservative full remaining service (no assumed progress).
        return incoming.deadline_tick - incoming.estimated_ticks < incumbent.deadline_tick - incumbent.estimated_ticks

    def _tenant_usage(self, tenant_id: str) -> ResourceVector:
        result = ResourceVector()
        for grant in self._grants.values():
            if grant.tenant_id == tenant_id and grant.state in {ACTIVE, REVOKING}:
                result = result.add(grant.resources)
        return result

    def _fits_candidate(self, ticket: RequestTicket) -> bool:
        if any(g.state == REVOKING and g.revoking_for_request_id == ticket.request.request_id
               for g in self._grants.values()):
            return False
        return self._fits_with_usage(ticket, self._usage)

    def _fits_with_usage(
        self,
        ticket: RequestTicket,
        usage: dict[str, ResourceVector],
        *,
        tenant_usage: ResourceVector | None = None,
        at_tick: int | None = None,
    ) -> bool:
        request = ticket.request
        if not self._deadline_possible(ticket, at_tick):
            return False
        cap = self._tenant_limits.get(request.tenant_id)
        if cap is not None:
            used = self._tenant_usage(request.tenant_id) if tenant_usage is None else tenant_usage
            if not request.resources.fits_within(cap.subtract(used)):
                return False
        plane = self._planes[request.plane]
        total_usage = ResourceVector()
        for value in usage.values():
            total_usage = total_usage.add(value)
        available = self.policy.total.subtract(total_usage)
        if not request.resources.fits_within(available):
            return False
        projected = usage[request.plane].add(request.resources)
        if projected.exceeds_fraction(self.policy.total, plane.max_fraction):
            return False

        protected = ResourceVector()
        for other_name, other_policy in self._planes.items():
            if other_name == request.plane:
                continue
            if not self._plane_has_queued_demand(other_name):
                continue
            protected = protected.add(
                usage[other_name].deficit_from(other_policy.reserved)
            )
        usable = ResourceVector(
            *(
                max(0, free - reserve)
                for free, reserve in zip(
                    available.values(), protected.values()
                )
            )
        )
        return request.resources.fits_within(usable)

    def _plane_has_queued_demand(self, plane: str) -> bool:
        return any(
            ticket.status == QUEUED and ticket.request.plane == plane
            and self._deadline_possible(ticket)
            for ticket in self._requests.values()
        )

    def _require_ticket(self, request_id: str) -> RequestTicket:
        ticket = self._requests.get(request_id)
        if ticket is None:
            raise ResourceConflict(f"unknown resource request: {request_id}")
        return ticket

    def _require_grant(self, grant_id: str) -> ResourceGrant:
        grant = self._grants.get(grant_id)
        if grant is None:
            raise ResourceConflict(f"unknown resource grant: {grant_id}")
        return grant


__all__ = [
    "ACTIVE",
    "CANCELLED",
    "COMPLETED",
    "GRANTED",
    "GlobalResourceError",
    "GlobalResourcePolicy",
    "GlobalResourceScheduler",
    "PlanePolicy",
    "QUEUED",
    "REVOKING",
    "RequestTicket",
    "ResourceConflict",
    "ResourceGrant",
    "ResourcePolicyError",
    "ResourceRequest",
    "ResourceUnavailable",
    "ResourceVector",
]
