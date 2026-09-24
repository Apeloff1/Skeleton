from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from skeleton.contracts.memory_record import MemoryKind, MemoryWriteProposal
from skeleton.memory.policy import (
    MemoryPolicyEngine,
    MemoryWriteDecision,
    MemoryWritePolicy,
)
from skeleton.memory.writeback import (
    GovernedMemoryWriter,
    MemoryStageConflict,
    MemoryWriteDenied,
)
from skeleton.persistence.memory_repository import SQLiteMemoryRepository


def _now():
    return datetime(2026, 9, 23, 17, 0, tzinfo=timezone.utc)


def _proposal(
    *,
    proposal_id: str | None = None,
    key: str = "write-1",
    content: str = "remember",
    provenance=("conversation:1",),
    source_operation_id: str | None = None,
    data_class: str = "confidential",
):
    return MemoryWriteProposal(
        proposal_id=proposal_id or str(uuid4()),
        tenant_id="tenant-a",
        namespace="assistant",
        subject_id="user-a",
        kind=MemoryKind.SEMANTIC,
        idempotency_key=key,
        proposed_at=_now(),
        content=content,
        provenance_refs=tuple(provenance),
        source_operation_id=source_operation_id or str(uuid4()),
        data_class=data_class,
    )


def test_policy_denies_missing_provenance() -> None:
    policy = MemoryPolicyEngine()

    result = policy.evaluate(_proposal(provenance=()))

    assert result.decision is MemoryWriteDecision.DENY
    assert result.reason == "provenance_required"


def test_policy_can_require_review_for_restricted_data() -> None:
    result = MemoryPolicyEngine().evaluate(_proposal(data_class="restricted"))

    assert result.decision is MemoryWriteDecision.REVIEW
    assert result.reason == "restricted_data_requires_review"


def test_stage_is_side_effect_free_until_commit() -> None:
    repo = SQLiteMemoryRepository()
    writer = GovernedMemoryWriter(repo)
    proposal = _proposal()

    staged = writer.stage(proposal)

    assert staged.proposal_id == proposal.proposal_id
    assert writer.staged_ids() == (proposal.proposal_id,)
    assert repo.list_subject(
        tenant_id="tenant-a",
        namespace="assistant",
        subject_id="user-a",
    ) == ()

    committed = writer.commit(proposal.proposal_id, now=_now())

    assert committed.content == "remember"
    assert writer.staged_ids() == ()


def test_denied_proposal_never_mutates_repository() -> None:
    repo = SQLiteMemoryRepository()
    writer = GovernedMemoryWriter(repo)
    proposal = _proposal(provenance=())
    writer.stage(proposal)

    with pytest.raises(MemoryWriteDenied, match="provenance_required"):
        writer.commit(proposal.proposal_id, now=_now())

    assert repo.list_subject(
        tenant_id="tenant-a",
        namespace="assistant",
        subject_id="user-a",
    ) == ()


def test_review_hold_requires_explicit_approval() -> None:
    repo = SQLiteMemoryRepository()
    writer = GovernedMemoryWriter(repo)
    proposal = _proposal(data_class="restricted")
    writer.stage(proposal)

    with pytest.raises(MemoryWriteDenied, match="restricted_data_requires_review"):
        writer.commit(proposal.proposal_id, now=_now())

    committed = writer.commit(
        proposal.proposal_id,
        review_approved=True,
        now=_now(),
    )
    assert committed.data_class == "restricted"


def test_proposal_identity_replay_is_exact_or_conflict() -> None:
    repo = SQLiteMemoryRepository()
    writer = GovernedMemoryWriter(repo)
    proposal_id = str(uuid4())
    first = _proposal(proposal_id=proposal_id, content="one")
    writer.stage(first)

    replay = writer.stage(first)
    assert replay.proposal.payload_digest == first.payload_digest

    with pytest.raises(MemoryStageConflict, match="different write intent"):
        writer.stage(
            _proposal(
                proposal_id=proposal_id,
                content="two",
                key=first.idempotency_key,
                source_operation_id=first.source_operation_id,
            )
        )


def test_policy_can_disable_source_operation_requirement() -> None:
    engine = MemoryPolicyEngine(
        MemoryWritePolicy(require_source_operation=False)
    )
    proposal = MemoryWriteProposal(
        proposal_id=str(uuid4()),
        tenant_id="tenant-a",
        namespace="assistant",
        subject_id="user-a",
        kind=MemoryKind.SEMANTIC,
        idempotency_key="write-1",
        proposed_at=_now(),
        content="remember",
        provenance_refs=("source:1",),
        source_operation_id=None,
    )

    assert engine.evaluate(proposal).allowed
