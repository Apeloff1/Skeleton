"""Signed durable recovery drill tests."""

from __future__ import annotations

from dataclasses import replace

import pytest

from skeleton.shells.ai.distributed_journal import (
    DistributedAIDecisionJournal,
)
from skeleton.shells.ai.distributed_state import InMemoryFencedStore
from skeleton.shells.ai.durable_backup_manifest import (
    DurableBackupManifestBuilder,
    DurableBackupManifestStore,
)
from skeleton.shells.ai.durable_consistency_barrier import (
    DurableConsistencyBarrierCoordinator,
    DurableConsistencyBarrierStore,
)
from skeleton.shells.ai.durable_recovery_drill import (
    DurableRecoveryDrillConflict,
    DurableRecoveryDrillCorruption,
    DurableRecoveryDrillOperator,
    DurableRecoveryDrillPolicy,
    DurableRecoveryDrillStore,
)
from skeleton.shells.ai.durable_restore_validation import (
    DurableRestoreMode,
    DurableRestoreVerifier,
)
from skeleton.shells.ai.signed_artifact import ArtifactSigner
from skeleton.shells.distributed_receipts import DistributedReceiptChain
from skeleton.shells.receipts import ExecutionReceipt


def fp(char: str) -> str:
    return char * 64


def receipt(name: str) -> ExecutionReceipt:
    return ExecutionReceipt(
        command="python",
        correlation_id=f"corr-{name}",
        fingerprint=fp("e"),
        started_at="2026-09-19T00:00:00+00:00",
        finished_at="2026-09-19T00:00:01+00:00",
        duration_ms=1.0,
        returncode=0,
        ok=True,
        timed_out=False,
        output_limited=False,
        stdout_bytes=1,
        stderr_bytes=0,
        attempt=1,
        receipt_id=f"receipt-{name}",
    )


class SequenceClock:
    def __init__(self, *values):
        self.values = list(values)
        self.last = (
            float(values[-1])
            if values
            else 0.0
        )

    def __call__(self):
        if self.values:
            self.last = float(
                self.values.pop(0)
            )
        return self.last


class Environment:
    def __init__(self):
        self.metadata = InMemoryFencedStore()
        self.source_backend = InMemoryFencedStore()
        self.source_journal = DistributedAIDecisionJournal(
            self.source_backend,
            namespace="journal",
            clock=lambda: 10.0,
        )
        self.source_receipts = DistributedReceiptChain(
            self.source_backend,
            namespace="receipts",
        )
        self.barrier_store = DurableConsistencyBarrierStore(
            self.metadata,
            ArtifactSigner(
                "barrier",
                b"b" * 32,
                clock=lambda: 10.0,
            ),
            namespace="barriers",
        )
        self.backup_store = DurableBackupManifestStore(
            self.metadata,
            ArtifactSigner(
                "backup",
                b"m" * 32,
                clock=lambda: 11.0,
            ),
            namespace="backups",
        )
        self.drill_store = DurableRecoveryDrillStore(
            self.metadata,
            ArtifactSigner(
                "drill",
                b"d" * 32,
                clock=lambda: 12.0,
            ),
            namespace="drills",
        )
        self.coordinator = DurableConsistencyBarrierCoordinator(
            self.barrier_store,
            clock=lambda: 10.0,
        )
        self.builder = DurableBackupManifestBuilder(
            self.barrier_store,
            self.backup_store,
            clock=lambda: 11.0,
        )
        self.restore = DurableRestoreVerifier(
            self.barrier_store,
            self.backup_store,
        )

    def source_chains(self):
        return (
            ("journal", self.source_journal),
            ("receipts", self.source_receipts),
        )

    def populate(self, name="one"):
        self.source_journal.append(
            f"event-{name}",
            session_id=f"session-{name}",
            intent_id=f"intent-{name}",
        )
        self.source_receipts.append(
            receipt(name)
        )

    def backup(self):
        barrier = self.coordinator.capture(
            "drill-barrier",
            self.source_chains(),
            operator_id="operator",
        ).stored.signed.barrier
        return self.builder.build(
            "drill-backup",
            barrier.barrier_id,
            self.source_chains(),
            operator_id="operator",
        ).stored.signed.manifest

    def target(self, manifest):
        backend = InMemoryFencedStore()
        journal = DistributedAIDecisionJournal(
            backend,
            namespace="journal",
            clock=lambda: 20.0,
        )
        receipts = DistributedReceiptChain(
            backend,
            namespace="receipts",
        )
        journal_member = manifest.chain(
            "journal"
        )
        receipt_member = manifest.chain(
            "receipts"
        )
        journal.restore_segment(
            self.source_journal.snapshot_segment(
                journal_member.segment_start_root,
                journal_member.segment_end_root,
            )
        )
        receipts.restore_segment(
            self.source_receipts.snapshot_segment(
                receipt_member.segment_start_root,
                receipt_member.segment_end_root,
            )
        )
        return backend, journal, receipts

    def operator(
        self,
        *,
        clock=None,
        policy=None,
    ):
        return DurableRecoveryDrillOperator(
            self.backup_store,
            self.restore,
            self.drill_store,
            policy=policy,
            clock=clock or SequenceClock(
                100.0,
                105.0,
            ),
        )


def test_successful_exact_recovery_drill():
    env = Environment()
    env.populate()
    manifest = env.backup()
    _, journal, receipts = env.target(
        manifest
    )
    stored = env.operator().run(
        "weekly",
        manifest.manifest_id,
        source_chains=env.source_chains(),
        restored_chains=(
            ("journal", journal),
            ("receipts", receipts),
        ),
        operator_id="operator",
    )
    drill = stored.signed.drill
    assert drill.success
    assert drill.restore_verified
    assert drill.verification_time_met
    assert drill.sequence_lag_met
    assert drill.duration_seconds == 5.0
    assert drill.max_sequence_lag == 0
    assert drill.generation == 1
    assert not drill.regression
    assert drill.regression_reasons == ()
    assert not drill.restore_performed_by_drill
    assert not drill.destructive_action_authorized


def test_drill_does_not_claim_restore_authority():
    env = Environment()
    env.populate()
    manifest = env.backup()
    _, journal, receipts = env.target(
        manifest
    )
    drill = env.operator().run(
        "weekly",
        manifest.manifest_id,
        source_chains=env.source_chains(),
        restored_chains=(
            ("journal", journal),
            ("receipts", receipts),
        ),
        operator_id="operator",
    ).signed.drill
    data = drill.to_dict()
    assert data["restore_performed_by_drill"] is False
    assert data["destructive_action_authorized"] is False
    assert data["grants_execution_authority"] is False
    assert data["grants_restore_authority"] is False
    assert data["grants_pruning_authority"] is False


def test_source_growth_records_sequence_lag():
    env = Environment()
    env.populate("one")
    manifest = env.backup()
    _, journal, receipts = env.target(
        manifest
    )
    env.populate("two")
    drill = env.operator().run(
        "weekly",
        manifest.manifest_id,
        source_chains=env.source_chains(),
        restored_chains=(
            ("journal", journal),
            ("receipts", receipts),
        ),
        operator_id="operator",
    ).signed.drill
    assert drill.success
    assert drill.max_sequence_lag == 1
    assert all(
        item.sequence_lag == 1
        for item in drill.members
    )
    assert all(
        item.backup_root_is_source_ancestor
        for item in drill.members
    )


def test_sequence_lag_objective_can_fail():
    env = Environment()
    env.populate("one")
    manifest = env.backup()
    _, journal, receipts = env.target(
        manifest
    )
    env.populate("two")
    policy = DurableRecoveryDrillPolicy(
        max_sequence_lag=0,
    )
    drill = env.operator(
        policy=policy
    ).run(
        "weekly",
        manifest.manifest_id,
        source_chains=env.source_chains(),
        restored_chains=(
            ("journal", journal),
            ("receipts", receipts),
        ),
        operator_id="operator",
    ).signed.drill
    assert not drill.sequence_lag_met
    assert not drill.success


def test_verification_time_objective_can_fail():
    env = Environment()
    env.populate()
    manifest = env.backup()
    _, journal, receipts = env.target(
        manifest
    )
    policy = DurableRecoveryDrillPolicy(
        max_verification_seconds=2.0,
    )
    drill = env.operator(
        policy=policy,
        clock=SequenceClock(
            100.0,
            105.0,
        ),
    ).run(
        "weekly",
        manifest.manifest_id,
        source_chains=env.source_chains(),
        restored_chains=(
            ("journal", journal),
            ("receipts", receipts),
        ),
        operator_id="operator",
    ).signed.drill
    assert drill.duration_seconds == 5.0
    assert not drill.verification_time_met
    assert not drill.success


def test_invalid_restore_fails_drill():
    env = Environment()
    env.populate()
    manifest = env.backup()
    backend = InMemoryFencedStore()
    empty_journal = DistributedAIDecisionJournal(
        backend,
        namespace="journal",
    )
    empty_receipts = DistributedReceiptChain(
        backend,
        namespace="receipts",
    )
    drill = env.operator().run(
        "weekly",
        manifest.manifest_id,
        source_chains=env.source_chains(),
        restored_chains=(
            ("journal", empty_journal),
            ("receipts", empty_receipts),
        ),
        operator_id="operator",
    ).signed.drill
    assert not drill.restore_verified
    assert not drill.success
    assert any(
        item.restore_state
        != "verified"
        for item in drill.members
    )


def test_descendant_restore_mode_can_succeed():
    env = Environment()
    env.populate()
    manifest = env.backup()
    _, journal, receipts = env.target(
        manifest
    )
    journal.append(
        "later",
        session_id="later",
        intent_id="later",
    )
    receipts.append(
        receipt("later")
    )
    drill = env.operator().run(
        "weekly",
        manifest.manifest_id,
        source_chains=(
            ("journal", journal),
            ("receipts", receipts),
        ),
        restored_chains=(
            ("journal", journal),
            ("receipts", receipts),
        ),
        operator_id="operator",
        restore_mode=(
            DurableRestoreMode.DESCENDANT_ALLOWED
        ),
    ).signed.drill
    assert drill.success
    assert drill.restore_mode == "descendant_allowed"
    assert all(
        item.restore_expected_root_is_ancestor
        for item in drill.members
    )


def test_exact_mode_marks_ahead_target_failed():
    env = Environment()
    env.populate()
    manifest = env.backup()
    _, journal, receipts = env.target(
        manifest
    )
    journal.append(
        "later",
        session_id="later",
        intent_id="later",
    )
    drill = env.operator().run(
        "weekly",
        manifest.manifest_id,
        source_chains=env.source_chains(),
        restored_chains=(
            ("journal", journal),
            ("receipts", receipts),
        ),
        operator_id="operator",
        restore_mode=(
            DurableRestoreMode.EXACT_BARRIER
        ),
    ).signed.drill
    assert not drill.success
    journal_member = next(
        item
        for item in drill.members
        if item.chain_id == "journal"
    )
    assert (
        journal_member.restore_state
        == "incomplete"
    )


def test_second_drill_binds_previous():
    env = Environment()
    env.populate()
    manifest = env.backup()
    _, journal, receipts = env.target(
        manifest
    )
    first = env.operator(
        clock=SequenceClock(1.0, 2.0)
    ).run(
        "weekly",
        manifest.manifest_id,
        source_chains=env.source_chains(),
        restored_chains=(
            ("journal", journal),
            ("receipts", receipts),
        ),
        operator_id="operator",
    ).signed.drill
    second = env.operator(
        clock=SequenceClock(3.0, 4.0)
    ).run(
        "weekly",
        manifest.manifest_id,
        source_chains=env.source_chains(),
        restored_chains=(
            ("journal", journal),
            ("receipts", receipts),
        ),
        operator_id="operator",
    ).signed.drill
    assert second.generation == 2
    assert second.previous_drill_id == first.drill_id
    assert second.previous_drill_digest == first.digest


def test_duration_regression_is_recorded():
    env = Environment()
    env.populate()
    manifest = env.backup()
    _, journal, receipts = env.target(
        manifest
    )
    env.operator(
        clock=SequenceClock(1.0, 2.0)
    ).run(
        "weekly",
        manifest.manifest_id,
        source_chains=env.source_chains(),
        restored_chains=(
            ("journal", journal),
            ("receipts", receipts),
        ),
        operator_id="operator",
    )
    second = env.operator(
        clock=SequenceClock(3.0, 6.0)
    ).run(
        "weekly",
        manifest.manifest_id,
        source_chains=env.source_chains(),
        restored_chains=(
            ("journal", journal),
            ("receipts", receipts),
        ),
        operator_id="operator",
    ).signed.drill
    assert second.regression
    assert (
        "verification duration increased"
        in second.regression_reasons
    )


def test_sequence_lag_regression_is_recorded():
    env = Environment()
    env.populate("one")
    manifest = env.backup()
    _, journal, receipts = env.target(
        manifest
    )
    env.operator(
        clock=SequenceClock(1.0, 2.0)
    ).run(
        "weekly",
        manifest.manifest_id,
        source_chains=env.source_chains(),
        restored_chains=(
            ("journal", journal),
            ("receipts", receipts),
        ),
        operator_id="operator",
    )
    env.populate("two")
    second = env.operator(
        clock=SequenceClock(3.0, 4.0)
    ).run(
        "weekly",
        manifest.manifest_id,
        source_chains=env.source_chains(),
        restored_chains=(
            ("journal", journal),
            ("receipts", receipts),
        ),
        operator_id="operator",
    ).signed.drill
    assert second.regression
    assert (
        "source-to-backup sequence lag increased"
        in second.regression_reasons
    )


def test_success_to_failure_regression_is_recorded():
    env = Environment()
    env.populate()
    manifest = env.backup()
    _, journal, receipts = env.target(
        manifest
    )
    env.operator(
        clock=SequenceClock(1.0, 2.0)
    ).run(
        "weekly",
        manifest.manifest_id,
        source_chains=env.source_chains(),
        restored_chains=(
            ("journal", journal),
            ("receipts", receipts),
        ),
        operator_id="operator",
    )
    empty_backend = InMemoryFencedStore()
    empty_journal = DistributedAIDecisionJournal(
        empty_backend,
        namespace="journal",
    )
    empty_receipts = DistributedReceiptChain(
        empty_backend,
        namespace="receipts",
    )
    second = env.operator(
        clock=SequenceClock(3.0, 4.0)
    ).run(
        "weekly",
        manifest.manifest_id,
        source_chains=env.source_chains(),
        restored_chains=(
            ("journal", empty_journal),
            ("receipts", empty_receipts),
        ),
        operator_id="operator",
    ).signed.drill
    assert second.regression
    assert (
        "previous successful drill now fails"
        in second.regression_reasons
    )


def test_equal_or_better_second_drill_has_no_regression():
    env = Environment()
    env.populate()
    manifest = env.backup()
    _, journal, receipts = env.target(
        manifest
    )
    env.operator(
        clock=SequenceClock(1.0, 3.0)
    ).run(
        "weekly",
        manifest.manifest_id,
        source_chains=env.source_chains(),
        restored_chains=(
            ("journal", journal),
            ("receipts", receipts),
        ),
        operator_id="operator",
    )
    second = env.operator(
        clock=SequenceClock(4.0, 5.0)
    ).run(
        "weekly",
        manifest.manifest_id,
        source_chains=env.source_chains(),
        restored_chains=(
            ("journal", journal),
            ("receipts", receipts),
        ),
        operator_id="operator",
    ).signed.drill
    assert not second.regression
    assert second.regression_reasons == ()


def test_source_rollback_is_rejected():
    env = Environment()
    env.populate("one")
    env.populate("two")
    manifest = env.backup()
    _, journal, receipts = env.target(
        manifest
    )
    rollback_backend = InMemoryFencedStore()
    rollback_journal = DistributedAIDecisionJournal(
        rollback_backend,
        namespace="journal",
    )
    rollback_receipts = DistributedReceiptChain(
        rollback_backend,
        namespace="receipts",
    )
    rollback_journal.restore_segment(
        env.source_journal.snapshot_range(
            1,
            1,
        )
    )
    rollback_receipts.restore_segment(
        env.source_receipts.snapshot_range(
            1,
            1,
        )
    )
    with pytest.raises(
        DurableRecoveryDrillConflict,
        match="rolled back",
    ):
        env.operator().run(
            "weekly",
            manifest.manifest_id,
            source_chains=(
                ("journal", rollback_journal),
                ("receipts", rollback_receipts),
            ),
            restored_chains=(
                ("journal", journal),
                ("receipts", receipts),
            ),
            operator_id="operator",
        )


def test_source_chain_set_must_match_manifest():
    env = Environment()
    env.populate()
    manifest = env.backup()
    _, journal, receipts = env.target(
        manifest
    )
    with pytest.raises(
        DurableRecoveryDrillConflict,
        match="chain set",
    ):
        env.operator().run(
            "weekly",
            manifest.manifest_id,
            source_chains=(
                ("journal", env.source_journal),
            ),
            restored_chains=(
                ("journal", journal),
                ("receipts", receipts),
            ),
            operator_id="operator",
        )


def test_duplicate_source_chain_rejected():
    env = Environment()
    env.populate()
    manifest = env.backup()
    _, journal, receipts = env.target(
        manifest
    )
    with pytest.raises(
        ValueError,
        match="duplicate",
    ):
        env.operator().run(
            "weekly",
            manifest.manifest_id,
            source_chains=(
                ("journal", env.source_journal),
                ("journal", env.source_journal),
            ),
            restored_chains=(
                ("journal", journal),
                ("receipts", receipts),
            ),
            operator_id="operator",
        )


def test_clock_rollback_is_rejected():
    env = Environment()
    env.populate()
    manifest = env.backup()
    _, journal, receipts = env.target(
        manifest
    )
    with pytest.raises(
        DurableRecoveryDrillConflict,
        match="clock moved backwards",
    ):
        env.operator(
            clock=SequenceClock(
                10.0,
                9.0,
            )
        ).run(
            "weekly",
            manifest.manifest_id,
            source_chains=env.source_chains(),
            restored_chains=(
                ("journal", journal),
                ("receipts", receipts),
            ),
            operator_id="operator",
        )


def test_store_current_returns_latest():
    env = Environment()
    env.populate()
    manifest = env.backup()
    _, journal, receipts = env.target(
        manifest
    )
    env.operator(
        clock=SequenceClock(1.0, 2.0)
    ).run(
        "weekly",
        manifest.manifest_id,
        source_chains=env.source_chains(),
        restored_chains=(
            ("journal", journal),
            ("receipts", receipts),
        ),
        operator_id="operator",
    )
    second = env.operator(
        clock=SequenceClock(3.0, 4.0)
    ).run(
        "weekly",
        manifest.manifest_id,
        source_chains=env.source_chains(),
        restored_chains=(
            ("journal", journal),
            ("receipts", receipts),
        ),
        operator_id="operator",
    )
    current = env.drill_store.current(
        "weekly"
    )
    assert current is not None
    assert (
        current.signed.drill.drill_id
        == second.signed.drill.drill_id
    )


def test_signature_tamper_is_detected():
    env = Environment()
    env.populate()
    manifest = env.backup()
    _, journal, receipts = env.target(
        manifest
    )
    stored = env.operator().run(
        "weekly",
        manifest.manifest_id,
        source_chains=env.source_chains(),
        restored_chains=(
            ("journal", journal),
            ("receipts", receipts),
        ),
        operator_id="operator",
    )
    drill_id = stored.signed.drill.drill_id
    key = env.drill_store._record_key(
        drill_id
    )
    record = env.metadata.get(
        env.drill_store.namespace,
        key,
    )
    env.metadata.compare_and_swap(
        env.drill_store.namespace,
        key,
        expected_revision=record.revision,
        value=replace(
            record.value,
            signature=replace(
                record.value.signature,
                signature="f" * 64,
            ),
        ),
    )
    with pytest.raises(
        DurableRecoveryDrillCorruption,
        match="signature",
    ):
        env.drill_store.get(
            drill_id
        )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"max_chains": 0},
        {"max_verification_seconds": 0},
        {"max_sequence_lag": -1},
        {"require_restore_verified": "yes"},
        {"require_source_ancestry": "yes"},
    ],
)
def test_policy_validation(kwargs):
    with pytest.raises(ValueError):
        DurableRecoveryDrillPolicy(
            **kwargs
        )


def test_policy_digest_is_stable():
    assert (
        DurableRecoveryDrillPolicy().digest
        == DurableRecoveryDrillPolicy().digest
    )


def test_store_namespace_validation():
    with pytest.raises(
        ValueError,
        match="namespace",
    ):
        DurableRecoveryDrillStore(
            InMemoryFencedStore(),
            ArtifactSigner(
                "drill",
                b"d" * 32,
            ),
            namespace="",
        )


def test_store_signer_validation():
    with pytest.raises(
        TypeError,
        match="signer",
    ):
        DurableRecoveryDrillStore(
            InMemoryFencedStore(),
            object(),
        )


def test_operator_type_validation():
    env = Environment()
    with pytest.raises(TypeError):
        DurableRecoveryDrillOperator(
            object(),
            env.restore,
            env.drill_store,
        )
    with pytest.raises(TypeError):
        DurableRecoveryDrillOperator(
            env.backup_store,
            object(),
            env.drill_store,
        )
    with pytest.raises(TypeError):
        DurableRecoveryDrillOperator(
            env.backup_store,
            env.restore,
            object(),
        )


def test_invalid_operator_id_rejected():
    env = Environment()
    env.populate()
    manifest = env.backup()
    _, journal, receipts = env.target(
        manifest
    )
    with pytest.raises(
        ValueError,
        match="operator_id",
    ):
        env.operator().run(
            "weekly",
            manifest.manifest_id,
            source_chains=env.source_chains(),
            restored_chains=(
                ("journal", journal),
                ("receipts", receipts),
            ),
            operator_id="",
        )


def test_invalid_drill_name_rejected():
    env = Environment()
    env.populate()
    manifest = env.backup()
    _, journal, receipts = env.target(
        manifest
    )
    with pytest.raises(
        ValueError,
        match="drill_name",
    ):
        env.operator().run(
            "",
            manifest.manifest_id,
            source_chains=env.source_chains(),
            restored_chains=(
                ("journal", journal),
                ("receipts", receipts),
            ),
            operator_id="operator",
        )


def test_drill_serialization_contains_objectives():
    env = Environment()
    env.populate()
    manifest = env.backup()
    _, journal, receipts = env.target(
        manifest
    )
    drill = env.operator().run(
        "weekly",
        manifest.manifest_id,
        source_chains=env.source_chains(),
        restored_chains=(
            ("journal", journal),
            ("receipts", receipts),
        ),
        operator_id="operator",
    ).signed.drill
    data = drill.to_dict()
    assert data["success"] is True
    assert data["verification_time_met"] is True
    assert data["sequence_lag_met"] is True
    assert data["max_sequence_lag"] == 0
    assert data["digest"] == drill.digest
    assert len(data["members"]) == 2
