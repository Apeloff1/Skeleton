"""CAS-bound hypothetical dispatch envelope and replay-only work fingerprints.

Never return URL paths, plaintext untrusted content, authentication claims
or a ready-to-run worker command. The canonical runner must separately
authorize every request, recheck current robots, enforce DNS socket bindings
and durably reserve its worst-case request and byte cost before network I/O.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from urllib.parse import urlsplit

from ..operations import CrawlRun
from .budget import BudgetProjection, verify_projected_budget
from .contracts import CampaignMandate, digest, ensure_snapshot_scope, integer
from .frontier_route_map import CrawlRouteTopology
from .slice_simulation import HypotheticalSlicePlan, simulate_canonical_slice
from .pressure import PressureDecision
from .ops_capacity import CapacityEnvelope
from .ops_host_governor import HostGovernor
from .ops_recovery import RecoveryHandshake


@dataclass(frozen=True)
class ProposedWorkFingerprint:
    ordinal: int
    opaque_url_digest: str
    host: str
    action: str
    planned_ready_at: float
    worst_case_request_bytes: int
    requires_live_robots_check: bool
    requires_dns_pinning_and_worker_lease: bool = True
    actual_request_performed: bool = False


@dataclass(frozen=True)
class DispatchEnvelope:
    mandate_digest: str
    source_snapshot_digest: str
    run_sequence: int
    routes_digest: str
    host_governor_digest: str
    recovery_digest: str
    capacity_digest: str
    hypothetical_slice_digest: str
    issued_at: float
    expires_at: float
    steps: tuple[ProposedWorkFingerprint, ...]
    feasible_hypothetical_requests: int
    full_response_byte_reserve: int
    blocked_reasons: tuple[str, ...]
    suppressed_candidate_count: int
    envelope_digest: str
    physical_worker_lease_granted: bool = False
    persistent_reservation_committed: bool = False
    execution_capability_issued: bool = False
    actual_network_executed: bool = False


def prepare_dispatch_envelope(
    mandate: CampaignMandate, snapshot: dict[str, object],
    budget: BudgetProjection, routes: CrawlRouteTopology,
    governor: HostGovernor, recovery: RecoveryHandshake,
    capacity: CapacityEnvelope, *, now: float, authorized: bool,
    pressure: PressureDecision | None = None,
    max_steps: int = 4,
) -> tuple[DispatchEnvelope, HypotheticalSlicePlan]:
    mandate.admit(now=now, authorized=authorized)
    ensure_snapshot_scope(snapshot, mandate)
    integer(max_steps, "operational slice maximum", 1, 4)
    actual = CrawlRun.from_snapshot(snapshot).snapshot()
    verify_projected_budget(actual, mandate, budget)
    if (
        routes.mandate_digest != mandate.fingerprint
        or routes.source_snapshot_digest != actual["snapshot_digest"]
        or governor.mandate_digest != mandate.fingerprint
        or governor.source_snapshot_digest != actual["snapshot_digest"]
        or recovery.mandate_digest != mandate.fingerprint
        or recovery.source_snapshot_digest != actual["snapshot_digest"]
        or recovery.run_sequence != actual["sequence"]
        or capacity.mandate_digest != mandate.fingerprint
        or capacity.governor_digest != governor.governor_digest
        or capacity.recovery_digest != recovery.handshake_digest
        or capacity.pressure_digest != (pressure.decision_digest if pressure else None)
    ):
        raise PermissionError("operational admission receipts are detached or forged")
    simulation = simulate_canonical_slice(
        mandate, actual, routes, budget, now=now, authorized=authorized,
        pressure=pressure, max_steps=max_steps,
    )
    holds = set(capacity.holds) | set(recovery.held_reasons) | set(simulation.terminal_blockers)
    if not recovery.witness_present:
        holds.add("no_authenticated_worker_or_checkpoint_witness")
    # A caller-supplied witness is *never* equivalent to backend lease fencing.
    holds.add("requires_fresh_backend_admission_before_any_network")
    possible = (not capacity.holds and not recovery.held_reasons
                and capacity.suggested_slice_steps > 0)
    max_count = min(
        max_steps, capacity.suggested_slice_steps, len(simulation.steps),
        budget.requests_remaining, budget.documents_remaining,
    ) if possible else 0
    frontier_ids = {row["url"] for row in actual["frontier"]}
    allowed_origins = {x.origin: x for x in governor.origins}
    proposed = []
    charged = 0
    for step in simulation.steps[:max_count]:
        if step.url not in frontier_ids:
            raise PermissionError("hypothetical work URL not in committed frontier")
        host_origin = urlsplit(step.url)
        if step.host not in mandate.scope.allowed_hosts or step.host != host_origin.hostname:
            raise PermissionError("hypothetical host escaped consent")
        guard = allowed_origins.get(step.origin)
        if guard is None or guard.host != step.host:
            raise PermissionError("hypothetical origin missing exact safety receipt")
        if step.conservative_reserve_bytes > mandate.request.max_response_bytes:
            raise PermissionError("hypothetical request exceeds bounded response bytes")
        charged += step.conservative_reserve_bytes
        if charged > budget.bytes_remaining:
            raise PermissionError("hypothetical plan overdraws remaining byte grant")
        proposed.append(ProposedWorkFingerprint(
            step.ordinal,
            digest({"mandate": mandate.fingerprint,
                    "snapshot": actual["snapshot_digest"], "url": step.url}),
            step.host, step.action, step.projected_ready_at,
            step.conservative_reserve_bytes,
            step.requires_live_robots_authority,
        ))
    if not proposed:
        holds.add("no_executable_candidate_issued")
    expires = min(mandate.scope.expires_at, now + 30)
    payload = {
        "mandate": mandate.fingerprint,
        "snapshot": actual["snapshot_digest"],
        "sequence": actual["sequence"],
        "routes": routes.route_digest,
        "governor": governor.governor_digest,
        "recovery": recovery.handshake_digest,
        "capacity": capacity.envelope_digest,
        "simulation": simulation.simulation_digest,
        "steps": [asdict(x) for x in proposed],
        "holds": sorted(holds),
        "at": now, "expires": expires,
    }
    return DispatchEnvelope(
        mandate.fingerprint, actual["snapshot_digest"], actual["sequence"],
        routes.route_digest, governor.governor_digest,
        recovery.handshake_digest, capacity.envelope_digest,
        simulation.simulation_digest, now, expires, tuple(proposed),
        len(proposed), charged, tuple(sorted(holds)),
        len(simulation.steps) - len(proposed), digest(payload),
    ), simulation
