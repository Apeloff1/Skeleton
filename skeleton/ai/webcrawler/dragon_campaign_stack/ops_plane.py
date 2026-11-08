"""Six-gate replay-verified operational assurance over an owned CrawlRun.

Nothing in this projection performs network I/O, physical worker operations,
Mongo writes, model execution or external source publication. An operator
witness and resource sample are source inputs, not authenticated authority.
Each stage has a digest chained to the previous source-bound receipt.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable
import json

from ..operations import CrawlRun
from .budget import BudgetProjection, project_budget, verify_projected_budget
from .contracts import CampaignMandate, digest, ensure_snapshot_scope
from .frontier_route_map import project_canonical_routes
from .pressure import ResourceObservation
from .ops_timeline import OperationalTimeline, inspect_operational_timeline
from .ops_host_governor import HostGovernor, govern_canonical_origins
from .ops_recovery import RecoveryHandshake, RecoveryWitness, assess_restart_handshake
from .ops_capacity import CapacityEnvelope, recommend_ops_capacity
from .ops_dispatch_envelope import DispatchEnvelope, prepare_dispatch_envelope
from .ops_runbook import OperatorRunbook, compile_operator_runbook


STAGES = (
    "exact_canonical_event_timeline",
    "per_origin_robots_and_cooldown_safety",
    "physical_worker_restart_and_cas_witness",
    "measured_resource_capacity_envelope",
    "opaque_bounded_dispatch_preflight",
    "review_only_operator_recovery_runbook",
)


@dataclass(frozen=True)
class OperationalStage:
    ordinal: int
    name: str
    source_receipt_digest: str
    previous_chain_digest: str
    chain_digest: str
    network_or_mutation_executed: bool = False


@dataclass(frozen=True)
class OperationalAssurance:
    mandate_digest: str
    source_snapshot_digest: str
    run_id: str
    run_sequence: int
    issued_at: float
    timeline: OperationalTimeline
    hosts: HostGovernor
    recovery: RecoveryHandshake
    capacity: CapacityEnvelope
    dispatch: DispatchEnvelope
    runbook: OperatorRunbook
    stages: tuple[OperationalStage, ...]
    report_digest: str
    read_only: bool = True
    source_text_exported: bool = False
    credential_exported: bool = False
    physical_worker_started: bool = False
    worker_lease_authenticated: bool = False
    mongo_state_mutated: bool = False
    network_request_performed: bool = False
    publication_or_training_granted: bool = False


def _chain(mandate: CampaignMandate, snapshot_digest: str,
           receipts: tuple[str, ...]) -> tuple[OperationalStage, ...]:
    if len(receipts) != len(STAGES):
        raise ValueError("operational receipt count changed")
    previous = "0" * 64
    stages = []
    for ordinal, (name, receipt) in enumerate(zip(STAGES, receipts)):
        envelope = {
            "mandate": mandate.fingerprint, "snapshot": snapshot_digest,
            "ordinal": ordinal, "name": name,
            "receipt": receipt, "previous": previous,
        }
        chain = digest(envelope)
        stages.append(OperationalStage(
            ordinal, name, receipt, previous, chain,
        ))
        previous = chain
    return tuple(stages)


def compose_operational_assurance(
    mandate: CampaignMandate, snapshot: dict[str, object],
    *, now: float, authorized: bool,
    resource_observations: Iterable[ResourceObservation] = (),
    recovery_witness: RecoveryWitness | None = None,
    budget: BudgetProjection | None = None,
) -> OperationalAssurance:
    mandate.admit(now=now, authorized=authorized)
    ensure_snapshot_scope(snapshot, mandate)
    canonical = CrawlRun.from_snapshot(snapshot).snapshot()
    packed_size = len(json.dumps(
        canonical, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False,
    ).encode("utf-8"))
    projected = project_budget(canonical, mandate, snapshot_bytes=packed_size)
    if budget is not None:
        if not isinstance(budget, BudgetProjection):
            raise TypeError("typed canonical budget required")
        verify_projected_budget(canonical, mandate, budget)
        if budget != projected:
            raise PermissionError("budget differs from exact snapshot usage")
    timeline = inspect_operational_timeline(
        mandate, canonical, now=now, authorized=authorized,
    )
    hosts = govern_canonical_origins(
        mandate, canonical, timeline, now=now, authorized=authorized,
    )
    recovery = assess_restart_handshake(
        mandate, canonical, projected, timeline,
        now=now, authorized=authorized, witness=recovery_witness,
    )
    observations = tuple(resource_observations)
    capacity, pressure = recommend_ops_capacity(
        mandate, projected, hosts, recovery, now=now, authorized=authorized,
        observations=observations,
    )
    routes = project_canonical_routes(
        mandate, canonical, now=now, authorized=authorized,
    )
    dispatch, _simulation = prepare_dispatch_envelope(
        mandate, canonical, projected, routes, hosts, recovery, capacity,
        now=now, authorized=authorized, pressure=pressure,
    )
    runbook = compile_operator_runbook(
        mandate, timeline, hosts, recovery, capacity, dispatch,
    )
    receipts = (
        timeline.timeline_digest, hosts.governor_digest,
        recovery.handshake_digest, capacity.envelope_digest,
        dispatch.envelope_digest, runbook.runbook_digest,
    )
    stages = _chain(mandate, canonical["snapshot_digest"], receipts)
    payload = {
        "mandate": mandate.fingerprint,
        "snapshot": canonical["snapshot_digest"],
        "run_id": canonical["run_id"],
        "run_sequence": canonical["sequence"],
        "issued_at": now,
        "stage_chain": [asdict(s) for s in stages],
        "receipts": receipts,
        "telemetry_count": len(observations),
        "source_policy": "external_authenticated_owner_required",
    }
    return OperationalAssurance(
        mandate.fingerprint, canonical["snapshot_digest"],
        canonical["run_id"], canonical["sequence"], now,
        timeline, hosts, recovery, capacity, dispatch, runbook,
        stages, digest(payload),
    )


def verify_operational_assurance(
    mandate: CampaignMandate, snapshot: dict[str, object],
    report: OperationalAssurance, *, now: float, authorized: bool,
    resource_observations: Iterable[ResourceObservation] = (),
    recovery_witness: RecoveryWitness | None = None,
    budget: BudgetProjection | None = None,
) -> None:
    if not isinstance(report, OperationalAssurance):
        raise TypeError("typed source-bound operational assurance required")
    expected = compose_operational_assurance(
        mandate, snapshot, now=now, authorized=authorized,
        resource_observations=resource_observations,
        recovery_witness=recovery_witness, budget=budget,
    )
    if expected != report:
        raise PermissionError("operational receipt, replay or authority drift")
