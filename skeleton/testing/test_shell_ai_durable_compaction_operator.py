"""End-to-end durable compaction workflow operator tests."""

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
from skeleton.shells.ai.durable_compaction_lineage import (
    CompactionLineageStatus,
    DurableCompactionLineageAuditor,
    DurableCompactionLineageError,
)
from skeleton.shells.ai.durable_compaction_lineage_health import (
    CompactionLineageFleetError,
    CompactionLineageFleetGuard,
    CompactionLineageHealthFinding,
    CompactionLineageHealthPolicy,
    CompactionLineageHealthSeverity,
)
from skeleton.shells.ai.durable_compaction_maintenance import (
    CompactionMaintenanceFinding,
    CompactionMaintenancePolicy,
    CompactionMaintenanceSeverity,
    DurableCompactionMaintenanceError,
    DurableCompactionMaintenanceGuard,
)
from skeleton.shells.ai.durable_compaction_operator import (
    DurableCompactionExecution,
    DurableCompactionOperator,
    DurableCompactionPrepared,
    DurableCompactionWorkflow,
    DurableCompactionWorkflowError,
    DurableCompactionWorkflowManualReview,
    DurableCompactionWorkflowPhase,
    DurableCompactionWorkflowStale,
    StoredDurableCompactionWorkflow,
)
from skeleton.shells.ai.durable_maintenance import (
    DurableMaintenanceConflict,
    DurableMaintenanceOperation,
    DurableMaintenanceResource,
    DurableMaintenanceStale,
    DurableMaintenanceStore,
)
from skeleton.shells.ai.durable_hot_floor import (
    DurableHotFloorStore,
)
from skeleton.shells.ai.durable_pruning import (
    DurablePruningExecutor,
    DurablePruningPhase,
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
                "operator.event",
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


class FailDeleteOnceBackend(
    InMemoryFencedStore
):
    def __init__(self):
        super().__init__()
        self.fail_enabled = False
        self.fail_after = 1
        self.calls = 0
        self.failed = False

    def delete(
        self,
        namespace,
        key,
        *,
        expected_revision,
    ):
        if (
            self.fail_enabled
            and not self.failed
        ):
            self.calls += 1
            if self.calls > self.fail_after:
                self.failed = True
                raise RuntimeError(
                    "synthetic operator pruning crash"
                )
        return super().delete(
            namespace,
            key,
            expected_revision=expected_revision,
        )


class OperatorFixture:
    def __init__(
        self,
        *,
        kind="journal",
        backend=None,
        now=400.0,
        max_items=100,
        maintenance=False,
        maintenance_store=None,
    ):
        self.kind = kind
        self.now = [float(now)]
        self.nonce = [0]
        self.backend = (
            backend
            or InMemoryFencedStore()
        )
        self.floor_store = (
            DurableHotFloorStore(
                self.backend,
                signer(
                    "hot-floor",
                    b"f",
                    clock=lambda: self.now[0],
                ),
                namespace=(
                    f"{kind}-hot-floors"
                ),
                clock=lambda: self.now[0],
            )
        )

        if kind == "journal":
            self.chain = (
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
            self.chain_id = "journal"
            self.first = append_events(
                self.chain,
                6,
            )
        elif kind == "receipts":
            self.chain = (
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
            self.chain_id = "receipts"
            self.first = tuple(
                self.chain.append(
                    receipt(index)
                )
                for index in range(6)
            )
        else:
            raise ValueError(
                "unknown fixture kind"
            )

        self.checkpoints = (
            DurableChainCheckpointStore(
                self.backend,
                signer(
                    "checkpoint",
                    b"c",
                ),
                namespace=(
                    f"{kind}-checkpoints"
                ),
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
                namespace=(
                    f"{kind}-archives"
                ),
                clock=lambda: 300.0,
            )
        )
        checkpoint = (
            self.checkpoints.publish(
                self.chain_id,
                self.chain,
            )
        )
        archive = (
            self.archive_builder.build(
                checkpoint,
                self.chain,
            )
        )
        self.archives.put(
            archive,
            checkpoint,
            self.chain,
        )
        self.archive = archive

        if kind == "journal":
            self.later = append_events(
                self.chain,
                2,
                start=6,
            )
        else:
            self.later = tuple(
                self.chain.append(
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
        self.retention = (
            self.retention_planner.plan(
                self.chain_id,
                self.chain,
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
                self.retention,
                self.chain,
            )
            .ready
        )

        self.certificate_store = (
            DurableCompactionCertificateStore(
                self.backend,
                signer(
                    "certificate",
                    b"s",
                    clock=(
                        lambda:
                        self.now[0]
                    ),
                ),
                self.compaction,
                namespace=(
                    f"{kind}-certificates"
                ),
                ttl_seconds=60.0,
                max_ttl_seconds=3600.0,
                clock=lambda: self.now[0],
            )
        )

        def nonce():
            self.nonce[0] += 1
            return (
                f"nonce-{kind}-"
                f"{self.nonce[0]}"
            )

        self.authorization_store = (
            DurablePruningAuthorizationStore(
                self.backend,
                signer(
                    "pruning",
                    b"p",
                    clock=(
                        lambda:
                        self.now[0]
                    ),
                ),
                self.certificate_store,
                namespace=(
                    f"{kind}-authorizations"
                ),
                ttl_seconds=30.0,
                max_ttl_seconds=600.0,
                max_delete_items=max_items,
                clock=lambda: self.now[0],
                nonce_factory=nonce,
            )
        )
        self.maintenance = maintenance_store
        if maintenance and self.maintenance is None:
            self.maintenance = DurableMaintenanceStore(
                self.backend,
                signer(
                    f"{kind}-maintenance",
                    b"m",
                ),
                namespace=(
                    f"{kind}-maintenance-epochs"
                ),
            )
        self.executor = (
            DurablePruningExecutor(
                self.backend,
                self.authorization_store,
                self.floor_store,
                maintenance=self.maintenance,
                namespace=(
                    f"{kind}-pruning"
                ),
                max_items=max_items,
                clock=lambda: self.now[0],
            )
        )
        self.operator = (
            DurableCompactionOperator(
                self.backend,
                self.compaction,
                self.certificate_store,
                self.authorization_store,
                self.executor,
                maintenance=self.maintenance,
                namespace=(
                    f"{kind}-operator"
                ),
                clock=lambda: self.now[0],
            )
        )

    def append_one(self):
        if self.kind == "journal":
            return append_events(
                self.chain,
                1,
                start=self.chain.length(),
            )[0]
        return self.chain.append(
            receipt(
                self.chain.length()
            )
        )

    def plan(self):
        return self.operator.plan(
            self.retention,
            self.chain,
            operator_id="operator",
        )

    def certify(self, workflow_id):
        return self.operator.certify(
            workflow_id,
            self.retention,
            self.chain,
        )

    def authorize(
        self,
        workflow_id,
    ):
        return self.operator.authorize(
            workflow_id,
            self.retention,
            self.chain,
        )

    def prepare(
        self,
        workflow_id,
    ):
        return self.operator.prepare(
            workflow_id,
            self.retention,
            self.chain,
        )

    def execute(
        self,
        workflow_id,
        *,
        maintenance_epoch=None,
    ):
        return self.operator.execute(
            workflow_id,
            self.retention,
            self.chain,
            maintenance_epoch=maintenance_epoch,
        )

    def acquire_maintenance(
        self,
        *,
        operation=DurableMaintenanceOperation.COMPACTION,
        owner_id="operator",
    ):
        if self.maintenance is None:
            raise RuntimeError(
                "fixture maintenance is not enabled"
            )
        return self.maintenance.acquire(
            operation,
            owner_id=owner_id,
            resources=(
                DurableMaintenanceResource.from_chain(
                    self.chain_id,
                    self.chain,
                ),
            ),
        )

    def through_prepared(self):
        plan = self.plan()
        self.certify(
            plan.workflow_id
        )
        self.authorize(
            plan.workflow_id
        )
        prepared = self.prepare(
            plan.workflow_id
        )
        return plan, prepared

    def through_complete(self):
        plan, prepared = (
            self.through_prepared()
        )
        result = self.execute(
            plan.workflow_id
        )
        return (
            plan,
            prepared,
            result,
        )


@pytest.mark.parametrize(
    "kind",
    ["journal", "receipts"],
)
def test_plan_is_non_destructive(kind):
    fixture = OperatorFixture(
        kind=kind
    )
    before = fixture.chain.snapshot()
    plan = fixture.plan()
    workflow = plan.stored.workflow

    assert (
        workflow.phase
        is DurableCompactionWorkflowPhase.PLANNED
    )
    assert (
        not workflow
        .destructive_authority_issued
    )
    assert (
        not workflow
        .delete_manifest_frozen
    )
    assert (
        not plan
        .destructive_action_authorized
    )
    assert fixture.chain.snapshot() == before
    assert (
        fixture.chain
        .hot_floor()
        .sequence
        == 0
    )


@pytest.mark.parametrize(
    "kind",
    ["journal", "receipts"],
)
def test_plan_binds_head_cutoff_archive_and_floor(kind):
    fixture = OperatorFixture(
        kind=kind
    )
    plan = fixture.plan()
    workflow = plan.stored.workflow
    readiness = plan.readiness

    assert (
        workflow.chain_id
        == fixture.chain_id
    )
    assert workflow.operator_id == "operator"
    assert (
        workflow.retention_plan_digest
        == fixture.retention.digest
    )
    assert (
        workflow.readiness_digest
        == readiness.digest
    )
    assert (
        workflow.compaction_policy_digest
        == readiness.policy_digest
    )
    assert (
        workflow.current_sequence
        == fixture.chain.head().sequence
    )
    assert (
        workflow.current_root
        == fixture.chain.head().root_hash
    )
    assert (
        workflow.cutoff_sequence
        == fixture.retention
        .archive_through_sequence
    )
    assert (
        workflow.cutoff_root
        == fixture.retention
        .archive_through_root
    )
    assert (
        workflow.previous_floor_sequence
        == 0
    )
    assert (
        workflow.previous_floor_root
        == "0" * 64
    )
    assert workflow.archive_id
    assert (
        len(
            workflow
            .archive_manifest_digest
        )
        == 64
    )


@pytest.mark.parametrize(
    "kind",
    ["journal", "receipts"],
)
def test_plan_retry_is_revision_idempotent(kind):
    fixture = OperatorFixture(
        kind=kind
    )
    first = fixture.plan()
    second = fixture.plan()
    assert (
        second.workflow_id
        == first.workflow_id
    )
    assert (
        second.stored.revision
        == first.stored.revision
    )
    assert (
        second.stored.workflow
        == first.stored.workflow
    )


@pytest.mark.parametrize(
    "kind",
    ["journal", "receipts"],
)
def test_different_operator_gets_different_workflow_id(kind):
    fixture = OperatorFixture(
        kind=kind
    )
    first = fixture.plan()
    second = fixture.operator.plan(
        fixture.retention,
        fixture.chain,
        operator_id="other-operator",
    )
    assert (
        first.workflow_id
        != second.workflow_id
    )


@pytest.mark.parametrize(
    "kind",
    ["journal", "receipts"],
)
def test_certify_advances_only_non_destructive_phase(kind):
    fixture = OperatorFixture(
        kind=kind
    )
    plan = fixture.plan()
    certificate = fixture.certify(
        plan.workflow_id
    )
    stored = fixture.operator.current(
        plan.workflow_id
    )
    workflow = stored.workflow

    assert (
        workflow.phase
        is DurableCompactionWorkflowPhase.CERTIFIED
    )
    assert (
        workflow.certificate_id
        == certificate.certificate_id
    )
    assert (
        workflow.certificate_digest
        == certificate.certificate.digest
    )
    assert (
        not workflow
        .destructive_authority_issued
    )
    assert (
        not certificate
        .destructive_action_authorized
    )
    assert (
        fixture.chain
        .hot_floor()
        .sequence
        == 0
    )


@pytest.mark.parametrize(
    "kind",
    ["journal", "receipts"],
)
def test_certify_retry_reuses_certificate(kind):
    fixture = OperatorFixture(
        kind=kind
    )
    plan = fixture.plan()
    first = fixture.certify(
        plan.workflow_id
    )
    revision = (
        fixture.operator
        .current(
            plan.workflow_id
        )
        .revision
    )
    second = fixture.certify(
        plan.workflow_id
    )
    assert second == first
    assert (
        fixture.operator
        .current(
            plan.workflow_id
        )
        .revision
        == revision
    )


@pytest.mark.parametrize(
    "kind",
    ["journal", "receipts"],
)
def test_authorize_requires_certified_workflow(kind):
    fixture = OperatorFixture(
        kind=kind
    )
    plan = fixture.plan()
    with pytest.raises(
        DurableCompactionWorkflowError,
        match="certified",
    ):
        fixture.authorize(
            plan.workflow_id
        )


@pytest.mark.parametrize(
    "kind",
    ["journal", "receipts"],
)
def test_authorize_crosses_explicit_destructive_boundary(kind):
    fixture = OperatorFixture(
        kind=kind
    )
    plan = fixture.plan()
    fixture.certify(
        plan.workflow_id
    )
    authorization = fixture.authorize(
        plan.workflow_id
    )
    workflow = (
        fixture.operator
        .current(
            plan.workflow_id
        )
        .workflow
    )

    assert (
        workflow.phase
        is DurableCompactionWorkflowPhase.AUTHORIZED
    )
    assert (
        workflow.authorization_id
        == authorization.authorization_id
    )
    assert (
        workflow.authorization_digest
        == authorization.authorization.digest
    )
    assert (
        workflow
        .destructive_authority_issued
    )
    assert (
        authorization
        .destructive_action_authorized
    )
    assert (
        workflow.delete_count
        == workflow.cutoff_sequence
        - workflow.previous_floor_sequence
    )
    assert (
        fixture.chain
        .hot_floor()
        .sequence
        == 0
    )


@pytest.mark.parametrize(
    "kind",
    ["journal", "receipts"],
)
def test_authorize_retry_is_idempotent(kind):
    fixture = OperatorFixture(
        kind=kind
    )
    plan = fixture.plan()
    fixture.certify(
        plan.workflow_id
    )
    first = fixture.authorize(
        plan.workflow_id
    )
    revision = (
        fixture.operator
        .current(
            plan.workflow_id
        )
        .revision
    )
    second = fixture.authorize(
        plan.workflow_id
    )
    assert second == first
    assert (
        fixture.operator
        .current(
            plan.workflow_id
        )
        .revision
        == revision
    )


@pytest.mark.parametrize(
    "kind",
    ["journal", "receipts"],
)
def test_prepare_requires_authorization(kind):
    fixture = OperatorFixture(
        kind=kind
    )
    plan = fixture.plan()
    fixture.certify(
        plan.workflow_id
    )
    with pytest.raises(
        DurableCompactionWorkflowError,
        match="authorized",
    ):
        fixture.prepare(
            plan.workflow_id
        )


@pytest.mark.parametrize(
    "kind",
    ["journal", "receipts"],
)
def test_prepare_freezes_manifest_without_deleting(kind):
    fixture = OperatorFixture(
        kind=kind
    )
    before = fixture.chain.snapshot()
    plan = fixture.plan()
    fixture.certify(
        plan.workflow_id
    )
    fixture.authorize(
        plan.workflow_id
    )
    prepared = fixture.prepare(
        plan.workflow_id
    )
    workflow = (
        prepared.stored.workflow
    )

    assert isinstance(
        prepared,
        DurableCompactionPrepared,
    )
    assert (
        workflow.phase
        is DurableCompactionWorkflowPhase.PREPARED
    )
    assert (
        workflow.delete_manifest_frozen
    )
    assert (
        workflow.pruning_operation_id
        == prepared.operation.operation_id
    )
    assert (
        workflow.pruning_manifest_digest
        == prepared.manifest.digest
    )
    assert (
        prepared.operation.phase
        is DurablePruningPhase.PREPARED
    )
    assert (
        prepared.manifest.delete_count
        == workflow.delete_count
    )
    assert fixture.chain.snapshot() == before
    assert (
        fixture.chain
        .hot_floor()
        .sequence
        == 0
    )


@pytest.mark.parametrize(
    "kind",
    ["journal", "receipts"],
)
def test_prepare_retry_reuses_exact_manifest(kind):
    fixture = OperatorFixture(
        kind=kind
    )
    plan, first = (
        fixture.through_prepared()
    )
    revision = (
        first.stored.revision
    )
    second = fixture.prepare(
        plan.workflow_id
    )
    assert (
        second.manifest.digest
        == first.manifest.digest
    )
    assert (
        second.operation.operation_id
        == first.operation.operation_id
    )
    assert (
        second.stored.revision
        == revision
    )


@pytest.mark.parametrize(
    "kind",
    ["journal", "receipts"],
)
def test_execute_requires_prepared_manifest(kind):
    fixture = OperatorFixture(
        kind=kind
    )
    plan = fixture.plan()
    fixture.certify(
        plan.workflow_id
    )
    fixture.authorize(
        plan.workflow_id
    )
    with pytest.raises(
        DurableCompactionWorkflowError,
        match="prepared",
    ):
        fixture.execute(
            plan.workflow_id
        )


@pytest.mark.parametrize(
    "kind",
    ["journal", "receipts"],
)
def test_execute_completes_pruning_and_workflow(kind):
    fixture = OperatorFixture(
        kind=kind
    )
    plan, _ = fixture.through_prepared()
    executed = fixture.execute(
        plan.workflow_id
    )
    workflow = (
        executed.stored.workflow
    )

    assert isinstance(
        executed,
        DurableCompactionExecution,
    )
    assert executed.ok
    assert executed.result.ok
    assert workflow.complete
    assert (
        workflow.phase
        is DurableCompactionWorkflowPhase.COMPLETE
    )
    assert (
        workflow.pruning_phase
        == DurablePruningPhase.COMPLETE.value
    )
    assert (
        workflow.deleted_items
        == workflow.delete_count
    )
    assert (
        workflow.floor_id
        == executed.result.floor.floor_id
    )
    assert (
        fixture.chain
        .hot_floor()
        .sequence
        == workflow.cutoff_sequence
    )
    assert (
        fixture.chain
        .hot_floor()
        .root_hash
        == workflow.cutoff_root
    )
    assert (
        fixture.chain.snapshot()
        == fixture.later
    )
    assert fixture.chain.verify()


@pytest.mark.parametrize(
    "kind",
    ["journal", "receipts"],
)
def test_completed_history_remains_available_via_archive(kind):
    fixture = OperatorFixture(
        kind=kind
    )
    plan, _, result = (
        fixture.through_complete()
    )
    workflow = (
        result.stored.workflow
    )
    archive_backed = (
        ArchiveBackedHistoricalChain(
            fixture.chain_id,
            fixture.chain,
            fixture.archives,
        )
    )
    historical = (
        archive_backed.snapshot_at(
            workflow.cutoff_root
        )
    )
    assert len(historical) == (
        workflow.cutoff_sequence
    )
    assert (
        historical[-1].sequence
        == workflow.cutoff_sequence
    )
    assert archive_backed.verify()


@pytest.mark.parametrize(
    "kind",
    ["journal", "receipts"],
)
def test_resume_completed_workflow_is_idempotent(kind):
    fixture = OperatorFixture(
        kind=kind
    )
    plan, _, first = (
        fixture.through_complete()
    )
    revision = first.stored.revision
    second = fixture.operator.resume(
        plan.workflow_id,
        fixture.retention,
        fixture.chain,
    )
    assert second.ok
    assert (
        second.stored.revision
        == revision
    )
    assert (
        second.result.operation.operation_id
        == first.result.operation.operation_id
    )


@pytest.mark.parametrize(
    "kind",
    ["journal", "receipts"],
)
def test_fresh_operator_reads_persisted_workflow(kind):
    fixture = OperatorFixture(
        kind=kind
    )
    plan, prepared = (
        fixture.through_prepared()
    )
    fresh = DurableCompactionOperator(
        fixture.backend,
        fixture.compaction,
        fixture.certificate_store,
        fixture.authorization_store,
        fixture.executor,
        namespace=f"{kind}-operator",
        clock=lambda: fixture.now[0],
    )
    restored = fresh.current(
        plan.workflow_id
    )
    assert restored == prepared.stored
    report = fresh.inspect(
        plan.workflow_id,
        fixture.retention,
        fixture.chain,
    )
    assert report.current
    assert report.safe_to_execute


@pytest.mark.parametrize(
    "kind",
    ["journal", "receipts"],
)
def test_chain_growth_after_plan_stales_certification(kind):
    fixture = OperatorFixture(
        kind=kind
    )
    plan = fixture.plan()
    fixture.append_one()

    with pytest.raises(
        DurableCompactionWorkflowStale,
    ):
        fixture.certify(
            plan.workflow_id
        )
    stored = fixture.operator.current(
        plan.workflow_id
    )
    assert (
        stored.workflow.phase
        is DurableCompactionWorkflowPhase.PLANNED
    )


@pytest.mark.parametrize(
    "kind",
    ["journal", "receipts"],
)
def test_chain_growth_after_certificate_stales_authorization(kind):
    fixture = OperatorFixture(
        kind=kind
    )
    plan = fixture.plan()
    fixture.certify(
        plan.workflow_id
    )
    fixture.append_one()

    with pytest.raises(
        DurableCompactionWorkflowStale,
    ):
        fixture.authorize(
            plan.workflow_id
        )
    assert (
        fixture.operator
        .current(
            plan.workflow_id
        )
        .workflow.phase
        is DurableCompactionWorkflowPhase.CERTIFIED
    )


@pytest.mark.parametrize(
    "kind",
    ["journal", "receipts"],
)
def test_chain_growth_after_prepare_blocks_execution(kind):
    fixture = OperatorFixture(
        kind=kind
    )
    plan, _ = fixture.through_prepared()
    fixture.append_one()

    with pytest.raises(Exception):
        fixture.execute(
            plan.workflow_id
        )
    stored = fixture.operator.current(
        plan.workflow_id
    )
    assert (
        stored.workflow.phase
        in {
            DurableCompactionWorkflowPhase.EXECUTING,
            DurableCompactionWorkflowPhase.MANUAL_REVIEW,
        }
    )
    assert (
        fixture.chain
        .hot_floor()
        .sequence
        == 0
    )


@pytest.mark.parametrize(
    "kind",
    ["journal", "receipts"],
)
def test_changed_retention_plan_is_rejected(kind):
    fixture = OperatorFixture(
        kind=kind
    )
    plan = fixture.plan()
    protected = (
        fixture.first[1].event_hash
        if kind == "journal"
        else fixture.first[1].receipt_hash
    )
    changed = (
        fixture.retention_planner.plan(
            fixture.chain_id,
            fixture.chain,
            protected_roots=(
                protected,
            ),
        )
    )
    assert (
        changed.digest
        != fixture.retention.digest
    )

    with pytest.raises(
        DurableCompactionWorkflowStale,
        match="retention",
    ):
        fixture.operator.certify(
            plan.workflow_id,
            changed,
            fixture.chain,
        )


@pytest.mark.parametrize(
    "kind",
    ["journal", "receipts"],
)
def test_archive_tamper_stales_workflow_before_certificate(kind):
    fixture = OperatorFixture(
        kind=kind
    )
    plan = fixture.plan()
    root = (
        fixture.retention
        .archive_through_root
    )
    key = fixture.archives._node_key(
        fixture.chain_id,
        root,
    )
    record = fixture.backend.get(
        fixture.archives.namespace,
        key,
    )
    raw = dict(record.value)
    payload = dict(
        raw["payload"]
    )
    if kind == "journal":
        payload["summary"] = "tampered"
    else:
        payload["stdout_bytes"] = 999
    raw["payload"] = payload
    fixture.backend.compare_and_swap(
        fixture.archives.namespace,
        key,
        expected_revision=record.revision,
        value=raw,
    )

    with pytest.raises(Exception):
        fixture.certify(
            plan.workflow_id
        )


@pytest.mark.parametrize(
    "kind",
    ["journal", "receipts"],
)
def test_expired_certificate_can_be_renewed_before_authorization(kind):
    fixture = OperatorFixture(
        kind=kind
    )
    plan = fixture.plan()
    first = fixture.certify(
        plan.workflow_id
    )
    fixture.now[0] = (
        first.certificate.expires_at
        + 1.0
    )
    second = fixture.certify(
        plan.workflow_id
    )
    assert (
        second.certificate_id
        != first.certificate_id
    )
    stored = fixture.operator.current(
        plan.workflow_id
    )
    assert (
        stored.workflow.certificate_id
        == second.certificate_id
    )
    authorization = fixture.authorize(
        plan.workflow_id
    )
    assert (
        authorization.authorization
        .certificate_id
        == second.certificate_id
    )


@pytest.mark.parametrize(
    "kind",
    ["journal", "receipts"],
)
def test_expired_authorization_can_be_renewed_before_prepare(kind):
    fixture = OperatorFixture(
        kind=kind
    )
    plan = fixture.plan()
    fixture.certify(
        plan.workflow_id
    )
    first = fixture.authorize(
        plan.workflow_id
    )
    fixture.now[0] = (
        first.authorization.expires_at
        + 1.0
    )
    second = fixture.authorize(
        plan.workflow_id
    )
    assert (
        second.authorization_id
        != first.authorization_id
    )
    assert (
        fixture.operator
        .current(
            plan.workflow_id
        )
        .workflow.authorization_id
        == second.authorization_id
    )
    prepared = fixture.prepare(
        plan.workflow_id
    )
    assert (
        prepared.authorization
        .authorization_id
        == second.authorization_id
    )


@pytest.mark.parametrize(
    "kind",
    ["journal", "receipts"],
)
def test_expired_authorization_blocks_pre_floor_execute(kind):
    fixture = OperatorFixture(
        kind=kind
    )
    plan, prepared = (
        fixture.through_prepared()
    )
    fixture.now[0] = (
        prepared.authorization
        .authorization.expires_at
        + 1.0
    )

    with pytest.raises(Exception):
        fixture.execute(
            plan.workflow_id
        )
    assert (
        fixture.chain
        .hot_floor()
        .sequence
        == 0
    )


@pytest.mark.parametrize(
    "kind",
    ["journal", "receipts"],
)
def test_crash_during_deletion_is_resumable_after_floor_commit(kind):
    backend = FailDeleteOnceBackend()
    fixture = OperatorFixture(
        kind=kind,
        backend=backend,
    )
    plan, _ = fixture.through_prepared()
    backend.fail_enabled = True

    with pytest.raises(
        RuntimeError,
        match="synthetic operator pruning crash",
    ):
        fixture.execute(
            plan.workflow_id
        )

    stored = fixture.operator.current(
        plan.workflow_id
    )
    assert (
        stored.workflow.phase
        is DurableCompactionWorkflowPhase.EXECUTING
    )
    assert stored.workflow.error_count == 1
    assert stored.workflow.resumable
    assert (
        fixture.chain
        .hot_floor()
        .sequence
        == stored.workflow.cutoff_sequence
    )

    # Expiry after floor commit does not revoke authority to finish the exact
    # already-fenced deletion manifest.
    fixture.now[0] += 1000.0
    backend.fail_enabled = False
    result = fixture.operator.resume(
        plan.workflow_id,
        fixture.retention,
        fixture.chain,
    )
    assert result.ok
    assert result.stored.workflow.complete
    assert (
        fixture.chain.snapshot()
        == fixture.later
    )


@pytest.mark.parametrize(
    "kind",
    ["journal", "receipts"],
)
def test_fresh_operator_resumes_crashed_deletion(kind):
    backend = FailDeleteOnceBackend()
    fixture = OperatorFixture(
        kind=kind,
        backend=backend,
    )
    plan, _ = fixture.through_prepared()
    backend.fail_enabled = True
    with pytest.raises(RuntimeError):
        fixture.execute(
            plan.workflow_id
        )
    backend.fail_enabled = False

    fresh_executor = DurablePruningExecutor(
        fixture.backend,
        fixture.authorization_store,
        fixture.floor_store,
        namespace=f"{kind}-pruning",
        max_items=100,
        clock=lambda: fixture.now[0],
    )
    fresh = DurableCompactionOperator(
        fixture.backend,
        fixture.compaction,
        fixture.certificate_store,
        fixture.authorization_store,
        fresh_executor,
        namespace=f"{kind}-operator",
        clock=lambda: fixture.now[0],
    )
    result = fresh.resume(
        plan.workflow_id,
        fixture.retention,
        fixture.chain,
    )
    assert result.ok
    assert result.stored.workflow.complete


@pytest.mark.parametrize(
    "kind",
    ["journal", "receipts"],
)
def test_inspect_reports_phase_capabilities(kind):
    fixture = OperatorFixture(
        kind=kind
    )
    plan = fixture.plan()
    report = fixture.operator.inspect(
        plan.workflow_id,
        fixture.retention,
        fixture.chain,
    )
    assert report.current
    assert not report.safe_to_execute
    assert not report.safe_to_resume
    assert report.reasons == ()

    fixture.certify(
        plan.workflow_id
    )
    fixture.authorize(
        plan.workflow_id
    )
    fixture.prepare(
        plan.workflow_id
    )
    report = fixture.operator.inspect(
        plan.workflow_id,
        fixture.retention,
        fixture.chain,
    )
    assert report.current
    assert report.safe_to_execute
    assert not report.safe_to_resume


@pytest.mark.parametrize(
    "kind",
    ["journal", "receipts"],
)
def test_inspect_detects_stale_head(kind):
    fixture = OperatorFixture(
        kind=kind
    )
    plan = fixture.plan()
    fixture.append_one()
    report = fixture.operator.inspect(
        plan.workflow_id,
        fixture.retention,
        fixture.chain,
    )
    assert not report.current
    assert not report.live_head_matches
    assert any(
        "live head differs" in reason
        for reason in report.reasons
    )


@pytest.mark.parametrize(
    "kind",
    ["journal", "receipts"],
)
def test_require_current_rejects_stale_workflow(kind):
    fixture = OperatorFixture(
        kind=kind
    )
    plan = fixture.plan()
    fixture.append_one()
    with pytest.raises(
        DurableCompactionWorkflowStale,
    ):
        fixture.operator.require_current(
            plan.workflow_id,
            fixture.retention,
            fixture.chain,
        )


@pytest.mark.parametrize(
    "kind",
    ["journal", "receipts"],
)
def test_complete_workflow_serializes_full_authority_chain(kind):
    fixture = OperatorFixture(
        kind=kind
    )
    _, _, result = (
        fixture.through_complete()
    )
    data = result.to_dict()
    workflow = data["stored"][
        "workflow"
    ]
    assert data["ok"] is True
    assert workflow["phase"] == "complete"
    assert (
        workflow[
            "destructive_authority_issued"
        ]
        is True
    )
    assert (
        workflow[
            "delete_manifest_frozen"
        ]
        is True
    )
    assert workflow["complete"] is True
    assert (
        workflow["deleted_items"]
        == workflow["delete_count"]
    )
    assert (
        len(workflow["binding_digest"])
        == 64
    )
    assert len(workflow["digest"]) == 64


@pytest.mark.parametrize(
    "kind",
    ["journal", "receipts"],
)
def test_workflow_binding_digest_is_stable_across_phases(kind):
    fixture = OperatorFixture(
        kind=kind
    )
    plan = fixture.plan()
    initial = (
        plan.stored.workflow
        .binding_digest
    )
    fixture.certify(
        plan.workflow_id
    )
    assert (
        fixture.operator
        .current(plan.workflow_id)
        .workflow.binding_digest
        == initial
    )
    fixture.authorize(
        plan.workflow_id
    )
    fixture.prepare(
        plan.workflow_id
    )
    result = fixture.execute(
        plan.workflow_id
    )
    assert (
        result.stored.workflow
        .binding_digest
        == initial
    )


@pytest.mark.parametrize(
    "kind",
    ["journal", "receipts"],
)
def test_workflow_revision_advances_monotonically(kind):
    fixture = OperatorFixture(
        kind=kind
    )
    plan = fixture.plan()
    revisions = [
        plan.stored.revision
    ]
    fixture.certify(
        plan.workflow_id
    )
    revisions.append(
        fixture.operator
        .current(plan.workflow_id)
        .revision
    )
    fixture.authorize(
        plan.workflow_id
    )
    revisions.append(
        fixture.operator
        .current(plan.workflow_id)
        .revision
    )
    fixture.prepare(
        plan.workflow_id
    )
    revisions.append(
        fixture.operator
        .current(plan.workflow_id)
        .revision
    )
    fixture.execute(
        plan.workflow_id
    )
    revisions.append(
        fixture.operator
        .current(plan.workflow_id)
        .revision
    )
    assert revisions == sorted(
        revisions
    )
    assert len(set(revisions)) == 5


def test_missing_workflow_is_rejected():
    fixture = OperatorFixture()
    with pytest.raises(
        DurableCompactionWorkflowError,
        match="missing",
    ):
        fixture.operator.certify(
            fp("missing"),
            fixture.retention,
            fixture.chain,
        )


def test_current_missing_workflow_returns_none():
    fixture = OperatorFixture()
    assert (
        fixture.operator.current(
            fp("missing")
        )
        is None
    )


def test_operator_namespace_validation():
    fixture = OperatorFixture()
    with pytest.raises(
        ValueError,
        match="namespace",
    ):
        DurableCompactionOperator(
            fixture.backend,
            fixture.compaction,
            fixture.certificate_store,
            fixture.authorization_store,
            fixture.executor,
            namespace="",
        )


@pytest.mark.parametrize(
    "retries",
    [0, 129, True],
)
def test_operator_retry_bound_validation(retries):
    fixture = OperatorFixture()
    with pytest.raises(
        ValueError,
        match="max_cas_retries",
    ):
        DurableCompactionOperator(
            fixture.backend,
            fixture.compaction,
            fixture.certificate_store,
            fixture.authorization_store,
            fixture.executor,
            max_cas_retries=retries,
        )


def test_operator_clock_validation():
    fixture = OperatorFixture()
    operator = DurableCompactionOperator(
        fixture.backend,
        fixture.compaction,
        fixture.certificate_store,
        fixture.authorization_store,
        fixture.executor,
        namespace="bad-clock-operator",
        clock=lambda: float("nan"),
    )
    with pytest.raises(
        DurableCompactionWorkflowError,
        match="clock",
    ):
        operator.plan(
            fixture.retention,
            fixture.chain,
            operator_id="operator",
        )


def test_operator_rejects_mismatched_certificate_store():
    fixture = OperatorFixture()
    other_planner = DurableCompactionPlanner(
        fixture.archives,
        DurableCompactionPolicy(
            minimum_live_tail=2,
            maximum_candidate_nodes=20,
        ),
    )
    other_store = (
        DurableCompactionCertificateStore(
            fixture.backend,
            signer(
                "other-certificate",
                b"z",
            ),
            other_planner,
            namespace="other-certificates",
        )
    )
    with pytest.raises(
        ValueError,
        match="different compaction planner",
    ):
        DurableCompactionOperator(
            fixture.backend,
            fixture.compaction,
            other_store,
            fixture.authorization_store,
            fixture.executor,
        )


def test_operator_rejects_mismatched_authorization_store():
    fixture = OperatorFixture()
    other_authorizations = (
        DurablePruningAuthorizationStore(
            fixture.backend,
            signer(
                "other-auth",
                b"z",
            ),
            fixture.certificate_store,
            namespace="other-auths",
        )
    )
    other_certificates = (
        DurableCompactionCertificateStore(
            fixture.backend,
            signer(
                "other-cert",
                b"y",
            ),
            fixture.compaction,
            namespace="other-certs",
        )
    )
    with pytest.raises(
        ValueError,
        match="different certificate store",
    ):
        DurableCompactionOperator(
            fixture.backend,
            fixture.compaction,
            other_certificates,
            other_authorizations,
            fixture.executor,
        )


def test_operator_rejects_mismatched_pruning_executor():
    fixture = OperatorFixture()
    other_authorizations = (
        DurablePruningAuthorizationStore(
            fixture.backend,
            signer(
                "other-auth",
                b"z",
            ),
            fixture.certificate_store,
            namespace="other-auths",
        )
    )
    other_executor = DurablePruningExecutor(
        fixture.backend,
        other_authorizations,
        fixture.floor_store,
        namespace="other-pruning",
    )
    with pytest.raises(
        ValueError,
        match="different authorization store",
    ):
        DurableCompactionOperator(
            fixture.backend,
            fixture.compaction,
            fixture.certificate_store,
            fixture.authorization_store,
            other_executor,
        )


def test_wrong_backend_workflow_value_type_is_rejected():
    fixture = OperatorFixture()
    workflow_id = fp("bad-workflow")
    fixture.backend.put_if_absent(
        fixture.operator.namespace,
        fixture.operator._key(
            workflow_id
        ),
        {"bad": True},
    )
    with pytest.raises(
        DurableCompactionWorkflowError,
        match="value type",
    ):
        fixture.operator.current(
            workflow_id
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema_version", 2),
        ("workflow_id", "bad"),
        ("chain_id", ""),
        ("operator_id", ""),
        ("retention_plan_digest", "bad"),
        ("readiness_digest", "bad"),
        ("compaction_policy_digest", "bad"),
        ("current_sequence", -1),
        ("cutoff_sequence", 0),
        ("previous_floor_sequence", -1),
        ("archive_id", ""),
        ("created_at", -1.0),
        ("updated_at", -1.0),
    ],
)
def test_workflow_validation(field, value):
    values = dict(
        schema_version=1,
        workflow_id=fp("workflow"),
        chain_id="journal",
        operator_id="operator",
        phase=(
            DurableCompactionWorkflowPhase
            .PLANNED
        ),
        retention_plan_digest=fp(
            "retention"
        ),
        readiness_digest=fp(
            "readiness"
        ),
        compaction_policy_digest=fp(
            "policy"
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
        created_at=1.0,
        updated_at=1.0,
    )
    values[field] = value
    with pytest.raises(
        (ValueError, TypeError),
    ):
        DurableCompactionWorkflow(
            **values
        )


def test_certified_workflow_requires_certificate():
    with pytest.raises(
        ValueError,
        match="certificate",
    ):
        DurableCompactionWorkflow(
            1,
            fp("workflow"),
            "journal",
            "operator",
            DurableCompactionWorkflowPhase.CERTIFIED,
            fp("retention"),
            fp("readiness"),
            fp("policy"),
            8,
            fp("head"),
            6,
            fp("cutoff"),
            0,
            "0" * 64,
            "archive",
            fp("archive"),
            created_at=1.0,
            updated_at=1.0,
        )


def test_authorized_workflow_requires_authorization():
    with pytest.raises(
        ValueError,
        match="authority",
    ):
        DurableCompactionWorkflow(
            1,
            fp("workflow"),
            "journal",
            "operator",
            DurableCompactionWorkflowPhase.AUTHORIZED,
            fp("retention"),
            fp("readiness"),
            fp("policy"),
            8,
            fp("head"),
            6,
            fp("cutoff"),
            0,
            "0" * 64,
            "archive",
            fp("archive"),
            certificate_id=fp("cert"),
            certificate_digest=fp(
                "cert-digest"
            ),
            created_at=1.0,
            updated_at=1.0,
        )


def test_complete_workflow_requires_complete_pruning_result():
    with pytest.raises(
        ValueError,
        match="completed pruning",
    ):
        DurableCompactionWorkflow(
            1,
            fp("workflow"),
            "journal",
            "operator",
            DurableCompactionWorkflowPhase.COMPLETE,
            fp("retention"),
            fp("readiness"),
            fp("policy"),
            8,
            fp("head"),
            6,
            fp("cutoff"),
            0,
            "0" * 64,
            "archive",
            fp("archive"),
            certificate_id=fp("cert"),
            certificate_digest=fp(
                "cert-digest"
            ),
            authorization_id=fp("auth"),
            authorization_digest=fp(
                "auth-digest"
            ),
            pruning_operation_id=fp(
                "operation"
            ),
            pruning_manifest_digest=fp(
                "manifest"
            ),
            pruning_phase=(
                DurablePruningPhase
                .PREPARED.value
            ),
            delete_count=6,
            deleted_items=6,
            floor_id=fp("floor"),
            created_at=1.0,
            updated_at=1.0,
        )


def test_stored_workflow_revision_validation():
    workflow = DurableCompactionWorkflow(
        1,
        fp("workflow"),
        "journal",
        "operator",
        DurableCompactionWorkflowPhase.PLANNED,
        fp("retention"),
        fp("readiness"),
        fp("policy"),
        8,
        fp("head"),
        6,
        fp("cutoff"),
        0,
        "0" * 64,
        "archive",
        fp("archive"),
        created_at=1.0,
        updated_at=1.0,
    )
    with pytest.raises(ValueError):
        StoredDurableCompactionWorkflow(
            0,
            workflow,
        )


def test_workflow_error_fields_are_paired():
    base = dict(
        schema_version=1,
        workflow_id=fp("workflow"),
        chain_id="journal",
        operator_id="operator",
        phase=(
            DurableCompactionWorkflowPhase
            .PLANNED
        ),
        retention_plan_digest=fp(
            "retention"
        ),
        readiness_digest=fp(
            "readiness"
        ),
        compaction_policy_digest=fp(
            "policy"
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
        created_at=1.0,
        updated_at=1.0,
    )
    with pytest.raises(
        ValueError,
        match="requires last_error",
    ):
        DurableCompactionWorkflow(
            **base,
            error_count=1,
            last_error_at=1.0,
        )
    with pytest.raises(
        ValueError,
        match="require error_count",
    ):
        DurableCompactionWorkflow(
            **base,
            last_error="error",
            last_error_at=1.0,
        )


class ConflictOnceBackend(
    InMemoryFencedStore
):
    def __init__(self):
        super().__init__()
        self.workflow_conflicted = False

    def compare_and_swap(
        self,
        namespace,
        key,
        *,
        expected_revision,
        value,
    ):
        if (
            "operator" in namespace
            and not self.workflow_conflicted
            and key.startswith("workflow:")
        ):
            self.workflow_conflicted = True
            raise DistributedStateConflict(
                "synthetic workflow race"
            )
        return super().compare_and_swap(
            namespace,
            key,
            expected_revision=expected_revision,
            value=value,
        )


@pytest.mark.parametrize(
    "kind",
    ["journal", "receipts"],
)
def test_workflow_transition_retries_cas_conflict(kind):
    backend = ConflictOnceBackend()
    fixture = OperatorFixture(
        kind=kind,
        backend=backend,
    )
    plan = fixture.plan()
    certificate = fixture.certify(
        plan.workflow_id
    )
    assert certificate.certificate_id
    assert backend.workflow_conflicted
    assert (
        fixture.operator
        .current(plan.workflow_id)
        .workflow.phase
        is DurableCompactionWorkflowPhase.CERTIFIED
    )


def lineage_auditor(fixture):
    return DurableCompactionLineageAuditor(
        fixture.operator
    )


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_compaction_lineage_complete_workflow_verifies(kind):
    fixture = OperatorFixture(kind=kind)
    plan, _, _ = fixture.through_complete()
    report = lineage_auditor(
        fixture
    ).require_verified(
        plan.workflow_id
    )
    assert report.ok
    assert report.status is CompactionLineageStatus.VERIFIED
    assert report.findings == ()
    assert report.certificate.verified
    assert report.authorization.verified
    assert report.archive.verified
    assert report.pruning_manifest.verified
    assert report.pruning_operation.verified
    assert report.hot_floor.verified


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_compaction_lineage_planned_workflow_is_clean_incomplete(kind):
    fixture = OperatorFixture(kind=kind)
    plan = fixture.plan()
    report = lineage_auditor(
        fixture
    ).inspect(
        plan.workflow_id
    )
    assert report.status is CompactionLineageStatus.INCOMPLETE
    assert report.safe_to_resume
    assert report.archive.verified
    assert not report.certificate.expected
    assert not report.authorization.expected
    assert not report.pruning_manifest.expected
    assert not report.hot_floor.expected
    assert report.findings == ()


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_compaction_lineage_certified_workflow_is_clean_incomplete(kind):
    fixture = OperatorFixture(kind=kind)
    plan = fixture.plan()
    fixture.certify(plan.workflow_id)
    report = lineage_auditor(
        fixture
    ).inspect(plan.workflow_id)
    assert report.status is CompactionLineageStatus.INCOMPLETE
    assert report.certificate.verified
    assert not report.authorization.expected
    assert report.archive.verified


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_compaction_lineage_authorized_workflow_is_clean_incomplete(kind):
    fixture = OperatorFixture(kind=kind)
    plan = fixture.plan()
    fixture.certify(plan.workflow_id)
    fixture.authorize(plan.workflow_id)
    report = lineage_auditor(
        fixture
    ).inspect(plan.workflow_id)
    assert report.status is CompactionLineageStatus.INCOMPLETE
    assert report.certificate.verified
    assert report.authorization.verified
    assert not report.pruning_manifest.expected


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_compaction_lineage_prepared_workflow_is_clean_incomplete(kind):
    fixture = OperatorFixture(kind=kind)
    plan, _ = fixture.through_prepared()
    report = lineage_auditor(
        fixture
    ).inspect(plan.workflow_id)
    assert report.status is CompactionLineageStatus.INCOMPLETE
    assert report.pruning_manifest.verified
    assert report.pruning_operation.verified
    assert not report.hot_floor.expected


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_compaction_lineage_survives_authority_expiry_after_completion(kind):
    fixture = OperatorFixture(kind=kind)
    plan, _, _ = fixture.through_complete()
    fixture.now[0] += 10_000.0
    report = lineage_auditor(
        fixture
    ).require_verified(plan.workflow_id)
    assert report.ok
    assert report.certificate.verified
    assert report.authorization.verified


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_compaction_lineage_survives_later_hot_floor(kind):
    fixture = OperatorFixture(kind=kind)
    plan, _, _ = fixture.through_complete()
    completed = fixture.operator.current(
        plan.workflow_id
    ).workflow
    first_floor = fixture.floor_store.floor_at(
        fixture.chain_id,
        completed.cutoff_sequence,
    )
    assert first_floor is not None

    fixture.now[0] += 1.0
    later = fixture.floor_store.advance(
        chain_id=fixture.chain_id,
        sequence=completed.cutoff_sequence + 1,
        root_hash=fp("later-floor-root"),
        archive_id="later-archive",
        archive_manifest_digest=fp(
            "later-archive-manifest"
        ),
        compaction_certificate_id=fp(
            "later-certificate"
        ),
        pruning_authorization_id=fp(
            "later-authorization"
        ),
        operation_id=fp(
            "later-operation"
        ),
        fencing_token=(
            first_floor.floor.fencing_token + 1
        ),
        expected_previous_sequence=(
            completed.cutoff_sequence
        ),
        expected_previous_root=(
            completed.cutoff_root
        ),
    )
    assert (
        fixture.floor_store.current(
            fixture.chain_id
        )
        == later
    )
    report = lineage_auditor(
        fixture
    ).require_verified(
        plan.workflow_id
    )
    assert report.ok
    assert report.hot_floor.artifact_id == completed.floor_id


def test_compaction_lineage_missing_workflow_is_incomplete():
    fixture = OperatorFixture()
    report = lineage_auditor(
        fixture
    ).inspect(
        fp("missing-workflow")
    )
    assert report.status is CompactionLineageStatus.INCOMPLETE
    assert report.findings[0].code == "workflow.missing"


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_compaction_lineage_missing_certificate_requires_manual_review(kind):
    fixture = OperatorFixture(kind=kind)
    plan = fixture.plan()
    fixture.certify(plan.workflow_id)
    workflow = fixture.operator.current(
        plan.workflow_id
    ).workflow
    key = fixture.certificate_store._certificate_key(
        workflow.certificate_id
    )
    record = fixture.backend.get(
        fixture.certificate_store.namespace,
        key,
    )
    fixture.backend.delete(
        fixture.certificate_store.namespace,
        key,
        expected_revision=record.revision,
    )
    report = lineage_auditor(
        fixture
    ).inspect(plan.workflow_id)
    assert report.status is CompactionLineageStatus.MANUAL_REVIEW
    assert any(
        item.code == "certificate.missing"
        for item in report.findings
    )


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_compaction_lineage_missing_authorization_requires_manual_review(kind):
    fixture = OperatorFixture(kind=kind)
    plan = fixture.plan()
    fixture.certify(plan.workflow_id)
    fixture.authorize(plan.workflow_id)
    workflow = fixture.operator.current(
        plan.workflow_id
    ).workflow
    key = fixture.authorization_store._authorization_key(
        workflow.authorization_id
    )
    record = fixture.backend.get(
        fixture.authorization_store.namespace,
        key,
    )
    fixture.backend.delete(
        fixture.authorization_store.namespace,
        key,
        expected_revision=record.revision,
    )
    report = lineage_auditor(
        fixture
    ).inspect(plan.workflow_id)
    assert report.status is CompactionLineageStatus.MANUAL_REVIEW
    assert any(
        item.code == "authorization.missing"
        for item in report.findings
    )


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_compaction_lineage_missing_archive_requires_manual_review(kind):
    fixture = OperatorFixture(kind=kind)
    plan = fixture.plan()
    workflow = fixture.operator.current(
        plan.workflow_id
    ).workflow
    key = fixture.archives._archive_key(
        workflow.archive_id
    )
    record = fixture.backend.get(
        fixture.archives.namespace,
        key,
    )
    fixture.backend.delete(
        fixture.archives.namespace,
        key,
        expected_revision=record.revision,
    )
    report = lineage_auditor(
        fixture
    ).inspect(plan.workflow_id)
    assert report.status is CompactionLineageStatus.MANUAL_REVIEW
    assert any(
        item.code == "archive.missing"
        for item in report.findings
    )


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_compaction_lineage_missing_manifest_requires_manual_review(kind):
    fixture = OperatorFixture(kind=kind)
    plan, prepared = fixture.through_prepared()
    operation_id = (
        prepared.operation.operation_id
    )
    key = fixture.executor._manifest_key(
        operation_id
    )
    record = fixture.backend.get(
        fixture.executor.namespace,
        key,
    )
    fixture.backend.delete(
        fixture.executor.namespace,
        key,
        expected_revision=record.revision,
    )
    report = lineage_auditor(
        fixture
    ).inspect(plan.workflow_id)
    assert report.status is CompactionLineageStatus.MANUAL_REVIEW
    assert any(
        item.code == "manifest.missing"
        for item in report.findings
    )


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_compaction_lineage_missing_operation_requires_manual_review(kind):
    fixture = OperatorFixture(kind=kind)
    plan, prepared = fixture.through_prepared()
    operation_id = (
        prepared.operation.operation_id
    )
    key = fixture.executor._operation_key(
        operation_id
    )
    record = fixture.backend.get(
        fixture.executor.namespace,
        key,
    )
    fixture.backend.delete(
        fixture.executor.namespace,
        key,
        expected_revision=record.revision,
    )
    report = lineage_auditor(
        fixture
    ).inspect(plan.workflow_id)
    assert report.status is CompactionLineageStatus.MANUAL_REVIEW
    assert any(
        item.code == "operation.missing"
        for item in report.findings
    )


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_compaction_lineage_missing_historical_floor_requires_manual_review(kind):
    fixture = OperatorFixture(kind=kind)
    plan, _, _ = fixture.through_complete()
    workflow = fixture.operator.current(
        plan.workflow_id
    ).workflow
    floor = fixture.floor_store.floor_at(
        fixture.chain_id,
        workflow.cutoff_sequence,
    )
    fixture.now[0] += 1.0
    fixture.floor_store.advance(
        chain_id=fixture.chain_id,
        sequence=workflow.cutoff_sequence + 1,
        root_hash=fp("later-root"),
        archive_id="later-archive",
        archive_manifest_digest=fp("later-archive"),
        compaction_certificate_id=fp("later-certificate"),
        pruning_authorization_id=fp("later-authorization"),
        operation_id=fp("later-operation"),
        fencing_token=floor.floor.fencing_token + 1,
        expected_previous_sequence=workflow.cutoff_sequence,
        expected_previous_root=workflow.cutoff_root,
    )
    history_key = fixture.floor_store._history_key(
        workflow.floor_id
    )
    index_key = fixture.floor_store._sequence_key(
        fixture.chain_id,
        workflow.cutoff_sequence,
    )
    history_record = fixture.backend.get(
        fixture.floor_store.namespace,
        history_key,
    )
    index_record = fixture.backend.get(
        fixture.floor_store.namespace,
        index_key,
    )
    fixture.backend.delete(
        fixture.floor_store.namespace,
        history_key,
        expected_revision=history_record.revision,
    )
    fixture.backend.delete(
        fixture.floor_store.namespace,
        index_key,
        expected_revision=index_record.revision,
    )
    report = lineage_auditor(
        fixture
    ).inspect(plan.workflow_id)
    assert report.status is CompactionLineageStatus.MANUAL_REVIEW
    assert any(
        item.code == "floor.missing"
        for item in report.findings
    )


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_compaction_lineage_workflow_certificate_digest_substitution_is_detected(kind):
    fixture = OperatorFixture(kind=kind)
    plan = fixture.plan()
    fixture.certify(plan.workflow_id)
    stored = fixture.operator.current(
        plan.workflow_id
    )
    key = fixture.operator._key(
        plan.workflow_id
    )
    record = fixture.backend.get(
        fixture.operator.namespace,
        key,
    )
    substituted = replace(
        stored.workflow,
        certificate_digest=fp(
            "substituted-certificate"
        ),
    )
    fixture.backend.compare_and_swap(
        fixture.operator.namespace,
        key,
        expected_revision=record.revision,
        value=substituted,
    )
    report = lineage_auditor(
        fixture
    ).inspect(plan.workflow_id)
    assert report.status is CompactionLineageStatus.MANUAL_REVIEW
    assert any(
        item.code == "certificate.digest"
        for item in report.findings
    )


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_compaction_lineage_workflow_authorization_digest_substitution_is_detected(kind):
    fixture = OperatorFixture(kind=kind)
    plan = fixture.plan()
    fixture.certify(plan.workflow_id)
    fixture.authorize(plan.workflow_id)
    stored = fixture.operator.current(
        plan.workflow_id
    )
    key = fixture.operator._key(
        plan.workflow_id
    )
    record = fixture.backend.get(
        fixture.operator.namespace,
        key,
    )
    substituted = replace(
        stored.workflow,
        authorization_digest=fp(
            "substituted-authorization"
        ),
    )
    fixture.backend.compare_and_swap(
        fixture.operator.namespace,
        key,
        expected_revision=record.revision,
        value=substituted,
    )
    report = lineage_auditor(
        fixture
    ).inspect(plan.workflow_id)
    assert report.status is CompactionLineageStatus.MANUAL_REVIEW
    assert any(
        item.code == "authorization.digest"
        for item in report.findings
    )


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_compaction_lineage_workflow_floor_id_substitution_is_detected(kind):
    fixture = OperatorFixture(kind=kind)
    plan, _, _ = fixture.through_complete()
    stored = fixture.operator.current(
        plan.workflow_id
    )
    key = fixture.operator._key(
        plan.workflow_id
    )
    record = fixture.backend.get(
        fixture.operator.namespace,
        key,
    )
    substituted = replace(
        stored.workflow,
        floor_id=fp("substituted-floor"),
    )
    fixture.backend.compare_and_swap(
        fixture.operator.namespace,
        key,
        expected_revision=record.revision,
        value=substituted,
    )
    report = lineage_auditor(
        fixture
    ).inspect(plan.workflow_id)
    assert report.status is CompactionLineageStatus.MANUAL_REVIEW
    assert any(
        item.code == "floor.id"
        for item in report.findings
    )


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_compaction_lineage_operation_phase_substitution_is_detected(kind):
    fixture = OperatorFixture(kind=kind)
    plan, _, _ = fixture.through_complete()
    workflow = fixture.operator.current(
        plan.workflow_id
    ).workflow
    key = fixture.executor._operation_key(
        workflow.pruning_operation_id
    )
    record = fixture.backend.get(
        fixture.executor.namespace,
        key,
    )
    payload = dict(record.value)
    payload["phase"] = DurablePruningPhase.EXECUTING.value
    fixture.backend.compare_and_swap(
        fixture.executor.namespace,
        key,
        expected_revision=record.revision,
        value=payload,
    )
    report = lineage_auditor(
        fixture
    ).inspect(plan.workflow_id)
    assert report.status is CompactionLineageStatus.MANUAL_REVIEW
    assert any(
        item.code == "operation.phase"
        for item in report.findings
    )


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_compaction_lineage_floor_sequence_index_substitution_is_detected(kind):
    fixture = OperatorFixture(kind=kind)
    plan, _, _ = fixture.through_complete()
    workflow = fixture.operator.current(
        plan.workflow_id
    ).workflow
    key = fixture.floor_store._sequence_key(
        fixture.chain_id,
        workflow.cutoff_sequence,
    )
    record = fixture.backend.get(
        fixture.floor_store.namespace,
        key,
    )
    payload = dict(record.value)
    payload["root_hash"] = fp("wrong-root")
    fixture.backend.compare_and_swap(
        fixture.floor_store.namespace,
        key,
        expected_revision=record.revision,
        value=payload,
    )
    report = lineage_auditor(
        fixture
    ).inspect(plan.workflow_id)
    assert report.status is CompactionLineageStatus.MANUAL_REVIEW
    assert any(
        item.code == "floor.lookup_corruption"
        for item in report.findings
    )


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_compaction_lineage_report_digest_is_stable(kind):
    fixture = OperatorFixture(kind=kind)
    plan, _, _ = fixture.through_complete()
    auditor = lineage_auditor(fixture)
    first = auditor.require_verified(
        plan.workflow_id
    )
    second = auditor.require_verified(
        plan.workflow_id
    )
    assert first == second
    assert first.digest == second.digest


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_compaction_lineage_report_serializes_full_authority(kind):
    fixture = OperatorFixture(kind=kind)
    plan, _, _ = fixture.through_complete()
    report = lineage_auditor(
        fixture
    ).require_verified(plan.workflow_id)
    data = report.to_dict()
    assert data["status"] == "verified"
    assert data["ok"] is True
    assert data["certificate"]["verified"] is True
    assert data["authorization"]["verified"] is True
    assert data["archive"]["verified"] is True
    assert data["pruning_manifest"]["verified"] is True
    assert data["pruning_operation"]["verified"] is True
    assert data["hot_floor"]["verified"] is True
    assert data["digest"] == report.digest


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_compaction_lineage_require_verified_rejects_incomplete(kind):
    fixture = OperatorFixture(kind=kind)
    plan = fixture.plan()
    with pytest.raises(
        DurableCompactionLineageError,
    ):
        lineage_auditor(
            fixture
        ).require_verified(
            plan.workflow_id
        )


def test_compaction_lineage_workflow_id_validation():
    fixture = OperatorFixture()
    with pytest.raises(
        ValueError,
        match="64-character",
    ):
        lineage_auditor(
            fixture
        ).inspect("bad")


def lineage_guard(
    fixture,
    policy=None,
):
    return CompactionLineageFleetGuard(
        lineage_auditor(fixture),
        policy,
    )


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_lineage_fleet_all_verified_is_allowed(kind):
    fixture = OperatorFixture(kind=kind)
    plan, _, _ = fixture.through_complete()
    report = lineage_guard(
        fixture
    ).require(
        (plan.workflow_id,)
    )
    assert report.allowed
    assert report.verified == 1
    assert report.incomplete == 0
    assert report.manual_review == 0
    assert report.errors == 0


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_lineage_fleet_default_policy_denies_incomplete(kind):
    fixture = OperatorFixture(kind=kind)
    plan = fixture.plan()
    report = lineage_guard(
        fixture
    ).inspect(
        (plan.workflow_id,)
    )
    assert not report.allowed
    assert report.incomplete == 1
    assert report.errors >= 1
    assert any(
        item.code
        == "compaction_lineage.incomplete_bound"
        for item in report.findings
    )


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_lineage_fleet_can_tolerate_bounded_incomplete(kind):
    fixture = OperatorFixture(kind=kind)
    plan = fixture.plan()
    guard = lineage_guard(
        fixture,
        CompactionLineageHealthPolicy(
            max_incomplete=1,
        ),
    )
    report = guard.require(
        (plan.workflow_id,)
    )
    assert report.allowed
    assert report.incomplete == 1
    assert report.errors == 0
    assert report.warnings >= 1


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_lineage_fleet_manual_review_is_never_tolerated(kind):
    fixture = OperatorFixture(kind=kind)
    plan = fixture.plan()
    fixture.certify(plan.workflow_id)
    stored = fixture.operator.current(
        plan.workflow_id
    )
    key = fixture.operator._key(
        plan.workflow_id
    )
    record = fixture.backend.get(
        fixture.operator.namespace,
        key,
    )
    fixture.backend.compare_and_swap(
        fixture.operator.namespace,
        key,
        expected_revision=record.revision,
        value=replace(
            stored.workflow,
            certificate_digest=fp(
                "fleet-conflict"
            ),
        ),
    )
    guard = lineage_guard(
        fixture,
        CompactionLineageHealthPolicy(
            max_incomplete=10,
        ),
    )
    report = guard.inspect(
        (plan.workflow_id,)
    )
    assert not report.allowed
    assert report.manual_review == 1
    assert report.errors >= 1
    assert any(
        item.code
        == "compaction_lineage.manual_review_present"
        for item in report.findings
    )


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_lineage_fleet_minimum_verified_is_enforced(kind):
    fixture = OperatorFixture(kind=kind)
    plan = fixture.plan()
    guard = lineage_guard(
        fixture,
        CompactionLineageHealthPolicy(
            max_incomplete=1,
            minimum_verified=1,
        ),
    )
    report = guard.inspect(
        (plan.workflow_id,)
    )
    assert not report.allowed
    assert any(
        item.code
        == "compaction_lineage.minimum_verified"
        for item in report.findings
    )


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_lineage_fleet_minimum_verified_accepts_completed(kind):
    fixture = OperatorFixture(kind=kind)
    plan, _, _ = fixture.through_complete()
    guard = lineage_guard(
        fixture,
        CompactionLineageHealthPolicy(
            minimum_verified=1,
        ),
    )
    report = guard.require(
        (plan.workflow_id,)
    )
    assert report.allowed
    assert report.verified == 1


def test_lineage_fleet_require_nonempty():
    fixture = OperatorFixture()
    guard = lineage_guard(
        fixture,
        CompactionLineageHealthPolicy(
            require_nonempty=True,
        ),
    )
    report = guard.inspect(())
    assert not report.allowed
    assert any(
        item.code
        == "compaction_lineage.empty_required_set"
        for item in report.findings
    )


def test_lineage_fleet_empty_allowed_by_default():
    fixture = OperatorFixture()
    report = lineage_guard(
        fixture
    ).require(())
    assert report.allowed
    assert report.workflow_ids == ()
    assert report.reports == ()


def test_lineage_fleet_sorts_workflow_ids():
    fixture = OperatorFixture()
    first = fixture.plan()
    second_id = fp(
        "synthetic-missing-second"
    )
    guard = lineage_guard(
        fixture,
        CompactionLineageHealthPolicy(
            max_incomplete=2,
        ),
    )
    report = guard.inspect(
        (second_id, first.workflow_id)
    )
    assert report.workflow_ids == tuple(
        sorted(
            (
                second_id,
                first.workflow_id,
            )
        )
    )


def test_lineage_fleet_rejects_duplicate_ids():
    fixture = OperatorFixture()
    plan = fixture.plan()
    with pytest.raises(
        ValueError,
        match="duplicate",
    ):
        lineage_guard(
            fixture
        ).inspect(
            (
                plan.workflow_id,
                plan.workflow_id,
            )
        )


@pytest.mark.parametrize(
    "workflow_id",
    ["", "bad", "x" * 63, "x" * 65],
)
def test_lineage_fleet_rejects_invalid_ids(workflow_id):
    fixture = OperatorFixture()
    with pytest.raises(
        ValueError,
        match="64-character",
    ):
        lineage_guard(
            fixture
        ).inspect(
            (workflow_id,)
        )


def test_lineage_fleet_max_workflow_bound():
    fixture = OperatorFixture()
    guard = lineage_guard(
        fixture,
        CompactionLineageHealthPolicy(
            max_workflows=1,
            max_incomplete=1,
        ),
    )
    with pytest.raises(
        CompactionLineageFleetError,
        match="bound",
    ):
        guard.inspect(
            (
                fp("workflow-one"),
                fp("workflow-two"),
            )
        )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"max_workflows": 0},
        {"max_workflows": True},
        {"max_incomplete": -1},
        {"minimum_verified": -1},
        {"max_findings": 0},
        {"max_findings": True},
        {"require_nonempty": "yes"},
    ],
)
def test_lineage_health_policy_validation(kwargs):
    with pytest.raises(ValueError):
        CompactionLineageHealthPolicy(
            **kwargs
        )


def test_lineage_health_policy_rejects_incomplete_above_workflow_bound():
    with pytest.raises(
        ValueError,
        match="max_incomplete",
    ):
        CompactionLineageHealthPolicy(
            max_workflows=2,
            max_incomplete=3,
        )


def test_lineage_health_policy_rejects_minimum_verified_above_workflow_bound():
    with pytest.raises(
        ValueError,
        match="minimum_verified",
    ):
        CompactionLineageHealthPolicy(
            max_workflows=2,
            minimum_verified=3,
        )


def test_lineage_health_policy_digest_is_stable():
    one = CompactionLineageHealthPolicy(
        max_workflows=10,
        max_incomplete=2,
        minimum_verified=3,
        require_nonempty=True,
        max_findings=99,
    )
    two = CompactionLineageHealthPolicy(
        max_workflows=10,
        max_incomplete=2,
        minimum_verified=3,
        require_nonempty=True,
        max_findings=99,
    )
    assert one.digest == two.digest
    assert len(one.digest) == 64


def test_lineage_health_policy_digest_changes_with_policy():
    one = CompactionLineageHealthPolicy()
    two = CompactionLineageHealthPolicy(
        max_incomplete=1,
    )
    assert one.digest != two.digest


class RaisingLineageAuditor(
    DurableCompactionLineageAuditor
):
    def inspect(self, workflow_id):
        raise RuntimeError(
            "synthetic lineage probe failure"
        )


def test_lineage_fleet_probe_exception_fails_closed():
    fixture = OperatorFixture()
    guard = CompactionLineageFleetGuard(
        RaisingLineageAuditor(
            fixture.operator
        )
    )
    workflow_id = fp(
        "probe-error-workflow"
    )
    report = guard.inspect(
        (workflow_id,)
    )
    assert not report.allowed
    assert report.manual_review == 1
    assert report.reports[0].requires_manual_review
    assert any(
        detail.code
        == "lineage.probe_error"
        for detail
        in report.reports[0].findings
    )


def test_lineage_fleet_require_raises_on_probe_error():
    fixture = OperatorFixture()
    guard = CompactionLineageFleetGuard(
        RaisingLineageAuditor(
            fixture.operator
        )
    )
    with pytest.raises(
        CompactionLineageFleetError,
    ):
        guard.require(
            (fp("probe-error"),)
        )


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_lineage_fleet_require_raises_on_manual_review(kind):
    fixture = OperatorFixture(kind=kind)
    plan = fixture.plan()
    fixture.certify(plan.workflow_id)
    stored = fixture.operator.current(
        plan.workflow_id
    )
    key = fixture.operator._key(
        plan.workflow_id
    )
    record = fixture.backend.get(
        fixture.operator.namespace,
        key,
    )
    fixture.backend.compare_and_swap(
        fixture.operator.namespace,
        key,
        expected_revision=record.revision,
        value=replace(
            stored.workflow,
            certificate_digest=fp(
                "manual-review-conflict"
            ),
        ),
    )
    with pytest.raises(
        CompactionLineageFleetError,
    ):
        lineage_guard(
            fixture
        ).require(
            (plan.workflow_id,)
        )


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_lineage_fleet_report_digest_is_stable(kind):
    fixture = OperatorFixture(kind=kind)
    plan, _, _ = fixture.through_complete()
    guard = lineage_guard(fixture)
    first = guard.require(
        (plan.workflow_id,)
    )
    second = guard.require(
        (plan.workflow_id,)
    )
    assert first == second
    assert first.digest == second.digest
    assert first.to_dict()["digest"] == first.digest


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_lineage_fleet_report_serializes_counts(kind):
    fixture = OperatorFixture(kind=kind)
    plan, _, _ = fixture.through_complete()
    report = lineage_guard(
        fixture
    ).require(
        (plan.workflow_id,)
    )
    data = report.to_dict()
    assert data["allowed"] is True
    assert data["verified"] == 1
    assert data["incomplete"] == 0
    assert data["manual_review"] == 0
    assert data["errors"] == 0
    assert data["workflow_ids"] == [
        plan.workflow_id
    ]


def test_lineage_health_finding_validation():
    finding = CompactionLineageHealthFinding(
        CompactionLineageHealthSeverity.WARNING,
        "code",
        "message",
        fp("workflow"),
    )
    assert finding.to_dict() == {
        "severity": "warning",
        "code": "code",
        "message": "message",
        "workflow_id": fp("workflow"),
    }
    with pytest.raises(ValueError):
        CompactionLineageHealthFinding(
            CompactionLineageHealthSeverity.ERROR,
            "",
            "message",
        )
    with pytest.raises(ValueError):
        CompactionLineageHealthFinding(
            CompactionLineageHealthSeverity.ERROR,
            "code",
            "",
        )


def test_lineage_guard_requires_auditor():
    with pytest.raises(
        TypeError,
        match="auditor",
    ):
        CompactionLineageFleetGuard(
            object()
        )


def test_lineage_guard_requires_policy_type():
    fixture = OperatorFixture()
    with pytest.raises(
        TypeError,
        match="policy",
    ):
        CompactionLineageFleetGuard(
            lineage_auditor(
                fixture
            ),
            object(),
        )


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_lineage_fleet_detail_conflicts_become_health_errors(kind):
    fixture = OperatorFixture(kind=kind)
    plan = fixture.plan()
    fixture.certify(plan.workflow_id)
    stored = fixture.operator.current(
        plan.workflow_id
    )
    key = fixture.operator._key(
        plan.workflow_id
    )
    record = fixture.backend.get(
        fixture.operator.namespace,
        key,
    )
    fixture.backend.compare_and_swap(
        fixture.operator.namespace,
        key,
        expected_revision=record.revision,
        value=replace(
            stored.workflow,
            certificate_digest=fp(
                "detail-conflict"
            ),
        ),
    )
    report = lineage_guard(
        fixture
    ).inspect(
        (plan.workflow_id,)
    )
    assert any(
        item.code.startswith(
            "compaction_lineage.detail."
        )
        for item in report.findings
    )


def test_lineage_fleet_max_findings_bound_fails_closed():
    fixture = OperatorFixture()
    guard = CompactionLineageFleetGuard(
        RaisingLineageAuditor(
            fixture.operator
        ),
        CompactionLineageHealthPolicy(
            max_workflows=10,
            max_incomplete=10,
            max_findings=1,
        ),
    )
    # A manual-review report creates both a fleet-level and per-workflow error,
    # exceeding the deliberately tiny finding budget.
    with pytest.raises(
        CompactionLineageFleetError,
        match="finding bound",
    ):
        guard.inspect(
            (fp("many-findings"),)
        )


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_lineage_fleet_mixed_verified_and_incomplete_with_tolerance(kind):
    fixture = OperatorFixture(kind=kind)
    completed, _, _ = (
        fixture.through_complete()
    )
    missing = fp(
        "missing-incomplete-workflow"
    )
    guard = lineage_guard(
        fixture,
        CompactionLineageHealthPolicy(
            max_incomplete=1,
            minimum_verified=1,
        ),
    )
    report = guard.require(
        (
            completed.workflow_id,
            missing,
        )
    )
    assert report.allowed
    assert report.verified == 1
    assert report.incomplete == 1
    assert report.manual_review == 0


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_lineage_fleet_mixed_manual_review_denies_even_with_incomplete_tolerance(kind):
    fixture = OperatorFixture(kind=kind)
    completed, _, _ = fixture.through_complete()
    workflow = fixture.operator.current(
        completed.workflow_id
    )
    key = fixture.operator._key(
        completed.workflow_id
    )
    record = fixture.backend.get(
        fixture.operator.namespace,
        key,
    )
    fixture.backend.compare_and_swap(
        fixture.operator.namespace,
        key,
        expected_revision=record.revision,
        value=replace(
            workflow.workflow,
            floor_id=fp("fleet-wrong-floor"),
        ),
    )
    guard = lineage_guard(
        fixture,
        CompactionLineageHealthPolicy(
            max_incomplete=10,
        ),
    )
    report = guard.inspect(
        (
            completed.workflow_id,
            fp("missing-workflow"),
        )
    )
    assert not report.allowed
    assert report.manual_review == 1


def maintenance_guard(
    fixture,
    *,
    lineage_policy=None,
    maintenance_policy=None,
):
    return DurableCompactionMaintenanceGuard(
        lineage_guard(
            fixture,
            lineage_policy,
        ),
        maintenance_policy,
    )


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_compaction_maintenance_complete_history_is_allowed(kind):
    fixture = OperatorFixture(kind=kind)
    plan, _, _ = fixture.through_complete()
    report = maintenance_guard(
        fixture
    ).require(
        (plan.workflow_id,),
        (fixture.chain_id,),
    )
    assert report.allowed
    assert report.errors == 0
    assert report.total_floors == 1
    assert report.unclaimed_floors == 0
    assert report.chains[0].ok
    assert report.chains[0].claimed_floor_ids == (
        fixture.operator.current(
            plan.workflow_id
        ).workflow.floor_id,
    )


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_compaction_maintenance_orphan_floor_is_denied(kind):
    fixture = OperatorFixture(kind=kind)
    plan, _, _ = fixture.through_complete()
    workflow = fixture.operator.current(
        plan.workflow_id
    ).workflow
    first_floor = fixture.floor_store.floor_at(
        fixture.chain_id,
        workflow.cutoff_sequence,
    )
    fixture.floor_store.advance(
        chain_id=fixture.chain_id,
        sequence=workflow.cutoff_sequence + 1,
        root_hash=fp("maintenance-orphan-root"),
        archive_id="maintenance-orphan-archive",
        archive_manifest_digest=fp(
            "maintenance-orphan-archive"
        ),
        compaction_certificate_id=fp(
            "maintenance-orphan-certificate"
        ),
        pruning_authorization_id=fp(
            "maintenance-orphan-authorization"
        ),
        operation_id=fp(
            "maintenance-orphan-operation"
        ),
        fencing_token=(
            first_floor.floor.fencing_token + 1
        ),
        expected_previous_sequence=(
            workflow.cutoff_sequence
        ),
        expected_previous_root=(
            workflow.cutoff_root
        ),
    )
    report = maintenance_guard(
        fixture
    ).inspect(
        (plan.workflow_id,),
        (fixture.chain_id,),
    )
    assert not report.allowed
    assert report.unclaimed_floors == 1
    assert any(
        item.code
        == "maintenance.floor_without_workflow"
        for item in report.chains[0].findings
    )


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_compaction_maintenance_can_disable_floor_coverage_policy(kind):
    fixture = OperatorFixture(kind=kind)
    plan, _, _ = fixture.through_complete()
    workflow = fixture.operator.current(
        plan.workflow_id
    ).workflow
    first_floor = fixture.floor_store.floor_at(
        fixture.chain_id,
        workflow.cutoff_sequence,
    )
    fixture.floor_store.advance(
        chain_id=fixture.chain_id,
        sequence=workflow.cutoff_sequence + 1,
        root_hash=fp("maintenance-uncovered-root"),
        archive_id="maintenance-uncovered-archive",
        archive_manifest_digest=fp(
            "maintenance-uncovered-archive"
        ),
        compaction_certificate_id=fp(
            "maintenance-uncovered-certificate"
        ),
        pruning_authorization_id=fp(
            "maintenance-uncovered-authorization"
        ),
        operation_id=fp(
            "maintenance-uncovered-operation"
        ),
        fencing_token=(
            first_floor.floor.fencing_token + 1
        ),
        expected_previous_sequence=(
            workflow.cutoff_sequence
        ),
        expected_previous_root=(
            workflow.cutoff_root
        ),
    )
    guard = maintenance_guard(
        fixture,
        maintenance_policy=CompactionMaintenancePolicy(
            require_floor_workflow_coverage=False,
        ),
    )
    report = guard.require(
        (plan.workflow_id,),
        (fixture.chain_id,),
    )
    assert report.allowed
    assert report.unclaimed_floors == 1


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_compaction_maintenance_incomplete_workflow_default_denied(kind):
    fixture = OperatorFixture(kind=kind)
    plan = fixture.plan()
    report = maintenance_guard(
        fixture
    ).inspect(
        (plan.workflow_id,),
        (fixture.chain_id,),
    )
    assert not report.allowed
    assert not report.lineage.allowed
    assert report.total_floors == 0


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_compaction_maintenance_incomplete_workflow_can_be_tolerated(kind):
    fixture = OperatorFixture(kind=kind)
    plan = fixture.plan()
    guard = maintenance_guard(
        fixture,
        lineage_policy=CompactionLineageHealthPolicy(
            max_incomplete=1,
        ),
    )
    report = guard.require(
        (plan.workflow_id,),
        (fixture.chain_id,),
    )
    assert report.allowed
    assert report.lineage.incomplete == 1
    assert report.total_floors == 0


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_compaction_maintenance_manual_review_never_allowed(kind):
    fixture = OperatorFixture(kind=kind)
    plan = fixture.plan()
    fixture.certify(plan.workflow_id)
    stored = fixture.operator.current(
        plan.workflow_id
    )
    key = fixture.operator._key(
        plan.workflow_id
    )
    record = fixture.backend.get(
        fixture.operator.namespace,
        key,
    )
    fixture.backend.compare_and_swap(
        fixture.operator.namespace,
        key,
        expected_revision=record.revision,
        value=replace(
            stored.workflow,
            certificate_digest=fp(
                "maintenance-conflict"
            ),
        ),
    )
    report = maintenance_guard(
        fixture,
        lineage_policy=CompactionLineageHealthPolicy(
            max_incomplete=10,
        ),
    ).inspect(
        (plan.workflow_id,),
        (fixture.chain_id,),
    )
    assert not report.allowed
    assert report.lineage.manual_review == 1


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_compaction_maintenance_unchecked_workflow_chain_is_denied(kind):
    fixture = OperatorFixture(kind=kind)
    plan, _, _ = fixture.through_complete()
    report = maintenance_guard(
        fixture
    ).inspect(
        (plan.workflow_id,),
        ("other-chain",),
    )
    assert not report.allowed
    assert any(
        item.code
        == "maintenance.workflow_chain_unchecked"
        for item in report.findings
    )


def test_compaction_maintenance_requires_nonempty_chain_set_by_default():
    fixture = OperatorFixture()
    plan = fixture.plan()
    report = maintenance_guard(
        fixture,
        lineage_policy=CompactionLineageHealthPolicy(
            max_incomplete=1,
        ),
    ).inspect(
        (plan.workflow_id,),
        (),
    )
    assert not report.allowed
    assert any(
        item.code
        == "maintenance.empty_chain_set"
        for item in report.findings
    )


def test_compaction_maintenance_can_allow_empty_chain_set():
    fixture = OperatorFixture()
    guard = maintenance_guard(
        fixture,
        maintenance_policy=CompactionMaintenancePolicy(
            require_nonempty_chains=False,
        ),
    )
    report = guard.require(
        (),
        (),
    )
    assert report.allowed
    assert report.chains == ()


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_compaction_maintenance_corrupt_floor_history_is_denied(kind):
    fixture = OperatorFixture(kind=kind)
    plan, _, _ = fixture.through_complete()
    workflow = fixture.operator.current(
        plan.workflow_id
    ).workflow
    history_key = fixture.floor_store._history_key(
        workflow.floor_id
    )
    record = fixture.backend.get(
        fixture.floor_store.namespace,
        history_key,
    )
    payload = dict(record.value)
    floor_payload = dict(
        payload["floor"]
    )
    floor_payload["archive_id"] = (
        "maintenance-tampered-archive"
    )
    payload["floor"] = floor_payload
    fixture.backend.compare_and_swap(
        fixture.floor_store.namespace,
        history_key,
        expected_revision=record.revision,
        value=payload,
    )
    report = maintenance_guard(
        fixture
    ).inspect(
        (plan.workflow_id,),
        (fixture.chain_id,),
    )
    assert not report.allowed
    assert any(
        item.code
        == "maintenance.floor_history_invalid"
        for item in report.chains[0].findings
    )


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_compaction_maintenance_missing_floor_history_is_denied(kind):
    fixture = OperatorFixture(kind=kind)
    plan, _, _ = fixture.through_complete()
    workflow = fixture.operator.current(
        plan.workflow_id
    ).workflow
    floor = fixture.floor_store.floor_at(
        fixture.chain_id,
        workflow.cutoff_sequence,
    )
    fixture.floor_store.advance(
        chain_id=fixture.chain_id,
        sequence=workflow.cutoff_sequence + 1,
        root_hash=fp("maintenance-next-root"),
        archive_id="maintenance-next-archive",
        archive_manifest_digest=fp(
            "maintenance-next-archive"
        ),
        compaction_certificate_id=fp(
            "maintenance-next-certificate"
        ),
        pruning_authorization_id=fp(
            "maintenance-next-authorization"
        ),
        operation_id=fp(
            "maintenance-next-operation"
        ),
        fencing_token=floor.floor.fencing_token + 1,
        expected_previous_sequence=(
            workflow.cutoff_sequence
        ),
        expected_previous_root=workflow.cutoff_root,
    )
    history_key = fixture.floor_store._history_key(
        workflow.floor_id
    )
    index_key = fixture.floor_store._sequence_key(
        fixture.chain_id,
        workflow.cutoff_sequence,
    )
    history_record = fixture.backend.get(
        fixture.floor_store.namespace,
        history_key,
    )
    index_record = fixture.backend.get(
        fixture.floor_store.namespace,
        index_key,
    )
    fixture.backend.delete(
        fixture.floor_store.namespace,
        history_key,
        expected_revision=history_record.revision,
    )
    fixture.backend.delete(
        fixture.floor_store.namespace,
        index_key,
        expected_revision=index_record.revision,
    )
    report = maintenance_guard(
        fixture
    ).inspect(
        (plan.workflow_id,),
        (fixture.chain_id,),
    )
    assert not report.allowed


@pytest.mark.parametrize(
    "chain_ids",
    [
        ("journal", "journal"),
        ("",),
        ("x" * 129,),
    ],
)
def test_compaction_maintenance_chain_id_validation(chain_ids):
    fixture = OperatorFixture()
    guard = maintenance_guard(fixture)
    with pytest.raises(ValueError):
        guard.inspect(
            (),
            chain_ids,
        )


def test_compaction_maintenance_chain_bound():
    fixture = OperatorFixture()
    guard = maintenance_guard(
        fixture,
        maintenance_policy=CompactionMaintenancePolicy(
            max_chains=1,
            require_nonempty_chains=False,
        ),
    )
    with pytest.raises(
        DurableCompactionMaintenanceError,
        match="chain bound",
    ):
        guard.inspect(
            (),
            ("a", "b"),
        )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"max_chains": 0},
        {"max_chains": True},
        {"max_findings": 0},
        {"max_findings": True},
        {"require_nonempty_chains": "yes"},
        {"require_floor_workflow_coverage": "yes"},
        {"reject_duplicate_floor_claims": "yes"},
    ],
)
def test_compaction_maintenance_policy_validation(kwargs):
    with pytest.raises(ValueError):
        CompactionMaintenancePolicy(
            **kwargs
        )


def test_compaction_maintenance_policy_digest_is_stable():
    one = CompactionMaintenancePolicy(
        max_chains=10,
        max_findings=20,
        require_nonempty_chains=False,
        require_floor_workflow_coverage=False,
        reject_duplicate_floor_claims=False,
    )
    two = CompactionMaintenancePolicy(
        max_chains=10,
        max_findings=20,
        require_nonempty_chains=False,
        require_floor_workflow_coverage=False,
        reject_duplicate_floor_claims=False,
    )
    assert one.digest == two.digest
    assert len(one.digest) == 64


def test_compaction_maintenance_policy_digest_changes():
    assert (
        CompactionMaintenancePolicy().digest
        != CompactionMaintenancePolicy(
            require_floor_workflow_coverage=False,
        ).digest
    )


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_compaction_maintenance_report_digest_is_stable(kind):
    fixture = OperatorFixture(kind=kind)
    plan, _, _ = fixture.through_complete()
    guard = maintenance_guard(fixture)
    first = guard.require(
        (plan.workflow_id,),
        (fixture.chain_id,),
    )
    second = guard.require(
        (plan.workflow_id,),
        (fixture.chain_id,),
    )
    assert first == second
    assert first.digest == second.digest
    assert first.to_dict()["digest"] == first.digest


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_compaction_maintenance_report_serializes_chain_coverage(kind):
    fixture = OperatorFixture(kind=kind)
    plan, _, _ = fixture.through_complete()
    report = maintenance_guard(
        fixture
    ).require(
        (plan.workflow_id,),
        (fixture.chain_id,),
    )
    data = report.to_dict()
    assert data["allowed"] is True
    assert data["total_floors"] == 1
    assert data["unclaimed_floors"] == 0
    assert data["chains"][0]["ok"] is True
    assert (
        data["chains"][0]["floor_count"]
        == 1
    )


def test_compaction_maintenance_finding_validation():
    finding = CompactionMaintenanceFinding(
        CompactionMaintenanceSeverity.WARNING,
        "maintenance.test",
        "warning",
        "journal",
        fp("workflow"),
        fp("floor"),
    )
    assert (
        finding.to_dict()["severity"]
        == "warning"
    )
    with pytest.raises(ValueError):
        CompactionMaintenanceFinding(
            CompactionMaintenanceSeverity.ERROR,
            "",
            "message",
        )
    with pytest.raises(ValueError):
        CompactionMaintenanceFinding(
            CompactionMaintenanceSeverity.ERROR,
            "code",
            "",
        )
    with pytest.raises(ValueError):
        CompactionMaintenanceFinding(
            CompactionMaintenanceSeverity.ERROR,
            "code",
            "message",
            floor_id="bad",
        )


def test_compaction_maintenance_guard_requires_lineage_guard():
    with pytest.raises(
        TypeError,
        match="lineage",
    ):
        DurableCompactionMaintenanceGuard(
            object()
        )


def test_compaction_maintenance_guard_requires_policy_type():
    fixture = OperatorFixture()
    with pytest.raises(
        TypeError,
        match="policy",
    ):
        DurableCompactionMaintenanceGuard(
            lineage_guard(fixture),
            object(),
        )


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_compaction_maintenance_require_raises_when_denied(kind):
    fixture = OperatorFixture(kind=kind)
    plan = fixture.plan()
    with pytest.raises(
        DurableCompactionMaintenanceError,
    ):
        maintenance_guard(
            fixture
        ).require(
            (plan.workflow_id,),
            (fixture.chain_id,),
        )


def test_compaction_maintenance_max_findings_bound():
    fixture = OperatorFixture()
    plan = fixture.plan()
    guard = maintenance_guard(
        fixture,
        maintenance_policy=CompactionMaintenancePolicy(
            max_findings=1,
        ),
    )
    # An incomplete lineage creates multiple findings across lineage and
    # maintenance accounting, exceeding this deliberately tiny cap.
    with pytest.raises(
        DurableCompactionMaintenanceError,
        match="finding bound",
    ):
        guard.inspect(
            (plan.workflow_id,),
            ("other-chain",),
        )


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_compaction_maintenance_current_floor_is_covered_by_workflow(kind):
    fixture = OperatorFixture(kind=kind)
    plan, _, _ = fixture.through_complete()
    workflow = fixture.operator.current(
        plan.workflow_id
    ).workflow
    report = maintenance_guard(
        fixture
    ).require(
        (plan.workflow_id,),
        (fixture.chain_id,),
    )
    current = fixture.floor_store.current(
        fixture.chain_id
    )
    assert current.floor.floor_id == workflow.floor_id
    assert (
        current.floor.floor_id
        in report.chains[0].claimed_floor_ids
    )


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_compaction_maintenance_history_digest_is_in_report(kind):
    fixture = OperatorFixture(kind=kind)
    plan, _, _ = fixture.through_complete()
    report = maintenance_guard(
        fixture
    ).require(
        (plan.workflow_id,),
        (fixture.chain_id,),
    )
    chain = report.chains[0]
    data = chain.to_dict()
    assert (
        data["history"]["digest"]
        == chain.history.digest
    )


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_compaction_maintenance_lineage_floor_claim_matches_history(kind):
    fixture = OperatorFixture(kind=kind)
    plan, _, _ = fixture.through_complete()
    report = maintenance_guard(
        fixture
    ).require(
        (plan.workflow_id,),
        (fixture.chain_id,),
    )
    lineage_floor = (
        report.lineage.reports[0]
        .hot_floor.artifact_id
    )
    history_ids = {
        item.floor.floor_id
        for item in report.chains[0]
        .history.floors
    }
    assert lineage_floor in history_ids
