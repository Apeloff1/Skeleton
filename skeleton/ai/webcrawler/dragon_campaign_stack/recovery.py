"""Conservative recovery assessment over the canonical Dragon crawler snapshot.

A physical worker join, a Mongo checkpoint confirmation, and valid consent
are separate conditions. No reservation is returned or retry automatically run.
"""
from __future__ import annotations

from dataclasses import dataclass
import json

from ..operations import CrawlRun
from .budget import project_budget
from .contracts import CampaignMandate, digest, ensure_snapshot_scope


@dataclass(frozen=True)
class RecoveryAssessment:
    run_id: str
    sequence: int
    state: str
    pending_dispatch: bool
    reserved_uncertain_bytes: int
    worker_join_observed: bool
    checkpoint_authority_confirmed: bool
    may_reopen: bool
    may_dispatch: bool
    necessary_actions: tuple[str, ...]
    recovery_digest: str
    external_effects_replayed: bool = False


def assess_campaign_recovery(
    snapshot: dict[str, object],
    mandate: CampaignMandate, *,
    now: float,
    authorized: bool,
    worker_join_observed: bool,
    checkpoint_authority_confirmed: bool,
) -> RecoveryAssessment:
    mandate.admit(now=now, authorized=authorized)
    ensure_snapshot_scope(snapshot, mandate)
    if type(worker_join_observed) is not bool or type(checkpoint_authority_confirmed) is not bool:
        raise ValueError("recovery authority predicates must be exact booleans")
    run = CrawlRun.from_snapshot(snapshot)
    canonical = run.snapshot()
    snapshot_size = len(json.dumps(
        canonical, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False,
    ).encode("utf-8"))
    budget = project_budget(canonical, mandate, snapshot_bytes=snapshot_size)
    actions = []
    if not worker_join_observed:
        actions.append("join_or_fence_previous_physical_worker")
    if not checkpoint_authority_confirmed:
        actions.append("reconcile_authoritative_mongo_commit")
    if budget.pending_dispatch:
        actions.append("retain_uncertain_request_and_max_byte_reserve")
        actions.append("canonical_interrupted_dispatch_recovery_required")
    if budget.state in ("cancelled", "failed", "budget_exhausted", "completed"):
        actions.append("terminal_or_failed_run_must_not_be_resumed_implicitly")
    if budget.state == "paused":
        actions.append("explicit_versioned_resume_required")
    if budget.requests_remaining == 0 or budget.bytes_remaining < 1024:
        actions.append("remaining_grant_insufficient")
    reopened = (
        worker_join_observed and checkpoint_authority_confirmed
        and budget.state in ("ready", "running", "paused")
    )
    dispatchable = (
        reopened and not budget.pending_dispatch
        and budget.state in ("ready", "running")
        and budget.requests_remaining > 0
        and budget.documents_remaining > 0
        and budget.bytes_remaining >= 1024
    )
    payload = {
        "run": canonical["run_id"],
        "snapshot": canonical["snapshot_digest"],
        "sequence": canonical["sequence"],
        "worker_join": worker_join_observed,
        "checkpoint_confirmed": checkpoint_authority_confirmed,
        "reopened": reopened,
        "dispatchable": dispatchable,
        "actions": actions,
    }
    return RecoveryAssessment(
        run_id=canonical["run_id"], sequence=canonical["sequence"],
        state=budget.state, pending_dispatch=budget.pending_dispatch,
        reserved_uncertain_bytes=budget.bytes_uncertain,
        worker_join_observed=worker_join_observed,
        checkpoint_authority_confirmed=checkpoint_authority_confirmed,
        may_reopen=reopened, may_dispatch=dispatchable,
        necessary_actions=tuple(actions),
        recovery_digest=digest(payload),
    )
