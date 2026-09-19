"""Signed durable backup-manifest and restore-verification integration tests."""

from __future__ import annotations

from dataclasses import replace

import pytest

from skeleton.shells.ai.distributed_journal import (
    DistributedAIDecisionJournal,
    DistributedJournalHead,
)
from skeleton.shells.ai.distributed_state import InMemoryFencedStore
from skeleton.shells.ai.durable_backup_manifest import (
    DurableBackupChainManifest,
    DurableBackupManifestBuilder,
    DurableBackupManifestConflict,
    DurableBackupManifestCorruption,
    DurableBackupManifestPolicy,
    DurableBackupManifestStore,
)
from skeleton.shells.ai.durable_consistency_barrier import (
    DurableConsistencyBarrierCoordinator,
    DurableConsistencyBarrierStore,
)
from skeleton.shells.ai.durable_restore_validation import (
    DurableRestoreChainState,
    DurableRestoreMode,
    DurableRestorePolicy,
    DurableRestoreState,
    DurableRestoreValidationError,
    DurableRestoreVerifier,
)
from skeleton.shells.ai.signed_artifact import ArtifactSigner
from skeleton.shells.distributed_receipts import (
    DistributedReceiptChain,
    DistributedReceiptHead,
)
from skeleton.shells.receipts import ExecutionReceipt


GENESIS = "0" * 64


def fp(char: str) -> str:
    return char * 64


def receipt(
    name: str,
    *,
    attempt: int = 1,
    fingerprint: str | None = None,
) -> ExecutionReceipt:
    return ExecutionReceipt(
        command="python",
        correlation_id=f"corr-{name}",
        fingerprint=fingerprint or fp("e"),
        started_at="2026-09-19T00:00:00+00:00",
        finished_at="2026-09-19T00:00:01+00:00",
        duration_ms=1.0,
        returncode=0,
        ok=True,
        timed_out=False,
        output_limited=False,
        stdout_bytes=1,
        stderr_bytes=0,
        attempt=attempt,
        receipt_id=f"receipt-{name}",
    )


class Environment:
    def __init__(self):
        self.metadata = InMemoryFencedStore()
        self.source = InMemoryFencedStore()
        self.journal = DistributedAIDecisionJournal(
            self.source,
            namespace="journal",
            clock=lambda: 10.0,
        )
        self.receipts = DistributedReceiptChain(
            self.source,
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
        self.coordinator = DurableConsistencyBarrierCoordinator(
            self.barrier_store,
            clock=lambda: 10.0,
        )
        self.builder = DurableBackupManifestBuilder(
            self.barrier_store,
            self.backup_store,
            clock=lambda: 11.0,
        )

    def chains(self):
        return (
            ("journal", self.journal),
            ("receipts", self.receipts),
        )

    def populate(self, count: int = 2):
        for index in range(1, count + 1):
            self.journal.append(
                f"event-{index}",
                session_id=f"session-{index}",
                intent_id=f"intent-{index}",
                proposal_id=f"proposal-{index}",
            )
            self.receipts.append(
                receipt(
                    str(index),
                    attempt=index,
                    fingerprint=(
                        hex(index % 15 + 1)[2:]
                        * 64
                    ),
                )
            )

    def barrier(self, name="nightly"):
        return self.coordinator.capture(
            name,
            self.chains(),
            operator_id="backup-operator",
        ).stored.signed.barrier

    def backup(
        self,
        *,
        backup_name="nightly-backup",
        barrier=None,
    ):
        barrier = barrier or self.barrier()
        return self.builder.build(
            backup_name,
            barrier.barrier_id,
            self.chains(),
            operator_id="backup-operator",
        ).stored.signed.manifest

    def fresh_target(self):
        backend = InMemoryFencedStore()
        return (
            backend,
            DistributedAIDecisionJournal(
                backend,
                namespace="journal",
                clock=lambda: 20.0,
            ),
            DistributedReceiptChain(
                backend,
                namespace="receipts",
            ),
        )

    def restore_exact(
        self,
        manifest,
        journal_target,
        receipt_target,
    ):
        journal_member = manifest.chain(
            "journal"
        )
        receipt_member = manifest.chain(
            "receipts"
        )
        journal_segment = (
            self.journal.snapshot_segment(
                journal_member.segment_start_root,
                journal_member.segment_end_root,
                max_items=100_000,
            )
        )
        receipt_segment = (
            self.receipts.snapshot_segment(
                receipt_member.segment_start_root,
                receipt_member.segment_end_root,
                max_items=100_000,
            )
        )
        journal_target.restore_segment(
            journal_segment,
            max_items=100_000,
        )
        receipt_target.restore_segment(
            receipt_segment,
            max_items=100_000,
        )


def verifier(env, *, policy=None):
    return DurableRestoreVerifier(
        env.barrier_store,
        env.backup_store,
        policy=policy,
    )


def test_build_backup_manifest_from_real_chains():
    env = Environment()
    env.populate(2)
    barrier = env.barrier()
    manifest = env.backup(
        barrier=barrier
    )
    assert manifest.generation == 1
    assert manifest.barrier_id == barrier.barrier_id
    assert manifest.barrier_digest == barrier.digest
    assert manifest.barrier_generation == 1
    assert manifest.atomic_snapshot is False
    assert manifest.restore_authorized is False
    assert [
        item.chain_id
        for item in manifest.chains
    ] == ["journal", "receipts"]


def test_backup_chain_segments_bind_exact_barrier_heads():
    env = Environment()
    env.populate(3)
    barrier = env.barrier()
    manifest = env.backup(
        barrier=barrier
    )
    for chain_id in (
        "journal",
        "receipts",
    ):
        member = manifest.chain(
            chain_id
        )
        barrier_member = barrier.member(
            chain_id
        )
        assert (
            member.barrier_member_digest
            == barrier_member.digest
        )
        assert (
            member.barrier_head_sequence
            == barrier_member.head_sequence
        )
        assert (
            member.barrier_head_root
            == barrier_member.head_root
        )
        assert member.segment_start_sequence == 0
        assert member.segment_start_root == GENESIS
        assert member.segment_item_count == 3
        assert member.prefix_archive_required is False
        assert member.prefix_archive_id == ""


def test_backup_manifest_does_not_authorize_actions():
    env = Environment()
    env.populate(1)
    manifest = env.backup()
    data = manifest.to_dict()
    assert data["atomic_snapshot"] is False
    assert data["restore_authorized"] is False
    assert data["grants_execution_authority"] is False
    assert data["grants_pruning_authority"] is False


def test_second_backup_generation_binds_previous_manifest():
    env = Environment()
    env.populate(1)
    first_barrier = env.barrier()
    first = env.backup(
        barrier=first_barrier
    )
    env.populate(1)
    second_barrier = env.barrier()
    second = env.backup(
        barrier=second_barrier
    )
    assert second.generation == 2
    assert second.previous_manifest_id == first.manifest_id
    assert second.previous_manifest_digest == first.digest


def test_backup_can_target_older_barrier_after_source_advances():
    env = Environment()
    env.populate(2)
    barrier = env.barrier()
    barrier_journal_root = (
        barrier.member("journal").head_root
    )
    env.populate(1)
    assert env.journal.root_hash() != barrier_journal_root
    manifest = env.backup(
        barrier=barrier
    )
    assert (
        manifest.chain("journal").segment_end_root
        == barrier_journal_root
    )
    assert (
        manifest.chain("journal").segment_item_count
        == 2
    )


def test_backup_chain_set_must_match_barrier():
    env = Environment()
    env.populate(1)
    barrier = env.barrier()
    with pytest.raises(
        DurableBackupManifestConflict,
        match="chain set",
    ):
        env.builder.build(
            "backup",
            barrier.barrier_id,
            (("journal", env.journal),),
            operator_id="operator",
        )


def test_backup_rejects_non_ancestor_barrier_root():
    env = Environment()
    env.populate(1)
    barrier = env.barrier()
    member = barrier.member("journal")
    key = env.journal._event_key(
        member.head_root
    )
    record = env.source.get(
        env.journal.namespace,
        key,
    )
    env.source.delete(
        env.journal.namespace,
        key,
        expected_revision=record.revision,
    )
    with pytest.raises(
        DurableBackupManifestConflict,
        match="ancestor",
    ):
        env.backup(
            barrier=barrier
        )


def test_backup_policy_segment_bound():
    env = Environment()
    env.populate(2)
    barrier = env.barrier()
    builder = DurableBackupManifestBuilder(
        env.barrier_store,
        env.backup_store,
        policy=DurableBackupManifestPolicy(
            max_segment_items=1,
        ),
    )
    with pytest.raises(
        DurableBackupManifestConflict,
        match="suffix exceeds",
    ):
        builder.build(
            "bounded",
            barrier.barrier_id,
            env.chains(),
            operator_id="operator",
        )


def test_exact_restore_verifies():
    env = Environment()
    env.populate(3)
    manifest = env.backup()
    _, journal_target, receipt_target = (
        env.fresh_target()
    )
    env.restore_exact(
        manifest,
        journal_target,
        receipt_target,
    )
    report = verifier(env).require_verified(
        manifest.manifest_id,
        (
            ("journal", journal_target),
            ("receipts", receipt_target),
        ),
    )
    assert report.ok
    assert report.state is DurableRestoreState.VERIFIED
    assert all(
        item.state
        is DurableRestoreChainState.VERIFIED
        for item in report.chains
    )
    assert all(
        item.exact_head
        for item in report.chains
    )
    assert all(
        item.segment_digest_match
        for item in report.chains
    )


def test_exact_restore_report_digest_is_stable():
    env = Environment()
    env.populate(2)
    manifest = env.backup()
    _, journal_target, receipt_target = (
        env.fresh_target()
    )
    env.restore_exact(
        manifest,
        journal_target,
        receipt_target,
    )
    restore = verifier(env)
    first = restore.require_verified(
        manifest.manifest_id,
        (
            ("journal", journal_target),
            ("receipts", receipt_target),
        ),
    )
    second = restore.require_verified(
        manifest.manifest_id,
        (
            ("journal", journal_target),
            ("receipts", receipt_target),
        ),
    )
    assert first.digest == second.digest
    assert first == second


def test_missing_restore_chain_is_incomplete():
    env = Environment()
    env.populate(1)
    manifest = env.backup()
    _, journal_target, _ = env.fresh_target()
    journal_segment = env.journal.snapshot_segment(
        GENESIS,
        manifest.chain(
            "journal"
        ).segment_end_root,
    )
    journal_target.restore_segment(
        journal_segment
    )
    report = verifier(env).verify(
        manifest.manifest_id,
        (("journal", journal_target),),
    )
    assert report.state is DurableRestoreState.CORRUPT
    assert any(
        finding.code == "chain_set.missing"
        for finding in report.findings
    )
    receipt_report = next(
        item
        for item in report.chains
        if item.chain_id == "receipts"
    )
    assert (
        receipt_report.state
        is DurableRestoreChainState.INCOMPLETE
    )


def test_extra_restore_chain_is_corrupt_topology():
    env = Environment()
    env.populate(1)
    manifest = env.backup()
    _, journal_target, receipt_target = (
        env.fresh_target()
    )
    env.restore_exact(
        manifest,
        journal_target,
        receipt_target,
    )
    extra = DistributedAIDecisionJournal(
        InMemoryFencedStore(),
        namespace="extra",
    )
    report = verifier(env).verify(
        manifest.manifest_id,
        (
            ("journal", journal_target),
            ("receipts", receipt_target),
            ("extra", extra),
        ),
    )
    assert report.state is DurableRestoreState.CORRUPT
    assert any(
        finding.code == "chain_set.extra"
        for finding in report.findings
    )


def test_rollback_is_incomplete():
    env = Environment()
    env.populate(3)
    manifest = env.backup()
    _, journal_target, receipt_target = (
        env.fresh_target()
    )
    journal_member = manifest.chain(
        "journal"
    )
    journal_partial = env.journal.snapshot_range(
        1,
        2,
    )
    journal_target.restore_segment(
        journal_partial
    )
    receipt_target.restore_segment(
        env.receipts.snapshot_segment(
            GENESIS,
            manifest.chain(
                "receipts"
            ).segment_end_root,
        )
    )
    report = verifier(env).verify(
        manifest.manifest_id,
        (
            ("journal", journal_target),
            ("receipts", receipt_target),
        ),
    )
    journal_report = report.chains[0]
    assert (
        journal_report.state
        is DurableRestoreChainState.INCOMPLETE
    )
    assert any(
        finding.code == "chain.rollback"
        for finding in journal_report.findings
    )
    assert journal_target.length() == 2
    assert journal_member.barrier_head_sequence == 3


def test_same_sequence_different_root_is_diverged():
    env = Environment()
    env.populate(1)
    manifest = env.backup()
    target_backend = InMemoryFencedStore()
    journal_target = DistributedAIDecisionJournal(
        target_backend,
        namespace="journal",
        clock=lambda: 20.0,
    )
    receipt_target = DistributedReceiptChain(
        target_backend,
        namespace="receipts",
    )
    journal_target.append(
        "different",
        session_id="different",
        intent_id="different",
    )
    receipt_target.restore_segment(
        env.receipts.snapshot()
    )
    report = verifier(env).verify(
        manifest.manifest_id,
        (
            ("journal", journal_target),
            ("receipts", receipt_target),
        ),
    )
    journal_report = next(
        item
        for item in report.chains
        if item.chain_id == "journal"
    )
    assert (
        journal_report.state
        is DurableRestoreChainState.DIVERGED
    )
    assert any(
        finding.code
        == "chain.same_sequence_divergence"
        for finding in journal_report.findings
    )


def test_descendant_is_incomplete_in_exact_mode():
    env = Environment()
    env.populate(1)
    manifest = env.backup()
    _, journal_target, receipt_target = (
        env.fresh_target()
    )
    env.restore_exact(
        manifest,
        journal_target,
        receipt_target,
    )
    journal_target.append(
        "later",
        session_id="later",
        intent_id="later",
    )
    report = verifier(env).verify(
        manifest.manifest_id,
        (
            ("journal", journal_target),
            ("receipts", receipt_target),
        ),
        mode=DurableRestoreMode.EXACT_BARRIER,
    )
    journal_report = next(
        item
        for item in report.chains
        if item.chain_id == "journal"
    )
    assert (
        journal_report.state
        is DurableRestoreChainState.INCOMPLETE
    )
    assert journal_report.expected_root_is_ancestor
    assert any(
        finding.code
        == "chain.ahead_of_exact_restore"
        for finding in journal_report.findings
    )


def test_descendant_allowed_mode_accepts_later_appends():
    env = Environment()
    env.populate(1)
    manifest = env.backup()
    _, journal_target, receipt_target = (
        env.fresh_target()
    )
    env.restore_exact(
        manifest,
        journal_target,
        receipt_target,
    )
    journal_target.append(
        "later",
        session_id="later",
        intent_id="later",
    )
    receipt_target.append(
        receipt(
            "later",
            attempt=2,
            fingerprint=fp("f"),
        )
    )
    report = verifier(env).require_verified(
        manifest.manifest_id,
        (
            ("journal", journal_target),
            ("receipts", receipt_target),
        ),
        mode=(
            DurableRestoreMode.DESCENDANT_ALLOWED
        ),
    )
    assert report.ok
    assert all(
        item.expected_root_is_ancestor
        for item in report.chains
    )
    assert all(
        not item.exact_head
        for item in report.chains
    )


def test_descendant_mode_rejects_fork():
    env = Environment()
    env.populate(1)
    manifest = env.backup()
    target_backend = InMemoryFencedStore()
    journal_target = DistributedAIDecisionJournal(
        target_backend,
        namespace="journal",
        clock=lambda: 20.0,
    )
    receipt_target = DistributedReceiptChain(
        target_backend,
        namespace="receipts",
    )
    journal_target.append(
        "fork-one",
        session_id="fork",
        intent_id="fork",
    )
    journal_target.append(
        "fork-two",
        session_id="fork",
        intent_id="fork",
    )
    receipt_target.restore_segment(
        env.receipts.snapshot()
    )
    report = verifier(env).verify(
        manifest.manifest_id,
        (
            ("journal", journal_target),
            ("receipts", receipt_target),
        ),
        mode=(
            DurableRestoreMode.DESCENDANT_ALLOWED
        ),
    )
    journal_report = next(
        item
        for item in report.chains
        if item.chain_id == "journal"
    )
    assert (
        journal_report.state
        is DurableRestoreChainState.DIVERGED
    )
    assert any(
        finding.code == "chain.ancestor_missing"
        for finding in journal_report.findings
    )


def test_corrupt_target_node_is_corrupt():
    env = Environment()
    env.populate(1)
    manifest = env.backup()
    target_backend, journal_target, receipt_target = (
        env.fresh_target()
    )
    env.restore_exact(
        manifest,
        journal_target,
        receipt_target,
    )
    root = journal_target.root_hash()
    key = journal_target._event_key(root)
    record = target_backend.get(
        journal_target.namespace,
        key,
    )
    target_backend.compare_and_swap(
        journal_target.namespace,
        key,
        expected_revision=record.revision,
        value=replace(
            record.value,
            summary="tampered",
        ),
    )
    report = verifier(env).verify(
        manifest.manifest_id,
        (
            ("journal", journal_target),
            ("receipts", receipt_target),
        ),
    )
    journal_report = next(
        item
        for item in report.chains
        if item.chain_id == "journal"
    )
    assert (
        journal_report.state
        is DurableRestoreChainState.CORRUPT
    )
    assert any(
        finding.code == "chain.integrity_failed"
        for finding in journal_report.findings
    )


def test_require_verified_raises_for_invalid_restore():
    env = Environment()
    env.populate(1)
    manifest = env.backup()
    _, journal_target, receipt_target = (
        env.fresh_target()
    )
    with pytest.raises(
        DurableRestoreValidationError,
    ):
        verifier(env).require_verified(
            manifest.manifest_id,
            (
                ("journal", journal_target),
                ("receipts", receipt_target),
            ),
        )


def test_empty_chains_can_be_backed_up_and_restored():
    env = Environment()
    barrier = env.barrier()
    manifest = env.backup(
        barrier=barrier
    )
    assert all(
        item.segment_item_count == 0
        for item in manifest.chains
    )
    _, journal_target, receipt_target = (
        env.fresh_target()
    )
    report = verifier(env).require_verified(
        manifest.manifest_id,
        (
            ("journal", journal_target),
            ("receipts", receipt_target),
        ),
    )
    assert report.ok
    assert all(
        item.expected_sequence == 0
        for item in report.chains
    )


def test_manifest_store_signature_tamper_is_detected():
    env = Environment()
    env.populate(1)
    manifest = env.backup()
    key = env.backup_store._record_key(
        manifest.manifest_id
    )
    record = env.metadata.get(
        env.backup_store.namespace,
        key,
    )
    tampered = replace(
        record.value,
        signature=replace(
            record.value.signature,
            signature="f" * 64,
        ),
    )
    env.metadata.compare_and_swap(
        env.backup_store.namespace,
        key,
        expected_revision=record.revision,
        value=tampered,
    )
    with pytest.raises(
        DurableBackupManifestCorruption,
        match="signature",
    ):
        env.backup_store.get(
            manifest.manifest_id
        )


def test_backup_current_returns_latest_generation():
    env = Environment()
    env.populate(1)
    first = env.backup()
    env.populate(1)
    second = env.backup()
    current = env.backup_store.current(
        "nightly-backup"
    )
    assert current is not None
    assert (
        current.signed.manifest.manifest_id
        == second.manifest_id
    )
    assert second.generation == 2
    assert first.generation == 1


def test_manifest_chain_lookup():
    env = Environment()
    env.populate(1)
    manifest = env.backup()
    assert (
        manifest.chain("journal").chain_id
        == "journal"
    )
    with pytest.raises(KeyError):
        manifest.chain("missing")


@pytest.mark.parametrize(
    "kwargs",
    [
        {"max_chains": 0},
        {"max_segment_items": 0},
        {"require_chain_verify": "yes"},
        {"require_barrier_root_ancestor": "yes"},
        {
            "require_archive_for_compacted_prefix":
            "yes"
        },
    ],
)
def test_backup_policy_validation(kwargs):
    with pytest.raises(ValueError):
        DurableBackupManifestPolicy(
            **kwargs
        )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"max_chains": 0},
        {"max_segment_items": 0},
        {"require_chain_verify": "yes"},
        {"require_segment_digest": "yes"},
        {"require_member_binding": "yes"},
    ],
)
def test_restore_policy_validation(kwargs):
    with pytest.raises(ValueError):
        DurableRestorePolicy(
            **kwargs
        )


def test_backup_chain_manifest_validation():
    with pytest.raises(
        ValueError,
        match="item_count",
    ):
        DurableBackupChainManifest(
            "journal",
            fp("m"),
            2,
            fp("b"),
            False,
            "",
            "",
            0,
            GENESIS,
            2,
            fp("b"),
            1,
            fp("s"),
        )


def test_restore_report_serializes():
    env = Environment()
    env.populate(1)
    manifest = env.backup()
    _, journal_target, receipt_target = (
        env.fresh_target()
    )
    env.restore_exact(
        manifest,
        journal_target,
        receipt_target,
    )
    report = verifier(env).require_verified(
        manifest.manifest_id,
        (
            ("journal", journal_target),
            ("receipts", receipt_target),
        ),
    )
    data = report.to_dict()
    assert data["state"] == "verified"
    assert data["ok"] is True
    assert data["mode"] == "exact_barrier"
    assert data["digest"] == report.digest
    assert len(data["chains"]) == 2


def test_restore_chain_set_duplicate_rejected():
    env = Environment()
    env.populate(1)
    manifest = env.backup()
    _, journal_target, _ = (
        env.fresh_target()
    )
    with pytest.raises(
        ValueError,
        match="duplicate",
    ):
        verifier(env).verify(
            manifest.manifest_id,
            (
                ("journal", journal_target),
                ("journal", journal_target),
            ),
        )


def test_restore_chain_surface_validation():
    env = Environment()
    env.populate(1)
    manifest = env.backup()
    with pytest.raises(
        TypeError,
        match="does not implement",
    ):
        verifier(env).verify(
            manifest.manifest_id,
            (
                ("journal", object()),
                ("receipts", object()),
            ),
        )


def test_manifest_store_namespace_validation():
    env = Environment()
    with pytest.raises(
        ValueError,
        match="namespace",
    ):
        DurableBackupManifestStore(
            env.metadata,
            ArtifactSigner(
                "backup",
                b"m" * 32,
            ),
            namespace="",
        )


def test_manifest_store_signer_validation():
    with pytest.raises(
        TypeError,
        match="signer",
    ):
        DurableBackupManifestStore(
            InMemoryFencedStore(),
            object(),
        )


def test_builder_type_validation():
    env = Environment()
    with pytest.raises(TypeError):
        DurableBackupManifestBuilder(
            object(),
            env.backup_store,
        )
    with pytest.raises(TypeError):
        DurableBackupManifestBuilder(
            env.barrier_store,
            object(),
        )


def test_restore_verifier_type_validation():
    env = Environment()
    with pytest.raises(TypeError):
        DurableRestoreVerifier(
            object(),
            env.backup_store,
        )
    with pytest.raises(TypeError):
        DurableRestoreVerifier(
            env.barrier_store,
            object(),
        )


def test_backup_manifest_segment_digest_changes_with_content():
    env = Environment()
    env.populate(1)
    first = env.backup(
        backup_name="first"
    )
    env.populate(1)
    second_barrier = env.barrier(
        name="second-barrier"
    )
    second = env.backup(
        backup_name="second",
        barrier=second_barrier,
    )
    assert (
        first.chain("journal").segment_digest
        != second.chain("journal").segment_digest
    )
    assert (
        first.chain("receipts").segment_digest
        != second.chain("receipts").segment_digest
    )


def test_manifest_generation_is_scoped_by_backup_name():
    env = Environment()
    env.populate(1)
    one = env.backup(
        backup_name="one"
    )
    two = env.backup(
        backup_name="two"
    )
    assert one.generation == 1
    assert two.generation == 1


def test_restore_descendant_segment_digest_still_matches_barrier_prefix():
    env = Environment()
    env.populate(2)
    manifest = env.backup()
    _, journal_target, receipt_target = (
        env.fresh_target()
    )
    env.restore_exact(
        manifest,
        journal_target,
        receipt_target,
    )
    journal_target.append(
        "later",
        session_id="later",
        intent_id="later",
    )
    report = verifier(env).verify(
        manifest.manifest_id,
        (
            ("journal", journal_target),
            ("receipts", receipt_target),
        ),
        mode=(
            DurableRestoreMode.DESCENDANT_ALLOWED
        ),
    )
    journal_report = next(
        item
        for item in report.chains
        if item.chain_id == "journal"
    )
    assert journal_report.segment_available
    assert journal_report.segment_verified
    assert journal_report.segment_digest_match


def test_manifest_head_to_missing_record_is_corrupt():
    env = Environment()
    env.metadata.put_if_absent(
        env.backup_store.namespace,
        env.backup_store._head_key(
            "missing"
        ),
        type(
            "Fake",
            (),
            {},
        )(),
    )
    with pytest.raises(
        DurableBackupManifestCorruption,
        match="head",
    ):
        env.backup_store.head("missing")


def test_source_and_target_roots_equal_after_exact_restore():
    env = Environment()
    env.populate(4)
    manifest = env.backup()
    _, journal_target, receipt_target = (
        env.fresh_target()
    )
    env.restore_exact(
        manifest,
        journal_target,
        receipt_target,
    )
    assert (
        journal_target.root_hash()
        == manifest.chain(
            "journal"
        ).barrier_head_root
    )
    assert (
        receipt_target.root_hash()
        == manifest.chain(
            "receipts"
        ).barrier_head_root
    )


def test_restore_mode_validation():
    env = Environment()
    env.populate(1)
    manifest = env.backup()
    _, journal_target, receipt_target = (
        env.fresh_target()
    )
    with pytest.raises(ValueError):
        verifier(env).verify(
            manifest.manifest_id,
            (
                ("journal", journal_target),
                ("receipts", receipt_target),
            ),
            mode="invalid",
        )
