from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from skeleton.contracts.memory_record import MemoryKind, MemoryWriteProposal
from skeleton.intelligence.admission import (
    AdmissionRequest,
    ResourceBudget,
    UsageEstimate,
)
from skeleton.intelligence.admission_runtime import AdmissionRuntime
from skeleton.intelligence.quota import TenantQuota, TenantQuotaLedger
from skeleton.memory.policy import (
    MemoryPolicyEngine,
    MemoryWriteDecision,
    MemoryWritePolicy,
)
from skeleton.memory.writeback import (
    GovernedMemoryWriter,
    MemoryStageConflict,
    MemoryWriteDenied,
    MemoryWritebackError,
)
from skeleton.persistence.memory_repository import SQLiteMemoryRepository
from skeleton.vault.governance_registry import GovernanceRegistry


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
    writer = GovernedMemoryWriter(repo, governance=GovernanceRegistry())
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
    writer = GovernedMemoryWriter(repo, governance=GovernanceRegistry())
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
    writer = GovernedMemoryWriter(repo, governance=GovernanceRegistry())
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
    writer = GovernedMemoryWriter(repo, governance=GovernanceRegistry())
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



def test_commit_registers_memory_in_governance_registry() -> None:
    repo = SQLiteMemoryRepository()
    governance = GovernanceRegistry()
    writer = GovernedMemoryWriter(repo, governance=governance)
    proposal = _proposal()
    writer.stage(proposal)

    record = writer.commit(proposal.proposal_id, now=_now())
    governed = governance.lifecycle.get(record.memory_id)

    assert governed["tenant_id"] == record.tenant_id
    assert governed["owner_plane"] == "memory"
    assert governed["source_ref"] == (
        f"memory://{record.namespace}/{record.memory_id}"
    )
    assert governed["data_class"] == record.data_class
    assert governed["purposes"] == [
        "model-inference",
        "retrieval-synthesis",
    ]
    assert governed["deletion_targets"] == ["memory"]


def test_memory_update_reconciles_governance_classification_and_retention() -> None:
    repo = SQLiteMemoryRepository()
    governance = GovernanceRegistry()
    writer = GovernedMemoryWriter(repo, governance=governance)

    create = _proposal(content="one", data_class="internal")
    writer.stage(create)
    first = writer.commit(create.proposal_id, now=_now())

    expiry = datetime(2026, 10, 1, 20, 0, tzinfo=timezone.utc)
    update = MemoryWriteProposal(
        proposal_id=str(uuid4()),
        tenant_id=first.tenant_id,
        namespace=first.namespace,
        subject_id=first.subject_id,
        kind=first.kind,
        idempotency_key="write-update",
        proposed_at=_now(),
        content="two",
        provenance_refs=("conversation:2",),
        source_operation_id=str(uuid4()),
        target_memory_id=first.memory_id,
        expected_version=first.version,
        expires_at=expiry,
        data_class="confidential",
    )
    writer.stage(update)
    second = writer.commit(update.proposal_id, now=_now())

    governed = governance.lifecycle.get(second.memory_id)
    assert governed["data_class"] == "confidential"
    assert governed["retention_until"] == expiry.timestamp()
    assert governed["created_at"] == first.created_at.timestamp()


def test_governance_persistence_failure_tombstones_memory_fail_closed(
    monkeypatch,
) -> None:
    repo = SQLiteMemoryRepository()
    governance = GovernanceRegistry()
    writer = GovernedMemoryWriter(repo, governance=governance)
    proposal = _proposal()
    writer.stage(proposal)

    def fail(*args, **kwargs):
        raise RuntimeError("governance unavailable")

    monkeypatch.setattr(governance, "reconcile_canonical_write", fail)

    with pytest.raises(
        MemoryWritebackError,
        match="governance registration failed; memory was tombstoned",
    ):
        writer.commit(proposal.proposal_id, now=_now())

    rows = repo.list_subject(
        tenant_id="tenant-a",
        namespace="assistant",
        subject_id="user-a",
        include_tombstoned=True,
    )
    assert len(rows) == 1
    assert rows[0].active is False
    assert repo.pending_projection_events()[-1].action == "delete"

def _admission_for(proposal: MemoryWriteProposal):
    ledger = TenantQuotaLedger()
    ledger.configure(
        proposal.tenant_id,
        TenantQuota(
            window_id="memory-write-window",
            max_operations=10,
            max_input_tokens=10_000,
            max_output_tokens=10_000,
            max_cost_usd=100.0,
            max_tool_calls=100,
            max_artifact_bytes=1_000_000,
            max_storage_bytes=1_000_000,
            max_concurrent_operations=4,
        ),
    )
    runtime = AdmissionRuntime(quota_ledger=ledger)
    runtime.admit(
        AdmissionRequest(
            operation_id=proposal.source_operation_id,
            tenant_id=proposal.tenant_id,
            capability="memory-write",
            budget=ResourceBudget(
                max_storage_bytes=1_000_000,
            ),
            estimate=UsageEstimate(),
        ),
        now_wall=_now().timestamp(),
    )
    return runtime, ledger


def test_governed_memory_commit_meters_storage_before_persistence() -> None:
    repo = SQLiteMemoryRepository()
    governance = GovernanceRegistry()
    proposal = _proposal()
    runtime, ledger = _admission_for(proposal)
    writer = GovernedMemoryWriter(
        repo,
        governance=governance,
        admission_runtime=runtime,
    )
    writer.stage(proposal)

    record = writer.commit(proposal.proposal_id, now=_now())
    snapshot = ledger.snapshot("tenant-a")
    storage = snapshot["metered_by_category"]["storage"]

    assert record.content == "remember"
    assert storage["storage_bytes"] > 0
    assert storage["artifact_bytes"] == 0
    assert snapshot["usage_events"] == 1


def test_governed_memory_commit_requires_active_admission_when_bound() -> None:
    repo = SQLiteMemoryRepository()
    governance = GovernanceRegistry()
    proposal = _proposal()
    ledger = TenantQuotaLedger()
    ledger.configure(
        proposal.tenant_id,
        TenantQuota(
            window_id="memory-write-window",
            max_storage_bytes=1_000_000,
        ),
    )
    runtime = AdmissionRuntime(quota_ledger=ledger)
    writer = GovernedMemoryWriter(
        repo,
        governance=governance,
        admission_runtime=runtime,
    )
    writer.stage(proposal)

    with pytest.raises(
        MemoryWritebackError,
        match="memory write denied by resource admission",
    ):
        writer.commit(proposal.proposal_id, now=_now())

    assert repo.list_subject(
        tenant_id="tenant-a",
        namespace="assistant",
        subject_id="user-a",
    ) == ()


def test_governed_memory_replay_does_not_double_charge_storage() -> None:
    repo = SQLiteMemoryRepository()
    governance = GovernanceRegistry()
    proposal = _proposal()
    runtime, ledger = _admission_for(proposal)
    writer = GovernedMemoryWriter(
        repo,
        governance=governance,
        admission_runtime=runtime,
    )
    writer.stage(proposal)
    first = writer.commit(proposal.proposal_id, now=_now())
    first_snapshot = ledger.snapshot("tenant-a")

    writer.stage(proposal)
    replay = writer.commit(proposal.proposal_id, now=_now())
    replay_snapshot = ledger.snapshot("tenant-a")

    assert replay == first
    assert replay_snapshot["usage_events"] == first_snapshot["usage_events"] == 1
    assert (
        replay_snapshot["metered_by_category"]["storage"]["storage_bytes"]
        == first_snapshot["metered_by_category"]["storage"]["storage_bytes"]
    )
