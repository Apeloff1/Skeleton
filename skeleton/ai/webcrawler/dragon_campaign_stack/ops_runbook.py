"""Finite ordered operator recovery and admission playbook.

All actions are human-readable metadata duties tied to an immutable snapshot;
the playbook never performs a worker join, lease CAS, source permission change,
network request, consent renewal, model call or autonomous publication.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

from .contracts import CampaignMandate, digest, integer
from .ops_timeline import OperationalTimeline
from .ops_host_governor import HostGovernor
from .ops_recovery import RecoveryHandshake
from .ops_capacity import CapacityEnvelope
from .ops_dispatch_envelope import DispatchEnvelope


@dataclass(frozen=True)
class OperatorRunbookStep:
    ordinal: int
    priority: str
    code: str
    rationale: str
    supporting_digest: str
    requires_backend_authority: bool = True
    automatically_executed: bool = False
    completed_or_approved: bool = False


@dataclass(frozen=True)
class OperatorRunbook:
    mandate_digest: str
    source_snapshot_digest: str
    steps: tuple[OperatorRunbookStep, ...]
    critical_step_count: int
    recovery_step_count: int
    advisory_step_count: int
    requires_human_review: bool
    runbook_digest: str
    actual_worker_intervention_performed: bool = False
    merge_or_release_approved: bool = False


def compile_operator_runbook(
    mandate: CampaignMandate, timeline: OperationalTimeline,
    hosts: HostGovernor, recovery: RecoveryHandshake,
    capacity: CapacityEnvelope, dispatch: DispatchEnvelope,
    *, max_steps: int = 48,
) -> OperatorRunbook:
    integer(max_steps, "operational runbook ceiling", 1, 128)
    if (any(x.mandate_digest != mandate.fingerprint
             for x in (timeline, hosts, recovery, capacity, dispatch))
        or len({
            timeline.source_snapshot_digest,
            hosts.source_snapshot_digest,
            recovery.source_snapshot_digest,
            dispatch.source_snapshot_digest,
        }) != 1
        or hosts.timeline_digest != timeline.timeline_digest
        or recovery.timeline_digest != timeline.timeline_digest
        or capacity.governor_digest != hosts.governor_digest
        or capacity.recovery_digest != recovery.handshake_digest
        or dispatch.capacity_digest != capacity.envelope_digest):
        raise PermissionError("operational runbook reads different frozen snapshots")
    staged = {}
    def add(priority: str, code: str, rationale: str, evidence: str) -> None:
        rank = {"critical": 0, "high": 1, "medium": 2, "advisory": 3}
        if priority not in rank:
            raise ValueError("invalid recovery priority")
        key = (priority, code)
        staged[key] = (priority, code, rationale, evidence)
    if timeline.pending_dispatch_unresolved or timeline.uncertain_bytes:
        add("critical", "reconcile_unsettled_dispatch",
            "Join previous worker and retain uncertain request/byte reserve until canonical reconciliation",
            timeline.timeline_digest)
    if timeline.interior_sequence_gap or timeline.clock_regression_detected:
        add("high", "inspect_canonical_event_custody",
            "Reject a missing or time-regressing event record before relying on historical replay",
            timeline.timeline_digest)
    if timeline.retained_history_incomplete:
        add("medium", "preserve_retained_history_limit",
            "An event ring is not proof of complete prior network effects",
            timeline.timeline_digest)
    if timeline.future_clock_receipts:
        add("high", "verify_time_base",
            "Check monotonic wall clock before evaluating due times and consent expiry",
            timeline.timeline_digest)
    if not recovery.witness_present or recovery.held_reasons:
        add("critical", "complete_durable_restart_fence",
            "Physically join/fence worker, revoke old epoch and inspect authenticated Mongo CAS",
            recovery.handshake_digest)
    if hosts.cold_robots_origins or hosts.stale_robots_origins:
        add("high", "refresh_robots_inside_canonical_runner",
            "Unobserved, unresolved or stale robots policy requires live origin validation",
            hosts.governor_digest)
    if not hosts.origins:
        add("medium", "examine_empty_frontier",
            "Check terminal state, exhausted budget and retained seed graph",
            hosts.governor_digest)
    if capacity.samples_observed == 0:
        add("high", "collect_authenticated_live_resource_samples",
            "Sample CPU, available RAM, disk and worker concurrency in the executing host",
            capacity.envelope_digest)
    if capacity.samples_observed and capacity.holds:
        add("medium", "recheck_resource_pressure_and_budget",
            "Narrow concurrency and retain byte reservations under measured headroom",
            capacity.envelope_digest)
    if dispatch.feasible_hypothetical_requests:
        add("advisory", "recheck_preflight_at_dispatch_boundary",
            "Proposals are opaque hints only; rerun DNS, robots, permission, epoch and pre-I/O CAS",
            dispatch.envelope_digest)
    if not dispatch.feasible_hypothetical_requests:
        add("medium", "resolve_holds_before_request_proposal",
            "No network work-order was issued by this read-only operational assessment",
            dispatch.envelope_digest)
    add("advisory", "human_assurance_signoff_required",
        "Review provenance, source rights, untrusted instructions and citation validity before knowledge use",
        dispatch.envelope_digest)
    if len(staged) > max_steps:
        raise ValueError("operator runbook overflow cannot silently discard remediation")
    rank = {"critical": 0, "high": 1, "medium": 2, "advisory": 3}
    entries = [
        OperatorRunbookStep(index, item[0], item[1], item[2], item[3])
        for index, item in enumerate(sorted(staged.values(), key=lambda x: (
            rank[x[0]], x[1],
        )))
    ]
    payload = {
        "mandate": mandate.fingerprint,
        "snapshot": timeline.source_snapshot_digest,
        "timeline": timeline.timeline_digest,
        "governor": hosts.governor_digest,
        "recovery": recovery.handshake_digest,
        "capacity": capacity.envelope_digest,
        "dispatch": dispatch.envelope_digest,
        "steps": [asdict(x) for x in entries],
    }
    return OperatorRunbook(
        mandate.fingerprint, timeline.source_snapshot_digest,
        tuple(entries), sum(x.priority == "critical" for x in entries),
        sum(x.code in ("reconcile_unsettled_dispatch",
                        "complete_durable_restart_fence") for x in entries),
        sum(x.priority == "advisory" for x in entries),
        True, digest(payload),
    )
