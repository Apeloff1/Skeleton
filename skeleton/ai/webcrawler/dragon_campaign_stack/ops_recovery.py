"""Restart-safe forensic handshake: typed source evidence, never a lease grant.

A client claim that a worker stopped is not proof it stopped. This offline
artifact exposes the exact missing authoritative acknowledgements, preserves
unknown remote outcomes and binds each operator claim to the current snapshot.
The actual backend must independently join the physical worker, revoke old
leases and confirm durable Mongo CAS before any new fetch is admitted.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

from ..operations import CrawlRun
from .contracts import CampaignMandate, digest, ensure_snapshot_scope, exact_digest, integer
from .budget import BudgetProjection, verify_projected_budget
from .ops_timeline import OperationalTimeline


@dataclass(frozen=True)
class RecoveryWitness:
    source_snapshot_digest: str
    expected_run_sequence: int
    expected_worker_epoch: int
    physical_worker_join_observed: bool
    old_lease_revoked: bool
    durable_mongo_checkpoint_confirmed: bool
    owner_scope_reauthenticated: bool
    live_consent_reauthenticated: bool
    source_authority: str = "caller_supplied_not_backend_verified"

    def __post_init__(self) -> None:
        exact_digest(self.source_snapshot_digest, "recovery snapshot")
        integer(self.expected_run_sequence, "recovery sequence", 0, 2**63-1)
        integer(self.expected_worker_epoch, "fencing epoch", 0, 2**63-1)
        for name in (
            "physical_worker_join_observed", "old_lease_revoked",
            "durable_mongo_checkpoint_confirmed", "owner_scope_reauthenticated",
            "live_consent_reauthenticated",
        ):
            if type(getattr(self, name)) is not bool:
                raise TypeError("recovery witness requires exact booleans")
        if self.source_authority != "caller_supplied_not_backend_verified":
            raise ValueError("untrusted recovery witness cannot assert authority")


@dataclass(frozen=True)
class RecoveryHandshake:
    mandate_digest: str
    source_snapshot_digest: str
    timeline_digest: str
    run_id: str
    run_sequence: int
    canonical_state: str
    expected_worker_epoch: int | None
    witness_present: bool
    pending_remote_outcome: bool
    unrefunded_uncertain_bytes: int
    operator_asserted_ready: bool
    held_reasons: tuple[str, ...]
    necessary_backend_steps: tuple[str, ...]
    handshake_digest: str
    real_worker_fenced: bool = False
    authoritative_checkpoint_committed: bool = False
    source_policy_revalidated: bool = False
    runtime_dispatch_authorized: bool = False


def assess_restart_handshake(
    mandate: CampaignMandate, snapshot: dict[str, object],
    budget: BudgetProjection, timeline: OperationalTimeline,
    *, now: float, authorized: bool,
    witness: RecoveryWitness | None = None,
) -> RecoveryHandshake:
    mandate.admit(now=now, authorized=authorized)
    ensure_snapshot_scope(snapshot, mandate)
    canonical = CrawlRun.from_snapshot(snapshot).snapshot()
    verify_projected_budget(canonical, mandate, budget)
    if not isinstance(timeline, OperationalTimeline) or (
        timeline.mandate_digest != mandate.fingerprint
        or timeline.source_snapshot_digest != canonical["snapshot_digest"]
        or timeline.run_sequence != canonical["sequence"]
    ):
        raise PermissionError("recovery timeline detached from live snapshot")
    if witness is not None and not isinstance(witness, RecoveryWitness):
        raise TypeError("typed non-authoritative witness required")
    if witness is not None and (
        witness.source_snapshot_digest != canonical["snapshot_digest"]
        or witness.expected_run_sequence != canonical["sequence"]
    ):
        raise RuntimeError("stale or cross-run recovery witness")
    holds = []
    steps = [
        "authenticate_current_account_source_and_consent_policy",
        "join_or_fence_previous_physical_worker_in_backend",
        "revoke_previous_worker_epoch_under_durable_cas",
        "confirm_authoritative_mongo_checkpoint_and_reserved_bytes",
        "recheck_dns_robots_and_budget_immediately_before_network",
    ]
    if witness is None:
        holds.append("no_canonical_worker_and_mongo_witness")
    elif not all((
        witness.physical_worker_join_observed, witness.old_lease_revoked,
        witness.durable_mongo_checkpoint_confirmed,
        witness.owner_scope_reauthenticated, witness.live_consent_reauthenticated,
    )):
        holds.append("operator_recovery_witness_incomplete")
    if budget.pending_dispatch or timeline.pending_dispatch_unresolved:
        holds.append("unreconciled_remote_dispatch_outcome")
        steps.append("resolve_or_quarantine_uncertain_remote_effect_without_refund")
    if budget.bytes_uncertain:
        holds.append("uncertain_byte_reservation_must_not_be_refunded")
    if timeline.interior_sequence_gap or timeline.clock_regression_detected:
        holds.append("event_history_integrity_requires_review")
    if budget.state not in ("ready", "running"):
        holds.append("explicit_canonical_state_transition_required")
    if budget.exhausted:
        holds.extend(budget.blockers)
    operator_ready = bool(witness is not None and all((
        witness.physical_worker_join_observed, witness.old_lease_revoked,
        witness.durable_mongo_checkpoint_confirmed,
        witness.owner_scope_reauthenticated, witness.live_consent_reauthenticated,
    )))
    payload = {
        "mandate": mandate.fingerprint,
        "snapshot": canonical["snapshot_digest"],
        "timeline": timeline.timeline_digest,
        "budget": asdict(budget),
        "epoch": witness.expected_worker_epoch if witness else None,
        "witness": asdict(witness) if witness else None,
        "holds": sorted(set(holds)),
        "steps": steps,
    }
    return RecoveryHandshake(
        mandate.fingerprint, canonical["snapshot_digest"],
        timeline.timeline_digest, canonical["run_id"], canonical["sequence"],
        budget.state, witness.expected_worker_epoch if witness else None,
        witness is not None, budget.pending_dispatch, budget.bytes_uncertain,
        operator_ready, tuple(sorted(set(holds))),
        tuple(dict.fromkeys(steps)), digest(payload),
    )
