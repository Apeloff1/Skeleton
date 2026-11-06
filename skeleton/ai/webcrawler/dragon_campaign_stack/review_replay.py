"""Pure append-only human-review simulation with deterministic replay custody.

The existing reviewed-knowledge owner, not this module, owns durable human
decisions. This module verifies a caller-supplied ordered sequence against
an exact review agenda and current policy, and produces a revision/CAS-aware
preview. It cannot authenticate an operator, sign a legal decision, perform
the associated Mongo write, or turn reviewed text into verified knowledge.

A completed review task means only that an authenticated person examined the
task. Publication and training remain separate, permanently disabled here.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable

from .contracts import CampaignMandate, bounded_text, digest, finite, integer
from .policy_matrix import SourcePolicyProjection
from .review_agenda import ReviewAgenda, ReviewTask

_ACTIONS = frozenset(("reviewed", "rejected", "needs_evidence", "deferred"))
_TERMINAL = frozenset(("reviewed", "rejected"))
_PREVIOUS_ROOT = "0" * 64


@dataclass(frozen=True)
class HumanReviewAction:
    task_id: str
    action: str
    reviewer_id: str
    external_receipt: str
    reviewed_at: float
    sequence: int
    expected_task_revision: int
    prior_chain_digest: str
    agenda_digest: str
    policy_digest: str
    remarks_digest: str | None = None
    signature_verified_by_authority: bool = False

    def __post_init__(self) -> None:
        bounded_text(self.task_id, "review task", 64)
        if self.action not in _ACTIONS:
            raise ValueError("invalid human review transition")
        bounded_text(self.reviewer_id, "reviewer identity", 256)
        bounded_text(self.external_receipt, "review owner reference", 512)
        finite(self.reviewed_at, "review clock")
        integer(self.sequence, "review log sequence", 1, 2048)
        integer(self.expected_task_revision, "expected task revision", 0, 2048)
        for value in (self.prior_chain_digest, self.agenda_digest, self.policy_digest):
            if not isinstance(value, str) or len(value) != 64 or any(
                c not in "0123456789abcdef" for c in value
            ):
                raise ValueError("malformed review digest")
        if self.remarks_digest is not None and (
            not isinstance(self.remarks_digest, str)
            or len(self.remarks_digest) != 64
            or any(c not in "0123456789abcdef" for c in self.remarks_digest)
        ):
            raise ValueError("malformed remarks hash")
        if self.signature_verified_by_authority is not True:
            raise PermissionError("current external reviewer authentication required")


@dataclass(frozen=True)
class ReviewTaskState:
    task_id: str
    task_type: str
    state: str
    revision: int
    last_sequence: int
    actionable: bool
    predecessors_satisfied: bool
    source_policy_current: bool
    operator_reviewed: bool
    knowledge_verified: bool = False
    publication_authorized: bool = False


@dataclass(frozen=True)
class ReviewReplay:
    mandate_digest: str
    source_snapshot_digest: str
    agenda_digest: str
    policy_digest: str
    event_count: int
    chain_head: str
    task_states: tuple[ReviewTaskState, ...]
    complete_task_ids: tuple[str, ...]
    pending_task_ids: tuple[str, ...]
    blocked_task_ids: tuple[str, ...]
    needs_evidence_task_ids: tuple[str, ...]
    replay_digest: str
    persistent_write_performed: bool = False
    review_signature_authentication_proven_by_receipt: bool = False
    facts_verified: bool = False


def _receipt_hash(event: HumanReviewAction) -> str:
    return digest({"schema": "dragon.human_review_action.v1", "event": asdict(event)})


def replay_human_reviews(
    mandate: CampaignMandate,
    agenda: ReviewAgenda,
    policy: SourcePolicyProjection,
    actions: Iterable[HumanReviewAction],
    *,
    now: float,
    authorized: bool,
    max_events: int = 512,
) -> ReviewReplay:
    mandate.admit(now=now, authorized=authorized)
    integer(max_events, "review event bound", 1, 2048)
    if agenda.mandate_digest != mandate.fingerprint or (
        policy.mandate_digest != mandate.fingerprint
    ):
        raise PermissionError("cross-mandate human review")
    if agenda.source_snapshot_digest != policy.source_snapshot_digest or (
        agenda.policy_digest != policy.policy_digest
    ):
        raise PermissionError("review policy changed since agenda")
    by_id = {task.task_id: task for task in agenda.tasks}
    if len(by_id) != len(agenda.tasks) or len(by_id) > 512:
        raise ValueError("review agenda identity ambiguity")
    if any(not isinstance(x, ReviewTask) for x in agenda.tasks):
        raise TypeError("typed review task required")
    rows = tuple(actions)
    if len(rows) > max_events:
        raise ValueError("review event log capacity exceeded")
    excluded = set(policy.excluded_source_ids)
    states: dict[str, tuple[str, int, int]] = {
        task_id: ("pending_human_review", 0, 0)
        for task_id in by_id
    }
    chain = _PREVIOUS_ROOT
    last_clock = mandate.created_at
    for sequence, action in enumerate(rows, start=1):
        if not isinstance(action, HumanReviewAction):
            raise TypeError("typed human decision receipt required")
        if action.sequence != sequence:
            raise ValueError("review log sequence is not contiguous")
        if action.prior_chain_digest != chain:
            raise PermissionError("human review append-only chain broken")
        if action.agenda_digest != agenda.agenda_digest or (
            action.policy_digest != policy.policy_digest
        ):
            raise PermissionError("review event references stale policy or agenda")
        task = by_id.get(action.task_id)
        if task is None:
            raise ValueError("review task never existed in this agenda")
        if not last_clock <= action.reviewed_at <= now:
            raise ValueError("nonmonotonic or future operator review")
        last_clock = action.reviewed_at
        state, revision, _ = states[action.task_id]
        if action.expected_task_revision != revision:
            raise PermissionError("review task revision compare-and-swap failure")
        if state in _TERMINAL:
            raise PermissionError("terminal human review task cannot be replayed")
        if task.source_id in excluded and action.action == "reviewed":
            raise PermissionError("withdrawn source task cannot be accepted")
        # Prerequisites must themselves be human-reviewed, not merely
        # postponed or rejected. No implicit aggregate completion.
        if action.action == "reviewed" and any(
            states[parent][0] != "reviewed" for parent in task.predecessors
        ):
            raise PermissionError("human review prerequisites unresolved")
        states[action.task_id] = (action.action, revision + 1, sequence)
        chain = digest({
            "previous": chain, "sequence": sequence,
            "receipt": _receipt_hash(action),
        })
    projected = []
    for task in agenda.tasks:
        state, revision, last_seq = states[task.task_id]
        dependencies_met = all(states[x][0] == "reviewed" for x in task.predecessors)
        policy_current = task.source_id not in excluded
        terminal = state in _TERMINAL
        projected.append(ReviewTaskState(
            task_id=task.task_id, task_type=task.task_type,
            state=state, revision=revision, last_sequence=last_seq,
            actionable=not terminal and policy_current and dependencies_met,
            predecessors_satisfied=dependencies_met,
            source_policy_current=policy_current,
            operator_reviewed=state == "reviewed",
        ))
    projected.sort(key=lambda x: x.task_id)
    output = {
        "mandate": mandate.fingerprint, "snapshot": agenda.source_snapshot_digest,
        "agenda": agenda.agenda_digest, "policy": policy.policy_digest,
        "head": chain, "count": len(rows),
        "states": [asdict(x) for x in projected],
    }
    return ReviewReplay(
        mandate_digest=mandate.fingerprint,
        source_snapshot_digest=agenda.source_snapshot_digest,
        agenda_digest=agenda.agenda_digest, policy_digest=policy.policy_digest,
        event_count=len(rows), chain_head=chain,
        task_states=tuple(projected),
        complete_task_ids=tuple(x.task_id for x in projected if x.state == "reviewed"),
        pending_task_ids=tuple(x.task_id for x in projected
                               if x.actionable and not x.operator_reviewed),
        blocked_task_ids=tuple(x.task_id for x in projected if not x.actionable),
        needs_evidence_task_ids=tuple(x.task_id for x in projected
                                      if x.state == "needs_evidence"),
        replay_digest=digest(output),
    )


@dataclass(frozen=True)
class HumanReviewProposal:
    """Untrusted operator-action request for the canonical reviewed-knowledge owner."""

    task_id: str
    action: str
    agenda_digest: str
    policy_digest: str
    expected_task_revision: int
    requested_at: float
    persistence_performed: bool = False
    authenticated: bool = False


def next_review_action(
    agenda: ReviewAgenda,
    policy: SourcePolicyProjection,
    replay: ReviewReplay,
    *,
    task_id: str,
    action: str,
    now: float,
) -> HumanReviewProposal:
    if agenda.agenda_digest != replay.agenda_digest or (
        policy.policy_digest != replay.policy_digest
    ):
        raise PermissionError("stale review proposal")
    if action not in _ACTIONS:
        raise ValueError("unsupported review proposal action")
    task = next((x for x in replay.task_states if x.task_id == task_id), None)
    if task is None:
        raise ValueError("unknown review task")
    if action == "reviewed" and not task.actionable:
        raise PermissionError("review prerequisites or policy not satisfied")
    if task.state in _TERMINAL:
        raise PermissionError("review task already terminal")
    finite(now, "review proposal clock")
    return HumanReviewProposal(
        task_id=task_id, action=action,
        agenda_digest=agenda.agenda_digest,
        policy_digest=policy.policy_digest,
        expected_task_revision=task.revision,
        requested_at=now,
    )
