"""Revision-fenced campaign control proposals, never authority side effects.

A proposal binds the observed exact snapshot and operator intent. Backend
separately enforces Mongo CAS, account rights, consent, leases and pre-I/O
checkpointing. An advisory decision cannot authorize any network request.
"""
from __future__ import annotations

from dataclasses import dataclass

from .contracts import CampaignMandate, digest, integer
from .integration import CampaignInspection
from .journal import CampaignJournal


_ALLOWED = {
    "ready": frozenset({"plan", "pause", "cancel"}),
    "running": frozenset({"plan", "pause", "cancel"}),
    "paused": frozenset({"resume", "cancel"}),
    "failed": frozenset({"cancel"}),
    "budget_exhausted": frozenset({"cancel"}),
    "completed": frozenset(),
    "cancelled": frozenset(),
}


@dataclass(frozen=True)
class CampaignControlProposal:
    action: str
    run_id: str
    observed_snapshot_digest: str
    observed_sequence: int
    expected_journal_revision: int
    reason: str
    admitted: bool
    holds: tuple[str, ...]
    proposal_digest: str
    authority: str = "advisory_only_requires_backend_cas"


def propose_campaign_control(
    report: CampaignInspection,
    mandate: CampaignMandate,
    journal: CampaignJournal, *,
    action: str, reason: str,
    expected_snapshot_digest: str,
    expected_sequence: int,
    expected_journal_revision: int,
    now: float, authorized: bool,
) -> CampaignControlProposal:
    mandate.admit(now=now, authorized=authorized)
    if not isinstance(report, CampaignInspection):
        raise ValueError("invalid campaign inspection")
    journal.verify(mandate)
    integer(expected_sequence, "observed run sequence", 0, 10000)
    integer(expected_journal_revision, "journal revision", 0, 1024)
    if not isinstance(reason, str) or not reason.strip() or len(reason) > 1024:
        raise ValueError("control requires an operator rationale")
    if report.mandate_digest != mandate.fingerprint:
        raise PermissionError("cross-mandate campaign control")
    if (expected_snapshot_digest != report.snapshot_digest
            or expected_sequence != report.run_sequence):
        raise RuntimeError("stale crawl snapshot lease")
    if expected_journal_revision != journal.revision:
        raise RuntimeError("stale campaign journal revision")
    if action not in ("plan", "pause", "resume", "cancel"):
        raise ValueError("unknown control action")
    if action not in _ALLOWED.get(report.budget.state, frozenset()):
        raise PermissionError("invalid canonical run control transition")
    holds = []
    if action == "plan":
        if report.budget.pending_dispatch:
            holds.append("in_flight_outcome_not_reconciled")
        if report.budget.exhausted:
            holds.extend(report.budget.blockers)
        if not report.plan.dispatches:
            holds.append("no_admitted_campaign_dispatches")
    if action == "resume" and report.budget.pending_dispatch:
        holds.append("recovery_of_unknown_remote_outcome_required")
    permitted = not holds
    payload = {
        "mandate": mandate.fingerprint, "action": action,
        "run": report.run_id, "snapshot": report.snapshot_digest,
        "sequence": report.run_sequence,
        "journal_head": journal.head, "expected_revision": journal.revision,
        "reason": reason, "admitted": permitted, "holds": sorted(set(holds)),
    }
    return CampaignControlProposal(
        action=action, run_id=report.run_id,
        observed_snapshot_digest=report.snapshot_digest,
        observed_sequence=report.run_sequence,
        expected_journal_revision=journal.revision,
        reason=reason, admitted=permitted,
        holds=tuple(sorted(set(holds))),
        proposal_digest=digest(payload),
    )
