"""Reservation-aware durable compaction operator and group integration tests."""

from __future__ import annotations

import hashlib

import pytest

from skeleton.shells.ai.distributed_journal import DistributedAIDecisionJournal
from skeleton.shells.ai.distributed_state import InMemoryFencedStore
from skeleton.shells.ai.durable_archive import DurableArchiveManifestBuilder
from skeleton.shells.ai.durable_archive_store import DurableArchiveRepository
from skeleton.shells.ai.durable_checkpoint import DurableChainCheckpointStore
from skeleton.shells.ai.durable_compaction import (
    DurableCompactionPlanner,
    DurableCompactionPolicy,
)
from skeleton.shells.ai.durable_compaction_certificate import (
    DurableCompactionCertificateStore,
)
from skeleton.shells.ai.durable_compaction_group import (
    DurableCompactionGroupCoordinator,
    DurableCompactionGroupPhase,
    DurableCompactionGroupRequest,
    DurableCompactionGroupStale,
)
from skeleton.shells.ai.durable_compaction_operator import (
    DurableCompactionOperator,
    DurableCompactionWorkflowStale,
)
from skeleton.shells.ai.durable_compaction_reservation import (
    DurableCompactionReservationConflict,
    DurableCompactionReservationStore,
)
from skeleton.shells.ai.durable_hot_floor import DurableHotFloorStore
from skeleton.shells.ai.durable_pruning import DurablePruningExecutor
from skeleton.shells.ai.durable_pruning_authorization import (
    DurablePruningAuthorizationStore,
)
from skeleton.shells.ai.durable_retention import (
    DurableRetentionPlanner,
    DurableRetentionPolicy,
)
from skeleton.shells.ai.signed_artifact import ArtifactSigner
from skeleton.shells.distributed_receipts import DistributedReceiptChain
from skeleton.shells.receipts import ExecutionReceipt


def fp(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def signer(name: str, char: bytes, clock=lambda: 100.0):
    return ArtifactSigner(
        name,
        char * 32,
        clock=clock,
    )


def append_events(journal, count, *, start=0):
    return tuple(
        journal.append(
            "reservation.integration",
            session_id=f"session-{index}",
            intent_id=f"intent-{index}",
            proposal_id=f"proposal-{index}",
            summary=f"event {index}",
            data={"index": index},
        )
        for index in range(start, start + count)
    )


def receipt(index: int) -> ExecutionReceipt:
    return ExecutionReceipt(
        command="python",
        correlation_id=f"corr-{index}",
        fingerprint=fp(f"receipt:{index}"),
        started_at="2026-09-19T00:00:00+00:00",
        finished_at="2026-09-19T00:00:01+00:00",
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


class FailReceiptOnceOperator(DurableCompactionOperator):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fail_enabled = False
        self.failed = False

    def execute(
        self,
        workflow_id,
        retention,
        chain,
        *,
        reservation_holder_id="",
    ):
        stored = self.current(workflow_id)
        if (
            self.fail_enabled
            and not self.failed
            and stored is not None
            and stored.workflow.chain_id == "receipts"
        ):
            self.failed = True
            raise RuntimeError("synthetic reservation group failure")
        return super().execute(
            workflow_id,
            retention,
            chain,
            reservation_holder_id=reservation_holder_id,
        )


class Fixture:
    def __init__(
        self,
        *,
        operator_class=DurableCompactionOperator,
        reservation_ttl=60.0,
    ):
        self.now = [400.0]
        self.backend = InMemoryFencedStore()
        self.floor_store = DurableHotFloorStore(
            self.backend,
            signer("floor", b"f", lambda: self.now[0]),
            namespace="reservation-hot-floors",
            clock=lambda: self.now[0],
        )
        self.journal = DistributedAIDecisionJournal(
            self.backend,
            namespace="journal",
            max_events=20,
            clock=lambda: 10.0,
            hot_floor_store=self.floor_store,
            hot_floor_chain_id="journal",
        )
        self.receipts = DistributedReceiptChain(
            self.backend,
            namespace="receipts",
            max_receipts=20,
            hot_floor_store=self.floor_store,
            hot_floor_chain_id="receipts",
        )
        self.first_journal = append_events(self.journal, 6)
        self.first_receipts = tuple(
            self.receipts.append(receipt(index))
            for index in range(6)
        )

        self.checkpoints = DurableChainCheckpointStore(
            self.backend,
            signer("checkpoint", b"c"),
            namespace="reservation-checkpoints",
            clock=lambda: 100.0,
        )
        self.archive_signer = signer("archive", b"a")
        self.archive_builder = DurableArchiveManifestBuilder(
            self.checkpoints,
            self.archive_signer,
            clock=lambda: 200.0,
        )
        self.archives = DurableArchiveRepository(
            self.backend,
            self.checkpoints,
            self.archive_signer,
            namespace="reservation-archives",
            clock=lambda: 300.0,
        )
        for chain_id, chain in (
            ("journal", self.journal),
            ("receipts", self.receipts),
        ):
            checkpoint = self.checkpoints.publish(chain_id, chain)
            archive = self.archive_builder.build(checkpoint, chain)
            self.archives.put(archive, checkpoint, chain)

        self.later_journal = append_events(self.journal, 2, start=6)
        self.later_receipts = tuple(
            self.receipts.append(receipt(index))
            for index in range(6, 8)
        )

        self.retention_planner = DurableRetentionPlanner(
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
        self.journal_retention = self.retention_planner.plan(
            "journal",
            self.journal,
        )
        self.receipt_retention = self.retention_planner.plan(
            "receipts",
            self.receipts,
        )
        self.compaction = DurableCompactionPlanner(
            self.archives,
            DurableCompactionPolicy(
                minimum_live_tail=2,
                maximum_candidate_nodes=20,
                max_protected_roots=32,
            ),
        )
        self.certificates = DurableCompactionCertificateStore(
            self.backend,
            signer("certificate", b"s", lambda: self.now[0]),
            self.compaction,
            namespace="reservation-certificates",
            ttl_seconds=60.0,
            max_ttl_seconds=3600.0,
            clock=lambda: self.now[0],
        )

        auth_nonce = [0]

        def next_auth_nonce():
            auth_nonce[0] += 1
            return f"auth-{auth_nonce[0]}"

        self.authorizations = DurablePruningAuthorizationStore(
            self.backend,
            signer("authorization", b"p", lambda: self.now[0]),
            self.certificates,
            namespace="reservation-authorizations",
            ttl_seconds=30.0,
            max_ttl_seconds=600.0,
            max_delete_items=100,
            clock=lambda: self.now[0],
            nonce_factory=next_auth_nonce,
        )
        self.executor = DurablePruningExecutor(
            self.backend,
            self.authorizations,
            self.floor_store,
            namespace="reservation-pruning",
            max_items=100,
            clock=lambda: self.now[0],
        )

        reservation_nonce = [0]

        def next_reservation_nonce():
            reservation_nonce[0] += 1
            return f"reservation-{reservation_nonce[0]}"

        self.reservations = DurableCompactionReservationStore(
            self.backend,
            signer("reservation", b"r", lambda: self.now[0]),
            namespace="compaction-reservations",
            ttl_seconds=reservation_ttl,
            max_ttl_seconds=3600.0,
            clock=lambda: self.now[0],
            nonce_factory=next_reservation_nonce,
        )
        self.operator = operator_class(
            self.backend,
            self.compaction,
            self.certificates,
            self.authorizations,
            self.executor,
            reservations=self.reservations,
            namespace="reserved-member-workflows",
            clock=lambda: self.now[0],
        )
        self.coordinator = DurableCompactionGroupCoordinator(
            self.backend,
            reservations=self.reservations,
            namespace="reserved-groups",
            clock=lambda: self.now[0],
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

    def plan_group(self):
        return self.coordinator.plan(
            self.requests(),
            epoch_id="epoch-1",
            operator_id="operator",
        )

    def certify_group(self, group_id):
        return self.coordinator.certify_all(
            group_id,
            self.requests(),
        )

    def authorize_group(self, group_id):
        return self.coordinator.authorize_all(
            group_id,
            self.requests(),
        )

    def prepare_group(self, group_id):
        return self.coordinator.prepare_all(
            group_id,
            self.requests(),
        )

    def through_prepared(self):
        planned = self.plan_group()
        certified = self.certify_group(planned.group.group_id)
        authorized = self.authorize_group(planned.group.group_id)
        prepared = self.prepare_group(planned.group.group_id)
        return planned, certified, authorized, prepared

    def foreign_operator(self, namespace="foreign-workflows"):
        return DurableCompactionOperator(
            self.backend,
            self.compaction,
            self.certificates,
            self.authorizations,
            self.executor,
            reservations=self.reservations,
            namespace=namespace,
            clock=lambda: self.now[0],
        )

    def foreign_plan(self, chain_id="journal"):
        operator = self.foreign_operator(
            namespace=f"foreign-{chain_id}-workflows"
        )
        retention = (
            self.journal_retention
            if chain_id == "journal"
            else self.receipt_retention
        )
        chain = (
            self.journal
            if chain_id == "journal"
            else self.receipts
        )
        plan = operator.plan(
            retention,
            chain,
            operator_id="foreign-operator",
        )
        return operator, plan, retention, chain


def test_group_plan_does_not_reserve_chains():
    fixture = Fixture()
    planned = fixture.plan_group()
    assert planned.group.phase is DurableCompactionGroupPhase.PLANNED
    assert fixture.reservations.current("journal") is None
    assert fixture.reservations.current("receipts") is None
    report = fixture.coordinator.inspect(
        planned.group.group_id,
        fixture.requests(),
    )
    assert report.current
    assert report.reasons == ()


def test_group_certification_acquires_every_member_reservation():
    fixture = Fixture()
    planned = fixture.plan_group()
    certified = fixture.certify_group(planned.group.group_id)
    assert certified.group.phase is DurableCompactionGroupPhase.CERTIFIED

    for chain_id in ("journal", "receipts"):
        item = fixture.reservations.current(chain_id)
        assert item is not None
        assert item.holder_id == planned.group.group_id
        assert item.reservation.operator_id == "operator"
        assert item.reservation.generation == 1


def test_group_reservation_holder_matches_persisted_group_id():
    fixture = Fixture()
    planned = fixture.plan_group()
    fixture.certify_group(planned.group.group_id)
    ids = {
        fixture.reservations.current(chain).holder_id
        for chain in ("journal", "receipts")
    }
    assert ids == {planned.group.group_id}


def test_group_certification_renews_nothing_on_same_phase_retry():
    fixture = Fixture()
    planned = fixture.plan_group()
    fixture.certify_group(planned.group.group_id)
    before = {
        chain: fixture.reservations.current(chain)
        for chain in ("journal", "receipts")
    }
    fixture.certify_group(planned.group.group_id)
    after = {
        chain: fixture.reservations.current(chain)
        for chain in ("journal", "receipts")
    }
    assert after == before


def test_group_authorization_renews_member_reservations():
    fixture = Fixture()
    planned = fixture.plan_group()
    fixture.certify_group(planned.group.group_id)
    before = {
        chain: fixture.reservations.current(chain).reservation.generation
        for chain in ("journal", "receipts")
    }
    fixture.authorize_group(planned.group.group_id)
    after = {
        chain: fixture.reservations.current(chain).reservation.generation
        for chain in ("journal", "receipts")
    }
    assert before == {"journal": 1, "receipts": 1}
    assert after == {"journal": 2, "receipts": 2}


def test_group_preparation_renews_member_reservations():
    fixture = Fixture()
    planned = fixture.plan_group()
    fixture.certify_group(planned.group.group_id)
    fixture.authorize_group(planned.group.group_id)
    fixture.prepare_group(planned.group.group_id)
    assert (
        fixture.reservations.current("journal").reservation.generation
        == 3
    )
    assert (
        fixture.reservations.current("receipts").reservation.generation
        == 3
    )


def test_group_execution_renews_then_releases_reservations():
    fixture = Fixture()
    planned, _, _, _ = fixture.through_prepared()
    completed = fixture.coordinator.execute(
        planned.group.group_id,
        fixture.requests(),
    )
    assert completed.group.complete
    for chain in ("journal", "receipts"):
        assert fixture.reservations.current(chain) is None
        status = fixture.reservations.status(chain)
        assert status.released
        assert not status.active


def test_group_completion_leaves_chains_available():
    fixture = Fixture()
    planned, _, _, _ = fixture.through_prepared()
    fixture.coordinator.execute(
        planned.group.group_id,
        fixture.requests(),
    )
    fixture.reservations.assert_available("journal")
    fixture.reservations.assert_available("receipts")


def test_foreign_operator_can_plan_while_group_holds_reservation():
    fixture = Fixture()
    planned = fixture.plan_group()
    fixture.certify_group(planned.group.group_id)
    operator, foreign_plan, _, _ = fixture.foreign_plan("journal")
    assert foreign_plan.stored.workflow.chain_id == "journal"
    assert operator.reservations is fixture.reservations


def test_foreign_operator_cannot_certify_reserved_chain():
    fixture = Fixture()
    planned = fixture.plan_group()
    fixture.certify_group(planned.group.group_id)
    operator, foreign_plan, retention, chain = fixture.foreign_plan("journal")

    with pytest.raises(
        DurableCompactionWorkflowStale,
        match="reserved",
    ):
        operator.certify(
            foreign_plan.workflow_id,
            retention,
            chain,
        )


def test_foreign_operator_cannot_use_group_holder_with_wrong_operator_identity():
    fixture = Fixture()
    planned = fixture.plan_group()
    fixture.certify_group(planned.group.group_id)
    operator, foreign_plan, retention, chain = fixture.foreign_plan("journal")

    with pytest.raises(
        DurableCompactionWorkflowStale,
        match="reservation",
    ):
        operator.certify(
            foreign_plan.workflow_id,
            retention,
            chain,
            reservation_holder_id=planned.group.group_id,
        )


def test_group_member_operator_can_use_exact_group_holder():
    fixture = Fixture()
    planned = fixture.plan_group()
    fixture.reservations.acquire_many(
        ("journal", "receipts"),
        holder_id=planned.group.group_id,
        operator_id="operator",
    )
    journal_member = next(
        member
        for member in planned.group.members
        if member.chain_id == "journal"
    )
    certificate = fixture.operator.certify(
        journal_member.workflow_id,
        fixture.journal_retention,
        fixture.journal,
        reservation_holder_id=planned.group.group_id,
    )
    assert certificate.certificate.chain_id == "journal"


def test_single_chain_operator_is_blocked_at_authority_boundary():
    fixture = Fixture()
    operator, foreign_plan, retention, chain = fixture.foreign_plan("journal")
    fixture.reservations.acquire(
        "journal",
        holder_id="group-owner",
        operator_id="group-operator",
    )

    with pytest.raises(DurableCompactionWorkflowStale):
        operator.certify(
            foreign_plan.workflow_id,
            retention,
            chain,
        )


def test_group_certification_conflict_preflight_leaves_other_chain_unreserved():
    fixture = Fixture()
    planned = fixture.plan_group()
    fixture.reservations.acquire(
        "receipts",
        holder_id="other-group",
        operator_id="other-operator",
    )

    with pytest.raises(
        DurableCompactionGroupStale,
        match="reservation",
    ):
        fixture.certify_group(planned.group.group_id)

    assert fixture.reservations.current("journal") is None
    assert (
        fixture.reservations.current("receipts").holder_id
        == "other-group"
    )


def test_group_inspection_reports_lost_reservation_after_certification():
    fixture = Fixture()
    planned = fixture.plan_group()
    fixture.certify_group(planned.group.group_id)
    fixture.reservations.release(
        "journal",
        holder_id=planned.group.group_id,
    )

    report = fixture.coordinator.inspect(
        planned.group.group_id,
        fixture.requests(),
    )
    assert not report.current
    assert any(
        "journal: group reservation status" in reason
        for reason in report.reasons
    )


def test_group_authorization_reacquires_released_reservation_if_still_free():
    fixture = Fixture()
    planned = fixture.plan_group()
    fixture.certify_group(planned.group.group_id)
    fixture.reservations.release(
        "journal",
        holder_id=planned.group.group_id,
    )
    authorized = fixture.authorize_group(planned.group.group_id)
    assert authorized.group.phase is DurableCompactionGroupPhase.AUTHORIZED
    item = fixture.reservations.current("journal")
    assert item is not None
    assert item.holder_id == planned.group.group_id
    assert item.reservation.generation == 2


def test_expired_group_reservations_are_reacquired_before_authorization():
    fixture = Fixture(reservation_ttl=5.0)
    planned = fixture.plan_group()
    fixture.certify_group(planned.group.group_id)
    fixture.now[0] += 6.0

    assert fixture.reservations.current("journal") is None
    assert fixture.reservations.current("receipts") is None

    authorized = fixture.authorize_group(planned.group.group_id)
    assert authorized.group.phase is DurableCompactionGroupPhase.AUTHORIZED
    assert (
        fixture.reservations.current("journal").holder_id
        == planned.group.group_id
    )
    assert (
        fixture.reservations.current("receipts").holder_id
        == planned.group.group_id
    )


def test_competitor_taking_expired_member_blocks_group_recovery():
    fixture = Fixture(reservation_ttl=5.0)
    planned = fixture.plan_group()
    fixture.certify_group(planned.group.group_id)
    fixture.now[0] += 6.0
    fixture.reservations.acquire(
        "receipts",
        holder_id="competitor",
        operator_id="competitor",
    )

    with pytest.raises(DurableCompactionGroupStale):
        fixture.authorize_group(planned.group.group_id)

    assert fixture.reservations.current("journal") is None
    assert (
        fixture.reservations.current("receipts").holder_id
        == "competitor"
    )


def test_partial_commit_retains_active_group_reservations():
    fixture = Fixture(operator_class=FailReceiptOnceOperator)
    planned, _, _, _ = fixture.through_prepared()
    fixture.operator.fail_enabled = True

    with pytest.raises(RuntimeError, match="synthetic reservation"):
        fixture.coordinator.execute(
            planned.group.group_id,
            fixture.requests(),
        )

    group = fixture.coordinator.current(planned.group.group_id).group
    assert group.phase is DurableCompactionGroupPhase.PARTIAL_COMMIT
    assert group.partial_commit
    for chain in ("journal", "receipts"):
        item = fixture.reservations.current(chain)
        assert item is not None
        assert item.holder_id == planned.group.group_id


def test_partial_commit_resume_renews_and_releases_reservations():
    fixture = Fixture(operator_class=FailReceiptOnceOperator)
    planned, _, _, _ = fixture.through_prepared()
    fixture.operator.fail_enabled = True
    with pytest.raises(RuntimeError):
        fixture.coordinator.execute(
            planned.group.group_id,
            fixture.requests(),
        )
    before = {
        chain: fixture.reservations.current(chain).reservation.generation
        for chain in ("journal", "receipts")
    }

    fixture.operator.fail_enabled = False
    completed = fixture.coordinator.resume(
        planned.group.group_id,
        fixture.requests(),
    )
    assert completed.group.complete
    assert all(value >= 4 for value in before.values())
    assert fixture.reservations.current("journal") is None
    assert fixture.reservations.current("receipts") is None


def test_fresh_coordinator_resumes_partial_commit_with_same_reservation_store():
    fixture = Fixture(operator_class=FailReceiptOnceOperator)
    planned, _, _, _ = fixture.through_prepared()
    fixture.operator.fail_enabled = True
    with pytest.raises(RuntimeError):
        fixture.coordinator.execute(
            planned.group.group_id,
            fixture.requests(),
        )
    fixture.operator.fail_enabled = False

    fresh = DurableCompactionGroupCoordinator(
        fixture.backend,
        reservations=fixture.reservations,
        namespace="reserved-groups",
        clock=lambda: fixture.now[0],
    )
    completed = fresh.resume(
        planned.group.group_id,
        fixture.requests(),
    )
    assert completed.group.complete
    assert fixture.reservations.current("journal") is None
    assert fixture.reservations.current("receipts") is None


def test_partial_commit_expiry_and_competitor_takeover_blocks_resume():
    fixture = Fixture(
        operator_class=FailReceiptOnceOperator,
        reservation_ttl=5.0,
    )
    planned, _, _, _ = fixture.through_prepared()
    fixture.operator.fail_enabled = True
    with pytest.raises(RuntimeError):
        fixture.coordinator.execute(
            planned.group.group_id,
            fixture.requests(),
        )
    fixture.now[0] += 6.0
    fixture.reservations.acquire(
        "receipts",
        holder_id="competitor",
        operator_id="competitor",
    )
    fixture.operator.fail_enabled = False

    with pytest.raises(DurableCompactionGroupStale):
        fixture.coordinator.resume(
            planned.group.group_id,
            fixture.requests(),
        )


def test_group_completion_release_does_not_release_foreign_holder():
    fixture = Fixture()
    planned, _, _, _ = fixture.through_prepared()
    # Execute normally. This validates only own reservations are released.
    completed = fixture.coordinator.execute(
        planned.group.group_id,
        fixture.requests(),
    )
    assert completed.group.complete
    competitor = fixture.reservations.acquire(
        "journal",
        holder_id="competitor",
        operator_id="competitor",
    )
    # Repeated complete call must not release the new holder.
    repeated = fixture.coordinator.resume(
        planned.group.group_id,
        fixture.requests(),
    )
    assert repeated.group.complete
    assert (
        fixture.reservations.current("journal")
        == competitor
    )


def test_coordinator_requires_member_operators_share_reservation_store():
    fixture = Fixture()
    unreserved_operator = DurableCompactionOperator(
        fixture.backend,
        fixture.compaction,
        fixture.certificates,
        fixture.authorizations,
        fixture.executor,
        namespace="unreserved-workflows",
        clock=lambda: fixture.now[0],
    )
    requests = (
        DurableCompactionGroupRequest(
            "journal",
            unreserved_operator,
            fixture.journal_retention,
            fixture.journal,
        ),
        DurableCompactionGroupRequest(
            "receipts",
            unreserved_operator,
            fixture.receipt_retention,
            fixture.receipts,
        ),
    )
    with pytest.raises(
        DurableCompactionGroupError,
        match="reservation store",
    ):
        fixture.coordinator.plan(
            requests,
            epoch_id="epoch",
            operator_id="operator",
        )


def test_coordinator_rejects_different_reservation_store_instances():
    fixture = Fixture()
    other_store = DurableCompactionReservationStore(
        fixture.backend,
        signer("other-reservation", b"x"),
        namespace="other-reservations",
    )
    other_operator = DurableCompactionOperator(
        fixture.backend,
        fixture.compaction,
        fixture.certificates,
        fixture.authorizations,
        fixture.executor,
        reservations=other_store,
        namespace="other-reservation-workflows",
    )
    requests = (
        DurableCompactionGroupRequest(
            "journal",
            other_operator,
            fixture.journal_retention,
            fixture.journal,
        ),
        DurableCompactionGroupRequest(
            "receipts",
            other_operator,
            fixture.receipt_retention,
            fixture.receipts,
        ),
    )
    with pytest.raises(
        DurableCompactionGroupError,
        match="reservation store",
    ):
        fixture.coordinator.plan(
            requests,
            epoch_id="epoch",
            operator_id="operator",
        )


def test_operator_inspection_reports_foreign_reservation():
    fixture = Fixture()
    operator, foreign_plan, retention, chain = fixture.foreign_plan("journal")
    fixture.reservations.acquire(
        "journal",
        holder_id="group",
        operator_id="operator",
    )
    report = operator.inspect(
        foreign_plan.workflow_id,
        retention,
        chain,
    )
    assert not report.current
    assert any(
        "reserved by another" in reason
        for reason in report.reasons
    )


def test_operator_inspection_accepts_matching_reservation_holder():
    fixture = Fixture()
    planned = fixture.plan_group()
    fixture.certify_group(planned.group.group_id)
    member = next(
        item
        for item in planned.group.members
        if item.chain_id == "journal"
    )
    report = fixture.operator.inspect(
        member.workflow_id,
        fixture.journal_retention,
        fixture.journal,
        reservation_holder_id=planned.group.group_id,
    )
    assert report.current


def test_group_inspection_is_current_after_certification_with_reservations():
    fixture = Fixture()
    planned = fixture.plan_group()
    fixture.certify_group(planned.group.group_id)
    report = fixture.coordinator.inspect(
        planned.group.group_id,
        fixture.requests(),
    )
    assert report.current
    assert report.reasons == ()


def test_group_inspection_is_current_after_preparation_with_reservations():
    fixture = Fixture()
    planned, _, _, prepared = fixture.through_prepared()
    report = fixture.coordinator.inspect(
        planned.group.group_id,
        fixture.requests(),
    )
    assert prepared.group.phase is DurableCompactionGroupPhase.PREPARED
    assert report.current
    assert report.safe_to_execute


def test_reservations_do_not_grant_destructive_authority():
    fixture = Fixture()
    planned = fixture.plan_group()
    fixture.certify_group(planned.group.group_id)
    for chain in ("journal", "receipts"):
        item = fixture.reservations.current(chain)
        assert item is not None
        assert not item.destructive_action_authorized
        assert (
            item.to_dict()["destructive_action_authorized"]
            is False
        )


def test_complete_group_reservations_have_monotonic_generations():
    fixture = Fixture()
    planned = fixture.plan_group()
    fixture.certify_group(planned.group.group_id)
    generation_1 = fixture.reservations.status("journal").generation
    fixture.authorize_group(planned.group.group_id)
    generation_2 = fixture.reservations.status("journal").generation
    fixture.prepare_group(planned.group.group_id)
    generation_3 = fixture.reservations.status("journal").generation
    fixture.coordinator.execute(
        planned.group.group_id,
        fixture.requests(),
    )
    released = fixture.reservations.status("journal")

    assert generation_1 == 1
    assert generation_2 == 2
    assert generation_3 == 3
    assert released.generation == 4
    assert released.released


def test_out_of_band_operator_can_proceed_after_group_releases_reservation_lane():
    fixture = Fixture()
    planned, _, _, _ = fixture.through_prepared()
    fixture.coordinator.execute(
        planned.group.group_id,
        fixture.requests(),
    )
    # The old retention plan is stale after pruning, but reservation ownership
    # itself is no longer the reason an out-of-band operator would be denied.
    fixture.reservations.assert_available("journal")
    fixture.reservations.assert_available("receipts")


def test_reservation_expiry_status_is_visible_to_group_inspection():
    fixture = Fixture(reservation_ttl=5.0)
    planned = fixture.plan_group()
    fixture.certify_group(planned.group.group_id)
    fixture.now[0] += 6.0
    report = fixture.coordinator.inspect(
        planned.group.group_id,
        fixture.requests(),
    )
    assert not report.current
    assert any(
        "reservation status" in reason
        for reason in report.reasons
    )


def test_group_authorization_after_expiry_uses_new_signed_generation():
    fixture = Fixture(reservation_ttl=5.0)
    planned = fixture.plan_group()
    fixture.certify_group(planned.group.group_id)
    old = fixture.reservations.status("journal")
    fixture.now[0] += 6.0
    fixture.authorize_group(planned.group.group_id)
    new = fixture.reservations.status("journal")
    assert new.active
    assert new.generation == old.generation + 1
    assert new.reservation_id != old.reservation_id


def test_group_preparation_fails_if_foreign_holder_takes_expired_chain():
    fixture = Fixture(reservation_ttl=5.0)
    planned = fixture.plan_group()
    fixture.certify_group(planned.group.group_id)
    fixture.authorize_group(planned.group.group_id)
    fixture.now[0] += 6.0
    fixture.reservations.acquire(
        "journal",
        holder_id="foreign",
        operator_id="foreign",
    )
    with pytest.raises(DurableCompactionGroupStale):
        fixture.prepare_group(planned.group.group_id)


def test_direct_member_prepare_requires_group_holder_when_reserved():
    fixture = Fixture()
    planned = fixture.plan_group()
    fixture.certify_group(planned.group.group_id)
    fixture.authorize_group(planned.group.group_id)
    member = next(
        item
        for item in fixture.coordinator.current(
            planned.group.group_id
        ).group.members
        if item.chain_id == "journal"
    )

    with pytest.raises(DurableCompactionWorkflowStale):
        fixture.operator.prepare(
            member.workflow_id,
            fixture.journal_retention,
            fixture.journal,
        )

    prepared = fixture.operator.prepare(
        member.workflow_id,
        fixture.journal_retention,
        fixture.journal,
        reservation_holder_id=planned.group.group_id,
    )
    assert prepared.manifest.chain_id == "journal"


def test_direct_member_execute_requires_group_holder_when_reserved():
    fixture = Fixture()
    planned, _, _, prepared_group = fixture.through_prepared()
    member = next(
        item
        for item in prepared_group.group.members
        if item.chain_id == "journal"
    )

    with pytest.raises(DurableCompactionWorkflowStale):
        fixture.operator.execute(
            member.workflow_id,
            fixture.journal_retention,
            fixture.journal,
        )


def test_group_reservation_status_serializes_owner_and_generation():
    fixture = Fixture()
    planned = fixture.plan_group()
    fixture.certify_group(planned.group.group_id)
    status = fixture.reservations.status("journal").to_dict()
    assert status["active"] is True
    assert status["holder_id"] == planned.group.group_id
    assert status["operator_id"] == "operator"
    assert status["generation"] == 1
    assert len(status["reservation_id"]) == 64
