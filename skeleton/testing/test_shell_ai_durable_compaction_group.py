"""Cross-chain durable compaction saga integration tests."""

from __future__ import annotations

from dataclasses import replace
import hashlib

import pytest

from skeleton.shells.ai.distributed_journal import (
    DistributedAIDecisionJournal,
)
from skeleton.shells.ai.distributed_state import (
    DistributedStateConflict,
    InMemoryFencedStore,
)
from skeleton.shells.ai.durable_archive import (
    DurableArchiveManifestBuilder,
)
from skeleton.shells.ai.durable_archive_store import (
    ArchiveBackedHistoricalChain,
    DurableArchiveRepository,
)
from skeleton.shells.ai.durable_checkpoint import (
    DurableChainCheckpointStore,
)
from skeleton.shells.ai.durable_compaction import (
    DurableCompactionPlanner,
    DurableCompactionPolicy,
)
from skeleton.shells.ai.durable_compaction_certificate import (
    DurableCompactionCertificateStore,
)
from skeleton.shells.ai.durable_compaction_group import (
    DurableCompactionGroup,
    DurableCompactionGroupCoordinator,
    DurableCompactionGroupError,
    DurableCompactionGroupManualReview,
    DurableCompactionGroupMember,
    DurableCompactionGroupPhase,
    DurableCompactionGroupRequest,
    DurableCompactionGroupStale,
    StoredDurableCompactionGroup,
)
from skeleton.shells.ai.durable_compaction_operator import (
    DurableCompactionOperator,
    DurableCompactionWorkflowPhase,
)
from skeleton.shells.ai.durable_hot_floor import (
    DurableHotFloorStore,
)
from skeleton.shells.ai.durable_pruning import (
    DurablePruningExecutor,
)
from skeleton.shells.ai.durable_pruning_authorization import (
    DurablePruningAuthorizationStore,
)
from skeleton.shells.ai.durable_retention import (
    DurableRetentionPlanner,
    DurableRetentionPolicy,
)
from skeleton.shells.ai.signed_artifact import ArtifactSigner
from skeleton.shells.distributed_receipts import (
    DistributedReceiptChain,
)
from skeleton.shells.receipts import ExecutionReceipt


def fp(value: str) -> str:
    return hashlib.sha256(
        value.encode()
    ).hexdigest()


def signer(
    name: str,
    char: bytes,
    *,
    clock=lambda: 100.0,
) -> ArtifactSigner:
    return ArtifactSigner(
        name,
        char * 32,
        clock=clock,
    )


def append_events(
    journal,
    count,
    *,
    start=0,
):
    values = []
    for index in range(
        start,
        start + count,
    ):
        values.append(
            journal.append(
                "group.event",
                session_id=f"session-{index}",
                intent_id=f"intent-{index}",
                proposal_id=f"proposal-{index}",
                summary=f"event {index}",
                data={"index": index},
            )
        )
    return tuple(values)


def receipt(index: int) -> ExecutionReceipt:
    return ExecutionReceipt(
        command="python",
        correlation_id=f"corr-{index}",
        fingerprint=fp(
            f"receipt:{index}"
        ),
        started_at=(
            "2026-09-19T00:00:00+00:00"
        ),
        finished_at=(
            "2026-09-19T00:00:01+00:00"
        ),
        duration_ms=1.0,
        returncode=0,
        ok=True,
        timed_out=False,
        output_limited=False,
        stdout_bytes=index + 1,
        stderr_bytes=0,
        attempt=1,
        receipt_id=f"receipt-{index}",
        metadata={"index": index},
    )


class FailTargetOnceOperator(
    DurableCompactionOperator
):
    def __init__(
        self,
        *args,
        target_chain="receipts",
        **kwargs,
    ):
        super().__init__(
            *args,
            **kwargs,
        )
        self.target_chain = (
            target_chain
        )
        self.fail_enabled = False
        self.failed = False

    def execute(
        self,
        workflow_id,
        retention,
        chain,
        **kwargs,
    ):
        stored = self.current(
            workflow_id
        )
        if (
            self.fail_enabled
            and not self.failed
            and stored is not None
            and stored.workflow.chain_id
            == self.target_chain
        ):
            self.failed = True
            raise RuntimeError(
                "synthetic group second-member failure"
            )
        return super().execute(
            workflow_id,
            retention,
            chain,
            **kwargs,
        )


class ManualReviewTargetOperator(
    DurableCompactionOperator
):
    def __init__(
        self,
        *args,
        target_chain="receipts",
        **kwargs,
    ):
        super().__init__(
            *args,
            **kwargs,
        )
        self.target_chain = (
            target_chain
        )
        self.fail_enabled = False

    def execute(
        self,
        workflow_id,
        retention,
        chain,
        **kwargs,
    ):
        stored = self.current(
            workflow_id
        )
        if (
            self.fail_enabled
            and stored is not None
            and stored.workflow.chain_id
            == self.target_chain
        ):
            raise (
                DurableCompactionGroupManualReview(
                    "synthetic member manual review"
                )
            )
        return super().execute(
            workflow_id,
            retention,
            chain,
            **kwargs,
        )


class GroupFixture:
    def __init__(
        self,
        *,
        backend=None,
        operator_class=DurableCompactionOperator,
    ):
        self.now = [400.0]
        self.nonce = [0]
        self.backend = (
            backend
            or InMemoryFencedStore()
        )
        self.floor_store = (
            DurableHotFloorStore(
                self.backend,
                signer(
                    "floor",
                    b"f",
                    clock=lambda: self.now[0],
                ),
                namespace="group-hot-floors",
                clock=lambda: self.now[0],
            )
        )

        self.journal = (
            DistributedAIDecisionJournal(
                self.backend,
                namespace="journal",
                max_events=20,
                clock=lambda: 10.0,
                hot_floor_store=(
                    self.floor_store
                ),
                hot_floor_chain_id=(
                    "journal"
                ),
            )
        )
        self.receipts = (
            DistributedReceiptChain(
                self.backend,
                namespace="receipts",
                max_receipts=20,
                hot_floor_store=(
                    self.floor_store
                ),
                hot_floor_chain_id=(
                    "receipts"
                ),
            )
        )
        self.first_journal = (
            append_events(
                self.journal,
                6,
            )
        )
        self.first_receipts = tuple(
            self.receipts.append(
                receipt(index)
            )
            for index in range(6)
        )

        self.checkpoints = (
            DurableChainCheckpointStore(
                self.backend,
                signer(
                    "checkpoint",
                    b"c",
                ),
                namespace="group-checkpoints",
                clock=lambda: 100.0,
            )
        )
        self.archive_signer = signer(
            "archive",
            b"a",
            clock=lambda: 200.0,
        )
        self.archive_builder = (
            DurableArchiveManifestBuilder(
                self.checkpoints,
                self.archive_signer,
                clock=lambda: 200.0,
            )
        )
        self.archives = (
            DurableArchiveRepository(
                self.backend,
                self.checkpoints,
                self.archive_signer,
                namespace="group-archives",
                clock=lambda: 300.0,
            )
        )

        for chain_id, chain in (
            ("journal", self.journal),
            ("receipts", self.receipts),
        ):
            checkpoint = (
                self.checkpoints.publish(
                    chain_id,
                    chain,
                )
            )
            archive = (
                self.archive_builder.build(
                    checkpoint,
                    chain,
                )
            )
            self.archives.put(
                archive,
                checkpoint,
                chain,
            )

        self.later_journal = (
            append_events(
                self.journal,
                2,
                start=6,
            )
        )
        self.later_receipts = tuple(
            self.receipts.append(
                receipt(index)
            )
            for index in range(
                6,
                8,
            )
        )

        self.retention_planner = (
            DurableRetentionPlanner(
                self.checkpoints,
                DurableRetentionPolicy(
                    minimum_live_tail=2,
                    minimum_archive_batch=2,
                    target_utilization=0.25,
                    warning_utilization=0.75,
                    critical_utilization=0.95,
                    max_protected_roots=32,
                ),
            )
        )
        self.journal_retention = (
            self.retention_planner.plan(
                "journal",
                self.journal,
            )
        )
        self.receipt_retention = (
            self.retention_planner.plan(
                "receipts",
                self.receipts,
            )
        )
        self.compaction = (
            DurableCompactionPlanner(
                self.archives,
                DurableCompactionPolicy(
                    minimum_live_tail=2,
                    maximum_candidate_nodes=20,
                    max_protected_roots=32,
                ),
            )
        )
        assert (
            self.compaction
            .require_ready(
                self.journal_retention,
                self.journal,
            )
            .ready
        )
        assert (
            self.compaction
            .require_ready(
                self.receipt_retention,
                self.receipts,
            )
            .ready
        )

        self.certificates = (
            DurableCompactionCertificateStore(
                self.backend,
                signer(
                    "certificate",
                    b"s",
                    clock=lambda: self.now[0],
                ),
                self.compaction,
                namespace="group-certificates",
                ttl_seconds=60.0,
                max_ttl_seconds=3600.0,
                clock=lambda: self.now[0],
            )
        )

        def nonce():
            self.nonce[0] += 1
            return (
                "group-nonce-"
                f"{self.nonce[0]}"
            )

        self.authorizations = (
            DurablePruningAuthorizationStore(
                self.backend,
                signer(
                    "pruning",
                    b"p",
                    clock=lambda: self.now[0],
                ),
                self.certificates,
                namespace="group-authorizations",
                ttl_seconds=30.0,
                max_ttl_seconds=600.0,
                max_delete_items=100,
                clock=lambda: self.now[0],
                nonce_factory=nonce,
            )
        )
        self.executor = (
            DurablePruningExecutor(
                self.backend,
                self.authorizations,
                self.floor_store,
                namespace="group-pruning",
                max_items=100,
                clock=lambda: self.now[0],
            )
        )
        self.operator = operator_class(
            self.backend,
            self.compaction,
            self.certificates,
            self.authorizations,
            self.executor,
            namespace="group-member-workflows",
            clock=lambda: self.now[0],
        )
        self.coordinator = (
            DurableCompactionGroupCoordinator(
                self.backend,
                namespace="compaction-groups",
                clock=lambda: self.now[0],
            )
        )

    def requests(self):
        return (
            DurableCompactionGroupRequest(
                "journal",
                self.operator,
                self.journal_retention,
                self.journal,
            ),
            DurableCompactionGroupRequest(
                "receipts",
                self.operator,
                self.receipt_retention,
                self.receipts,
            ),
        )

    def plan(self):
        return self.coordinator.plan(
            self.requests(),
            epoch_id="evidence-epoch-1",
            operator_id="operator",
        )

    def through_prepared(self):
        planned = self.plan()
        certified = (
            self.coordinator
            .certify_all(
                planned.group.group_id,
                self.requests(),
            )
        )
        authorized = (
            self.coordinator
            .authorize_all(
                planned.group.group_id,
                self.requests(),
            )
        )
        prepared = (
            self.coordinator
            .prepare_all(
                planned.group.group_id,
                self.requests(),
            )
        )
        return (
            planned,
            certified,
            authorized,
            prepared,
        )

    def through_complete(self):
        (
            planned,
            certified,
            authorized,
            prepared,
        ) = self.through_prepared()
        completed = (
            self.coordinator.execute(
                planned.group.group_id,
                self.requests(),
            )
        )
        return (
            planned,
            certified,
            authorized,
            prepared,
            completed,
        )


def test_group_plan_is_non_destructive():
    fixture = GroupFixture()
    journal_before = (
        fixture.journal.snapshot()
    )
    receipt_before = (
        fixture.receipts.snapshot()
    )
    stored = fixture.plan()
    group = stored.group

    assert (
        group.phase
        is DurableCompactionGroupPhase.PLANNED
    )
    assert len(group.members) == 2
    assert tuple(
        member.chain_id
        for member in group.members
    ) == (
        "journal",
        "receipts",
    )
    assert (
        fixture.journal.snapshot()
        == journal_before
    )
    assert (
        fixture.receipts.snapshot()
        == receipt_before
    )
    assert (
        fixture.journal
        .hot_floor()
        .sequence
        == 0
    )
    assert (
        fixture.receipts
        .hot_floor()
        .sequence
        == 0
    )


def test_group_plan_is_idempotent_and_order_independent():
    fixture = GroupFixture()
    first = fixture.plan()
    second = (
        fixture.coordinator.plan(
            tuple(
                reversed(
                    fixture.requests()
                )
            ),
            epoch_id="evidence-epoch-1",
            operator_id="operator",
        )
    )
    assert (
        second.group.group_id
        == first.group.group_id
    )
    assert (
        second.revision
        == first.revision
    )
    assert second.group == first.group


def test_group_id_changes_with_epoch():
    fixture = GroupFixture()
    first = fixture.plan()
    second = (
        fixture.coordinator.plan(
            fixture.requests(),
            epoch_id="evidence-epoch-2",
            operator_id="operator",
        )
    )
    assert (
        second.group.group_id
        != first.group.group_id
    )


def test_group_id_changes_with_operator():
    fixture = GroupFixture()
    first = fixture.plan()
    second = (
        fixture.coordinator.plan(
            fixture.requests(),
            epoch_id="evidence-epoch-1",
            operator_id="other-operator",
        )
    )
    assert (
        second.group.group_id
        != first.group.group_id
    )


def test_certify_all_binds_every_member_without_destructive_authority():
    fixture = GroupFixture()
    planned = fixture.plan()
    certified = (
        fixture.coordinator.certify_all(
            planned.group.group_id,
            fixture.requests(),
        )
    )
    group = certified.group
    assert (
        group.phase
        is DurableCompactionGroupPhase.CERTIFIED
    )
    assert all(
        member.certificate_id
        for member in group.members
    )
    assert all(
        not member.authorization_id
        for member in group.members
    )
    assert (
        fixture.journal
        .hot_floor()
        .sequence
        == 0
    )
    assert (
        fixture.receipts
        .hot_floor()
        .sequence
        == 0
    )


def test_authorize_all_requires_certified_group():
    fixture = GroupFixture()
    planned = fixture.plan()
    with pytest.raises(
        DurableCompactionGroupError,
        match="certified",
    ):
        fixture.coordinator.authorize_all(
            planned.group.group_id,
            fixture.requests(),
        )


def test_authorize_all_binds_every_member():
    fixture = GroupFixture()
    planned = fixture.plan()
    fixture.coordinator.certify_all(
        planned.group.group_id,
        fixture.requests(),
    )
    authorized = (
        fixture.coordinator
        .authorize_all(
            planned.group.group_id,
            fixture.requests(),
        )
    )
    assert (
        authorized.group.phase
        is DurableCompactionGroupPhase.AUTHORIZED
    )
    assert all(
        member.authorization_id
        for member in authorized.group.members
    )
    assert all(
        member.delete_count == 6
        for member
        in authorized.group.members
    )


def test_prepare_all_requires_authorized_group():
    fixture = GroupFixture()
    planned = fixture.plan()
    fixture.coordinator.certify_all(
        planned.group.group_id,
        fixture.requests(),
    )
    with pytest.raises(
        DurableCompactionGroupError,
        match="authorized",
    ):
        fixture.coordinator.prepare_all(
            planned.group.group_id,
            fixture.requests(),
        )


def test_prepare_all_freezes_every_manifest_before_deletion():
    fixture = GroupFixture()
    journal_before = (
        fixture.journal.snapshot()
    )
    receipt_before = (
        fixture.receipts.snapshot()
    )
    *_, prepared = (
        fixture.through_prepared()
    )
    group = prepared.group

    assert (
        group.phase
        is DurableCompactionGroupPhase.PREPARED
    )
    assert all(
        member.prepared
        for member in group.members
    )
    assert all(
        member.pruning_operation_id
        for member in group.members
    )
    assert all(
        member.pruning_manifest_digest
        for member in group.members
    )
    assert (
        fixture.journal.snapshot()
        == journal_before
    )
    assert (
        fixture.receipts.snapshot()
        == receipt_before
    )
    assert (
        fixture.journal
        .hot_floor()
        .sequence
        == 0
    )
    assert (
        fixture.receipts
        .hot_floor()
        .sequence
        == 0
    )


def test_execute_requires_fully_prepared_group():
    fixture = GroupFixture()
    planned = fixture.plan()
    fixture.coordinator.certify_all(
        planned.group.group_id,
        fixture.requests(),
    )
    fixture.coordinator.authorize_all(
        planned.group.group_id,
        fixture.requests(),
    )
    with pytest.raises(
        DurableCompactionGroupError,
        match="fully prepared",
    ):
        fixture.coordinator.execute(
            planned.group.group_id,
            fixture.requests(),
        )


def test_group_execute_compacts_both_chains():
    fixture = GroupFixture()
    *_, completed = (
        fixture.through_complete()
    )
    group = completed.group

    assert (
        group.phase
        is DurableCompactionGroupPhase.COMPLETE
    )
    assert group.complete
    assert group.completed_members == 2
    assert group.next_member_index == 2
    assert all(
        member.complete
        for member in group.members
    )
    assert (
        fixture.journal.snapshot()
        == fixture.later_journal
    )
    assert (
        fixture.receipts.snapshot()
        == fixture.later_receipts
    )
    assert (
        fixture.journal
        .hot_floor()
        .sequence
        == 6
    )
    assert (
        fixture.receipts
        .hot_floor()
        .sequence
        == 6
    )
    assert fixture.journal.verify()
    assert fixture.receipts.verify()


def test_completed_group_preserves_both_archived_histories():
    fixture = GroupFixture()
    fixture.through_complete()

    journal_history = (
        ArchiveBackedHistoricalChain(
            "journal",
            fixture.journal,
            fixture.archives,
        )
    )
    receipt_history = (
        ArchiveBackedHistoricalChain(
            "receipts",
            fixture.receipts,
            fixture.archives,
        )
    )
    journal_root = (
        fixture.journal_retention
        .archive_through_root
    )
    receipt_root = (
        fixture.receipt_retention
        .archive_through_root
    )

    assert len(
        journal_history.snapshot_at(
            journal_root
        )
    ) == 6
    assert len(
        receipt_history.snapshot_at(
            receipt_root
        )
    ) == 6
    assert journal_history.verify()
    assert receipt_history.verify()


def test_execute_complete_group_is_idempotent():
    fixture = GroupFixture()
    (
        planned,
        _,
        _,
        _,
        completed,
    ) = fixture.through_complete()
    again = (
        fixture.coordinator.execute(
            planned.group.group_id,
            fixture.requests(),
        )
    )
    assert again == completed


def test_fresh_coordinator_reads_complete_group():
    fixture = GroupFixture()
    *_, completed = (
        fixture.through_complete()
    )
    fresh = (
        DurableCompactionGroupCoordinator(
            fixture.backend,
            namespace="compaction-groups",
            clock=lambda: fixture.now[0],
        )
    )
    restored = fresh.current(
        completed.group.group_id
    )
    assert restored == completed


def test_group_inspection_is_safe_before_execution():
    fixture = GroupFixture()
    *_, prepared = (
        fixture.through_prepared()
    )
    report = (
        fixture.coordinator.inspect(
            prepared.group.group_id,
            fixture.requests(),
        )
    )
    assert report.current
    assert report.safe_to_execute
    assert not report.partial_commit
    assert not report.safe_to_resume
    assert report.reasons == ()


def test_group_member_order_is_stable_in_serialization():
    fixture = GroupFixture()
    stored = fixture.plan()
    data = stored.group.to_dict()
    assert [
        member["chain_id"]
        for member in data["members"]
    ] == [
        "journal",
        "receipts",
    ]
    assert len(
        data["binding_digest"]
    ) == 64
    assert len(data["digest"]) == 64


def test_stale_journal_member_blocks_group_certification():
    fixture = GroupFixture()
    planned = fixture.plan()
    append_events(
        fixture.journal,
        1,
        start=8,
    )
    with pytest.raises(Exception):
        fixture.coordinator.certify_all(
            planned.group.group_id,
            fixture.requests(),
        )
    assert (
        fixture.coordinator
        .current(
            planned.group.group_id
        )
        .group.phase
        is DurableCompactionGroupPhase.PLANNED
    )


def test_stale_receipt_member_blocks_group_certification_after_other_member_certifies():
    fixture = GroupFixture()
    planned = fixture.plan()
    fixture.receipts.append(
        receipt(8)
    )
    with pytest.raises(Exception):
        fixture.coordinator.certify_all(
            planned.group.group_id,
            fixture.requests(),
        )
    journal_workflow = (
        fixture.operator.current(
            next(
                member.workflow_id
                for member
                in planned.group.members
                if member.chain_id
                == "journal"
            )
        )
    )
    assert journal_workflow is not None
    assert (
        journal_workflow.workflow.phase
        in {
            DurableCompactionWorkflowPhase.PLANNED,
            DurableCompactionWorkflowPhase.CERTIFIED,
        }
    )


def test_group_request_set_must_match_persisted_membership():
    fixture = GroupFixture()
    planned = fixture.plan()
    with pytest.raises(
        DurableCompactionGroupError,
        match="request set",
    ):
        fixture.coordinator.certify_all(
            planned.group.group_id,
            fixture.requests()[:1],
        )


def test_group_retention_substitution_is_rejected():
    fixture = GroupFixture()
    planned = fixture.plan()
    protected = (
        fixture.first_journal[1]
        .event_hash
    )
    changed = (
        fixture.retention_planner.plan(
            "journal",
            fixture.journal,
            protected_roots=(
                protected,
            ),
        )
    )
    requests = (
        DurableCompactionGroupRequest(
            "journal",
            fixture.operator,
            changed,
            fixture.journal,
        ),
        fixture.requests()[1],
    )
    with pytest.raises(
        DurableCompactionGroupStale,
        match="retention",
    ):
        fixture.coordinator.certify_all(
            planned.group.group_id,
            requests,
        )


def test_partial_commit_is_persisted_when_second_member_fails_before_floor():
    fixture = GroupFixture(
        operator_class=(
            FailTargetOnceOperator
        ),
    )
    (
        planned,
        _,
        _,
        _,
    ) = fixture.through_prepared()
    fixture.operator.fail_enabled = True

    with pytest.raises(
        RuntimeError,
        match="synthetic group second-member failure",
    ):
        fixture.coordinator.execute(
            planned.group.group_id,
            fixture.requests(),
        )

    stored = (
        fixture.coordinator.current(
            planned.group.group_id
        )
    )
    assert (
        stored.group.phase
        is DurableCompactionGroupPhase.PARTIAL_COMMIT
    )
    assert stored.group.partial_commit
    assert stored.group.resumable
    journal_member = next(
        member
        for member in stored.group.members
        if member.chain_id == "journal"
    )
    receipt_member = next(
        member
        for member in stored.group.members
        if member.chain_id == "receipts"
    )
    assert journal_member.complete
    assert journal_member.floor_committed
    assert not receipt_member.complete
    assert not receipt_member.floor_committed
    assert (
        fixture.journal
        .hot_floor()
        .sequence
        == 6
    )
    assert (
        fixture.receipts
        .hot_floor()
        .sequence
        == 0
    )


def test_partial_commit_requires_explicit_resume():
    fixture = GroupFixture(
        operator_class=(
            FailTargetOnceOperator
        ),
    )
    planned, *_ = (
        fixture.through_prepared()
    )
    fixture.operator.fail_enabled = True
    with pytest.raises(RuntimeError):
        fixture.coordinator.execute(
            planned.group.group_id,
            fixture.requests(),
        )
    stored = fixture.coordinator.current(
        planned.group.group_id
    )
    assert stored.group.partial_commit
    report = fixture.coordinator.inspect(
        planned.group.group_id,
        fixture.requests(),
    )
    assert report.partial_commit
    assert report.safe_to_resume
    assert not report.safe_to_execute


def test_partial_commit_resume_finishes_second_member():
    fixture = GroupFixture(
        operator_class=(
            FailTargetOnceOperator
        ),
    )
    planned, *_ = (
        fixture.through_prepared()
    )
    fixture.operator.fail_enabled = True
    with pytest.raises(RuntimeError):
        fixture.coordinator.execute(
            planned.group.group_id,
            fixture.requests(),
        )

    fixture.operator.fail_enabled = False
    completed = (
        fixture.coordinator.resume(
            planned.group.group_id,
            fixture.requests(),
        )
    )
    assert completed.group.complete
    assert (
        fixture.receipts
        .hot_floor()
        .sequence
        == 6
    )
    assert (
        fixture.receipts.snapshot()
        == fixture.later_receipts
    )


def test_fresh_coordinator_resumes_partial_commit():
    fixture = GroupFixture(
        operator_class=(
            FailTargetOnceOperator
        ),
    )
    planned, *_ = (
        fixture.through_prepared()
    )
    fixture.operator.fail_enabled = True
    with pytest.raises(RuntimeError):
        fixture.coordinator.execute(
            planned.group.group_id,
            fixture.requests(),
        )
    fixture.operator.fail_enabled = False

    fresh = (
        DurableCompactionGroupCoordinator(
            fixture.backend,
            namespace="compaction-groups",
            clock=lambda: fixture.now[0],
        )
    )
    completed = fresh.resume(
        planned.group.group_id,
        fixture.requests(),
    )
    assert completed.group.complete


def test_manual_review_member_escalates_group():
    fixture = GroupFixture(
        operator_class=(
            ManualReviewTargetOperator
        ),
    )
    planned, *_ = (
        fixture.through_prepared()
    )
    fixture.operator.fail_enabled = True

    with pytest.raises(
        DurableCompactionGroupManualReview,
    ):
        fixture.coordinator.execute(
            planned.group.group_id,
            fixture.requests(),
        )
    stored = fixture.coordinator.current(
        planned.group.group_id
    )
    assert (
        stored.group.phase
        is DurableCompactionGroupPhase.MANUAL_REVIEW
    )
    assert stored.group.requires_manual_review


def test_manual_review_group_cannot_resume_automatically():
    fixture = GroupFixture(
        operator_class=(
            ManualReviewTargetOperator
        ),
    )
    planned, *_ = (
        fixture.through_prepared()
    )
    fixture.operator.fail_enabled = True
    with pytest.raises(
        DurableCompactionGroupManualReview,
    ):
        fixture.coordinator.execute(
            planned.group.group_id,
            fixture.requests(),
        )
    with pytest.raises(
        DurableCompactionGroupManualReview,
    ):
        fixture.coordinator.resume(
            planned.group.group_id,
            fixture.requests(),
        )


def test_group_revision_advances_monotonically():
    fixture = GroupFixture()
    planned = fixture.plan()
    revisions = [
        planned.revision
    ]
    certified = (
        fixture.coordinator
        .certify_all(
            planned.group.group_id,
            fixture.requests(),
        )
    )
    revisions.append(
        certified.revision
    )
    authorized = (
        fixture.coordinator
        .authorize_all(
            planned.group.group_id,
            fixture.requests(),
        )
    )
    revisions.append(
        authorized.revision
    )
    prepared = (
        fixture.coordinator
        .prepare_all(
            planned.group.group_id,
            fixture.requests(),
        )
    )
    revisions.append(
        prepared.revision
    )
    completed = (
        fixture.coordinator.execute(
            planned.group.group_id,
            fixture.requests(),
        )
    )
    revisions.append(
        completed.revision
    )

    assert revisions == sorted(
        revisions
    )
    assert len(set(revisions)) == 5


def test_group_binding_digest_is_stable_across_phases():
    fixture = GroupFixture()
    planned = fixture.plan()
    binding = (
        planned.group.binding_digest
    )
    fixture.coordinator.certify_all(
        planned.group.group_id,
        fixture.requests(),
    )
    fixture.coordinator.authorize_all(
        planned.group.group_id,
        fixture.requests(),
    )
    fixture.coordinator.prepare_all(
        planned.group.group_id,
        fixture.requests(),
    )
    completed = (
        fixture.coordinator.execute(
            planned.group.group_id,
            fixture.requests(),
        )
    )
    assert (
        completed.group.binding_digest
        == binding
    )


def test_duplicate_chain_id_is_rejected():
    fixture = GroupFixture()
    request = fixture.requests()[0]
    with pytest.raises(
        ValueError,
        match="duplicate",
    ):
        fixture.coordinator.plan(
            (request, request),
            epoch_id="epoch",
            operator_id="operator",
        )


def test_single_member_group_is_rejected():
    fixture = GroupFixture()
    with pytest.raises(
        ValueError,
        match="member count",
    ):
        fixture.coordinator.plan(
            fixture.requests()[:1],
            epoch_id="epoch",
            operator_id="operator",
        )


def test_missing_group_is_rejected():
    fixture = GroupFixture()
    with pytest.raises(
        DurableCompactionGroupError,
        match="missing",
    ):
        fixture.coordinator.certify_all(
            fp("missing"),
            fixture.requests(),
        )


def test_current_missing_group_returns_none():
    fixture = GroupFixture()
    assert (
        fixture.coordinator.current(
            fp("missing")
        )
        is None
    )


def test_wrong_group_backend_value_type_is_rejected():
    fixture = GroupFixture()
    group_id = fp("bad-group")
    fixture.backend.put_if_absent(
        fixture.coordinator.namespace,
        fixture.coordinator._key(
            group_id
        ),
        {"bad": True},
    )
    with pytest.raises(
        DurableCompactionGroupError,
        match="value type",
    ):
        fixture.coordinator.current(
            group_id
        )


def test_coordinator_namespace_validation():
    with pytest.raises(
        ValueError,
        match="namespace",
    ):
        DurableCompactionGroupCoordinator(
            InMemoryFencedStore(),
            namespace="",
        )


@pytest.mark.parametrize(
    "max_members",
    [0, 1, 65, True],
)
def test_coordinator_member_bound_validation(max_members):
    with pytest.raises(
        ValueError,
        match="max_members",
    ):
        DurableCompactionGroupCoordinator(
            InMemoryFencedStore(),
            max_members=max_members,
        )


@pytest.mark.parametrize(
    "retries",
    [0, 129, True],
)
def test_coordinator_retry_bound_validation(retries):
    with pytest.raises(
        ValueError,
        match="max_cas_retries",
    ):
        DurableCompactionGroupCoordinator(
            InMemoryFencedStore(),
            max_cas_retries=retries,
        )


def test_coordinator_invalid_clock_blocks_plan():
    fixture = GroupFixture()
    bad = DurableCompactionGroupCoordinator(
        fixture.backend,
        namespace="bad-clock-groups",
        clock=lambda: float("nan"),
    )
    with pytest.raises(
        DurableCompactionGroupError,
        match="clock",
    ):
        bad.plan(
            fixture.requests(),
            epoch_id="epoch",
            operator_id="operator",
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("workflow_id", "bad"),
        ("workflow_binding_digest", "bad"),
        ("retention_plan_digest", "bad"),
        ("current_sequence", -1),
        ("cutoff_sequence", 0),
        ("previous_floor_sequence", -1),
        ("archive_id", ""),
    ],
)
def test_group_member_validation(field, value):
    values = dict(
        chain_id="journal",
        workflow_id=fp("workflow"),
        workflow_binding_digest=fp(
            "binding"
        ),
        retention_plan_digest=fp(
            "retention"
        ),
        current_sequence=8,
        current_root=fp("head"),
        cutoff_sequence=6,
        cutoff_root=fp("cutoff"),
        previous_floor_sequence=0,
        previous_floor_root="0" * 64,
        archive_id="archive",
        archive_manifest_digest=fp(
            "archive"
        ),
    )
    values[field] = value
    with pytest.raises(
        (ValueError, TypeError),
    ):
        DurableCompactionGroupMember(
            **values
        )


def _member(
    chain_id,
    *,
    suffix,
):
    return DurableCompactionGroupMember(
        chain_id,
        fp(f"workflow:{suffix}"),
        fp(f"binding:{suffix}"),
        fp(f"retention:{suffix}"),
        8,
        fp(f"head:{suffix}"),
        6,
        fp(f"cutoff:{suffix}"),
        0,
        "0" * 64,
        f"archive-{suffix}",
        fp(f"archive:{suffix}"),
    )


def test_group_requires_sorted_unique_members():
    first = _member(
        "journal",
        suffix="j",
    )
    second = _member(
        "receipts",
        suffix="r",
    )
    with pytest.raises(
        ValueError,
        match="sorted",
    ):
        DurableCompactionGroup(
            1,
            fp("group"),
            "epoch",
            "operator",
            DurableCompactionGroupPhase.PLANNED,
            (second, first),
            1.0,
            1.0,
        )


def test_group_requires_at_least_two_members():
    with pytest.raises(
        ValueError,
        match="at least two",
    ):
        DurableCompactionGroup(
            1,
            fp("group"),
            "epoch",
            "operator",
            DurableCompactionGroupPhase.PLANNED,
            (
                _member(
                    "journal",
                    suffix="j",
                ),
            ),
            1.0,
            1.0,
        )


def test_prepared_group_requires_all_member_manifests():
    with pytest.raises(
        ValueError,
        match="manifest",
    ):
        DurableCompactionGroup(
            1,
            fp("group"),
            "epoch",
            "operator",
            DurableCompactionGroupPhase.PREPARED,
            (
                _member(
                    "journal",
                    suffix="j",
                ),
                _member(
                    "receipts",
                    suffix="r",
                ),
            ),
            1.0,
            1.0,
        )


def test_complete_group_requires_all_members_complete():
    with pytest.raises(
        ValueError,
        match="every member",
    ):
        DurableCompactionGroup(
            1,
            fp("group"),
            "epoch",
            "operator",
            DurableCompactionGroupPhase.COMPLETE,
            (
                _member(
                    "journal",
                    suffix="j",
                ),
                _member(
                    "receipts",
                    suffix="r",
                ),
            ),
            1.0,
            1.0,
        )


def test_stored_group_revision_validation():
    group = DurableCompactionGroup(
        1,
        fp("group"),
        "epoch",
        "operator",
        DurableCompactionGroupPhase.PLANNED,
        (
            _member(
                "journal",
                suffix="j",
            ),
            _member(
                "receipts",
                suffix="r",
            ),
        ),
        1.0,
        1.0,
    )
    with pytest.raises(ValueError):
        StoredDurableCompactionGroup(
            0,
            group,
        )


class ConflictOnceBackend(
    InMemoryFencedStore
):
    def __init__(self):
        super().__init__()
        self.group_conflicted = False

    def compare_and_swap(
        self,
        namespace,
        key,
        *,
        expected_revision,
        value,
    ):
        if (
            namespace
            == "compaction-groups"
            and key.startswith("group:")
            and not self.group_conflicted
        ):
            self.group_conflicted = True
            raise DistributedStateConflict(
                "synthetic group CAS race"
            )
        return super().compare_and_swap(
            namespace,
            key,
            expected_revision=expected_revision,
            value=value,
        )


def test_group_transition_retries_cas_conflict():
    backend = ConflictOnceBackend()
    fixture = GroupFixture(
        backend=backend
    )
    planned = fixture.plan()
    certified = (
        fixture.coordinator.certify_all(
            planned.group.group_id,
            fixture.requests(),
        )
    )
    assert backend.group_conflicted
    assert (
        certified.group.phase
        is DurableCompactionGroupPhase.CERTIFIED
    )


def test_request_validates_retention_chain_identity():
    fixture = GroupFixture()
    with pytest.raises(
        ValueError,
        match="chain_id",
    ):
        DurableCompactionGroupRequest(
            "wrong",
            fixture.operator,
            fixture.journal_retention,
            fixture.journal,
        )


def test_group_inspection_serializes_member_status():
    fixture = GroupFixture()
    *_, prepared = (
        fixture.through_prepared()
    )
    report = fixture.coordinator.inspect(
        prepared.group.group_id,
        fixture.requests(),
    )
    data = report.to_dict()
    assert data["current"] is True
    assert data["safe_to_execute"] is True
    assert [
        item["chain_id"]
        for item
        in data["member_current"]
    ] == [
        "journal",
        "receipts",
    ]
    assert all(
        item["current"]
        for item
        in data["member_current"]
    )
