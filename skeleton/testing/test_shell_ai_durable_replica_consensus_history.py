"""Monotonic durable replica consensus history tests."""

from __future__ import annotations

from dataclasses import replace

import pytest

from skeleton.shells.ai.distributed_journal import (
    DistributedAIDecisionJournal,
)
from skeleton.shells.ai.distributed_state import (
    DistributedStateConflict,
    InMemoryFencedStore,
)
from skeleton.shells.ai.durable_replica_consensus import (
    DurableReplicaConsensusEvaluator,
    DurableReplicaConsensusPolicy,
)
from skeleton.shells.ai.durable_replica_consensus_history import (
    DurableReplicaConsensusEpoch,
    DurableReplicaConsensusEquivocation,
    DurableReplicaConsensusHistoryError,
    DurableReplicaConsensusHistoryHead,
    DurableReplicaConsensusHistoryStore,
    DurableReplicaConsensusRollback,
)
from skeleton.shells.ai.durable_replica_fleet import (
    DurableReplicaFleetMemberReport,
    DurableReplicaFleetReport,
)
from skeleton.shells.ai.durable_replication import (
    DurableChainReplicationReport,
    DurableEvidenceReplicationReport,
    DurableReplicaState,
)
from skeleton.shells.distributed_receipts import (
    DistributedReceiptChain,
)
from skeleton.shells.receipts import ExecutionReceipt


def fp(char: str) -> str:
    return char * 64


def receipt(index: int) -> ExecutionReceipt:
    return ExecutionReceipt(
        command="python",
        correlation_id=f"corr-{index}",
        fingerprint=fp(hex(index % 16)[2:]),
        started_at="2026-09-19T00:00:00+00:00",
        finished_at="2026-09-19T00:00:01+00:00",
        duration_ms=1.0,
        returncode=0,
        ok=True,
        timed_out=False,
        output_limited=False,
        stdout_bytes=index,
        stderr_bytes=0,
        attempt=1,
        receipt_id=f"receipt-{index}",
    )


class Environment:
    def __init__(self, count=2):
        self.now = [100.0]
        self.chain_backend = InMemoryFencedStore()
        self.history_backend = InMemoryFencedStore()
        self.journal = DistributedAIDecisionJournal(
            self.chain_backend,
            namespace="journal",
            clock=lambda: self.now[0],
        )
        self.receipts = DistributedReceiptChain(
            self.chain_backend,
            namespace="receipts",
        )
        self.count = 0
        for _ in range(count):
            self.advance()
        self.evaluator = DurableReplicaConsensusEvaluator(
            DurableReplicaConsensusPolicy(
                min_agreeing_replicas=2,
                min_agreeing_failure_domains=2,
                min_agreement_fraction=2.0 / 3.0,
            )
        )
        self.store = DurableReplicaConsensusHistoryStore(
            self.history_backend,
            namespace="history",
            clock=lambda: self.now[0],
        )

    def advance(self):
        self.count += 1
        index = self.count
        self.journal.append(
            f"event.{index}",
            session_id=f"session-{index}",
            intent_id=f"intent-{index}",
            proposal_id=f"proposal-{index}",
        )
        self.receipts.append(
            receipt(index)
        )

    def chain_report(
        self,
        chain_id,
        sequence,
        root,
    ):
        return DurableChainReplicationReport(
            chain_id,
            DurableReplicaState.IN_SYNC,
            sequence,
            root,
            sequence,
            root,
            0,
            True,
            True,
            None,
            "",
            "",
            fp("p"),
        )

    def replication_report(self):
        journal_head = self.journal.head()
        receipt_head = self.receipts.head()
        return DurableEvidenceReplicationReport(
            self.chain_report(
                "journal",
                journal_head.sequence,
                journal_head.root_hash,
            ),
            self.chain_report(
                "receipts",
                receipt_head.sequence,
                receipt_head.root_hash,
            ),
            fp("p"),
        )

    def consensus_report(
        self,
        *,
        observed_at=None,
        fleet_policy_digest=fp("f"),
    ):
        replication = self.replication_report()
        members = tuple(
            DurableReplicaFleetMemberReport(
                target,
                domain,
                False,
                replication,
                True,
                "",
            )
            for target, domain in (
                ("replica-a", "zone-a"),
                ("replica-b", "zone-b"),
                ("replica-c", "zone-c"),
            )
        )
        fleet = DurableReplicaFleetReport(
            "primary",
            (
                self.now[0]
                if observed_at is None
                else observed_at
            ),
            members,
            (),
            fleet_policy_digest,
            2,
            2,
        )
        return self.evaluator.require_consensus(
            fleet
        )

    def record(self, report=None):
        return self.store.record(
            report or self.consensus_report(),
            journal_chain=self.journal,
            receipt_chain=self.receipts,
        )


def test_first_consensus_creates_generation_one():
    env = Environment()
    report = env.consensus_report()
    stored = env.record(report)
    assert stored.epoch.generation == 1
    assert stored.epoch.previous_digest == ""
    assert stored.current
    assert stored.head.generation == 1
    assert (
        stored.epoch.consensus_state_digest
        == report.state_digest
    )


def test_same_consensus_state_is_idempotent():
    env = Environment()
    report = env.consensus_report()
    first = env.record(report)
    second = env.record(report)
    assert second == first
    assert env.store.lineage("primary") == (
        first.epoch,
    )


def test_observation_time_only_change_is_idempotent():
    env = Environment()
    first_report = env.consensus_report(
        observed_at=100.0,
    )
    second_report = env.consensus_report(
        observed_at=101.0,
    )
    assert (
        first_report.state_digest
        == second_report.state_digest
    )
    first = env.record(first_report)
    env.now[0] = 101.0
    second = env.record(second_report)
    assert second == first


def test_source_growth_creates_next_epoch():
    env = Environment()
    first = env.record()
    env.advance()
    env.now[0] = 101.0
    second = env.record()
    assert second.epoch.generation == 2
    assert (
        second.epoch.previous_digest
        == first.epoch.digest
    )
    assert (
        second.epoch.journal_sequence
        > first.epoch.journal_sequence
    )
    assert (
        second.epoch.receipt_sequence
        > first.epoch.receipt_sequence
    )


def test_same_heads_but_fleet_policy_change_creates_epoch():
    env = Environment()
    first = env.record(
        env.consensus_report(
            fleet_policy_digest=fp("f"),
        )
    )
    env.now[0] = 101.0
    second = env.record(
        env.consensus_report(
            fleet_policy_digest=fp("9"),
        )
    )
    assert second.epoch.generation == 2
    assert (
        second.epoch.journal_root
        == first.epoch.journal_root
    )
    assert (
        second.epoch.fleet_policy_digest
        != first.epoch.fleet_policy_digest
    )


def test_lineage_is_oldest_to_newest():
    env = Environment()
    epochs = [env.record().epoch]
    for index in range(3):
        env.advance()
        env.now[0] += 1
        epochs.append(
            env.record().epoch
        )
    assert env.store.lineage(
        "primary"
    ) == tuple(epochs)


def test_history_verifies_against_live_source_chains():
    env = Environment()
    env.record()
    env.advance()
    env.record()
    env.advance()
    env.record()
    assert env.store.verify(
        "primary",
        journal_chain=env.journal,
        receipt_chain=env.receipts,
    )


def test_empty_history_verifies():
    env = Environment()
    assert env.store.verify(
        "primary",
        journal_chain=env.journal,
        receipt_chain=env.receipts,
    )


def test_require_current_accepts_matching_consensus():
    env = Environment()
    report = env.consensus_report()
    stored = env.record(report)
    required = env.store.require_current(
        report,
        journal_chain=env.journal,
        receipt_chain=env.receipts,
    )
    assert required == stored


def test_require_current_rejects_changed_consensus():
    env = Environment()
    old = env.consensus_report()
    env.record(old)
    env.advance()
    current = env.consensus_report()
    with pytest.raises(
        DurableReplicaConsensusHistoryError,
        match="differs",
    ):
        env.store.require_current(
            current,
            journal_chain=env.journal,
            receipt_chain=env.receipts,
        )


def test_record_requires_certifiable_report():
    env = Environment()
    report = env.consensus_report()
    broken = replace(
        report,
        selected=None,
    )
    with pytest.raises(Exception):
        env.record(broken)


def test_live_chain_must_match_consensus_head():
    env = Environment()
    stale = env.consensus_report()
    env.advance()
    with pytest.raises(
        DurableReplicaConsensusHistoryError,
        match="live head differs",
    ):
        env.record(stale)


def test_lower_journal_sequence_is_rollback():
    env = Environment(count=3)
    first = env.record()
    older_sequence = (
        first.epoch.journal_sequence - 1
    )
    older_root = env.journal.root_for_sequence(
        older_sequence
    )
    selected = first.epoch
    report = env.consensus_report()
    candidate = replace(
        report.selected,
        head=replace(
            report.selected.head,
            journal_sequence=older_sequence,
            journal_root=older_root,
        ),
    )
    rollback = replace(
        report,
        selected=candidate,
        candidates=(candidate,),
        votes=tuple(
            replace(
                vote,
                head=candidate.head,
                target_journal_sequence=older_sequence,
                target_journal_root=older_root,
            )
            for vote in report.votes
        ),
        findings=(),
    )
    # _verify_live_head catches stale live state first, which is also fail-closed.
    with pytest.raises(
        DurableReplicaConsensusHistoryError,
    ):
        env.record(rollback)


def test_lower_receipt_sequence_is_rollback():
    env = Environment(count=3)
    first = env.record()
    older_sequence = (
        first.epoch.receipt_sequence - 1
    )
    older_root = env.receipts.root_for_sequence(
        older_sequence
    )
    report = env.consensus_report()
    candidate = replace(
        report.selected,
        head=replace(
            report.selected.head,
            receipt_sequence=older_sequence,
            receipt_root=older_root,
        ),
    )
    rollback = replace(
        report,
        selected=candidate,
        candidates=(candidate,),
        votes=tuple(
            replace(
                vote,
                head=candidate.head,
                target_receipt_sequence=older_sequence,
                target_receipt_root=older_root,
            )
            for vote in report.votes
        ),
        findings=(),
    )
    with pytest.raises(
        DurableReplicaConsensusHistoryError,
    ):
        env.record(rollback)


def test_same_sequence_different_journal_root_is_equivocation():
    env = Environment()
    first = env.record()
    report = env.consensus_report()
    fake_root = fp("9")
    candidate = replace(
        report.selected,
        head=replace(
            report.selected.head,
            journal_root=fake_root,
        ),
    )
    forged = replace(
        report,
        selected=candidate,
        candidates=(candidate,),
        votes=tuple(
            replace(
                vote,
                head=candidate.head,
                target_journal_root=fake_root,
            )
            for vote in report.votes
        ),
        findings=(),
    )
    # Current live chain refuses the forged root before transition.
    with pytest.raises(
        DurableReplicaConsensusHistoryError,
    ):
        env.record(forged)
    assert (
        env.store.current("primary").epoch
        == first.epoch
    )


def test_history_detects_prior_root_removed_from_source_view():
    env = Environment()
    first = env.record()
    env.advance()
    # Monkey-style wrapper that lies only about historical root resolution.
    class BrokenJournal:
        def head(self):
            return env.journal.head()

        def root_for_sequence(self, sequence):
            if sequence == first.epoch.journal_sequence:
                return fp("9")
            return env.journal.root_for_sequence(
                sequence
            )

    with pytest.raises(
        DurableReplicaConsensusEquivocation,
        match="prior consensus root",
    ):
        env.store.record(
            env.consensus_report(),
            journal_chain=BrokenJournal(),
            receipt_chain=env.receipts,
        )


def test_history_detects_prior_receipt_root_removed_from_source_view():
    env = Environment()
    first = env.record()
    env.advance()

    class BrokenReceipts:
        def head(self):
            return env.receipts.head()

        def root_for_sequence(self, sequence):
            if sequence == first.epoch.receipt_sequence:
                return fp("9")
            return env.receipts.root_for_sequence(
                sequence
            )

    with pytest.raises(
        DurableReplicaConsensusEquivocation,
        match="prior consensus root",
    ):
        env.store.record(
            env.consensus_report(),
            journal_chain=env.journal,
            receipt_chain=BrokenReceipts(),
        )


def test_history_verify_detects_tampered_epoch_payload():
    env = Environment()
    stored = env.record()
    key = env.store._epoch_key(
        stored.epoch.digest
    )
    record = env.history_backend.get(
        env.store.namespace,
        key,
    )
    env.history_backend.compare_and_swap(
        env.store.namespace,
        key,
        expected_revision=record.revision,
        value=replace(
            stored.epoch,
            fleet_state_digest=fp("9"),
        ),
    )
    assert not env.store.verify(
        "primary",
        journal_chain=env.journal,
        receipt_chain=env.receipts,
    )


def test_current_detects_missing_epoch():
    env = Environment()
    stored = env.record()
    key = env.store._epoch_key(
        stored.epoch.digest
    )
    record = env.history_backend.get(
        env.store.namespace,
        key,
    )
    env.history_backend.delete(
        env.store.namespace,
        key,
        expected_revision=record.revision,
    )
    with pytest.raises(
        DurableReplicaConsensusHistoryError,
        match="missing epoch",
    ):
        env.store.current("primary")


def test_current_detects_wrong_head_type():
    backend = InMemoryFencedStore()
    store = DurableReplicaConsensusHistoryStore(
        backend,
        namespace="history",
    )
    backend.put_if_absent(
        "history",
        store._source_key("primary"),
        {"bad": True},
    )
    with pytest.raises(
        DurableReplicaConsensusHistoryError,
        match="head",
    ):
        store.current("primary")


def test_get_epoch_detects_wrong_value_type():
    backend = InMemoryFencedStore()
    store = DurableReplicaConsensusHistoryStore(
        backend,
        namespace="history",
    )
    backend.put_if_absent(
        "history",
        store._epoch_key(fp("a")),
        {"bad": True},
    )
    with pytest.raises(
        DurableReplicaConsensusHistoryError,
        match="value type",
    ):
        store.get_epoch(fp("a"))


def test_lineage_missing_parent_is_detected():
    env = Environment()
    first = env.record()
    env.advance()
    second = env.record()
    first_key = env.store._epoch_key(
        first.epoch.digest
    )
    record = env.history_backend.get(
        env.store.namespace,
        first_key,
    )
    env.history_backend.delete(
        env.store.namespace,
        first_key,
        expected_revision=record.revision,
    )
    with pytest.raises(
        DurableReplicaConsensusHistoryError,
        match="parent epoch is missing",
    ):
        env.store.lineage("primary")
    assert second.epoch.generation == 2


def test_lineage_bound_is_enforced():
    env = Environment()
    env.record()
    env.advance()
    env.record()
    with pytest.raises(
        DurableReplicaConsensusHistoryError,
        match="exceeds bound",
    ):
        env.store.lineage(
            "primary",
            max_epochs=1,
        )


def test_lineage_max_epochs_validation():
    env = Environment()
    for value in (0, True, 100001):
        if value == 100001:
            # Default max is 100000.
            pass
        with pytest.raises(ValueError):
            env.store.lineage(
                "primary",
                max_epochs=value,
            )


def test_epoch_serialization():
    env = Environment()
    epoch = env.record().epoch
    data = epoch.to_dict()
    assert data["source_id"] == "primary"
    assert data["generation"] == 1
    assert len(data["head_digest"]) == 64
    assert len(data["digest"]) == 64


def test_stored_epoch_serialization():
    env = Environment()
    stored = env.record()
    data = stored.to_dict()
    assert data["current"] is True
    assert data["head"]["generation"] == 1
    assert data["epoch"]["generation"] == 1


def test_history_head_validation():
    with pytest.raises(ValueError):
        DurableReplicaConsensusHistoryHead(
            "",
            1,
            fp("a"),
        )
    with pytest.raises(ValueError):
        DurableReplicaConsensusHistoryHead(
            "primary",
            0,
            fp("a"),
        )
    with pytest.raises(ValueError):
        DurableReplicaConsensusHistoryHead(
            "primary",
            1,
            "bad",
        )


def test_epoch_validation_first_generation_has_no_parent():
    env = Environment()
    epoch = env.record().epoch
    with pytest.raises(ValueError, match="first"):
        replace(
            epoch,
            previous_digest=fp("9"),
        )


def test_epoch_validation_later_generation_requires_parent():
    env = Environment()
    env.record()
    env.advance()
    epoch = env.record().epoch
    with pytest.raises(ValueError, match="requires previous"):
        replace(
            epoch,
            previous_digest="",
        )


def test_epoch_requires_sorted_targets():
    env = Environment()
    epoch = env.record().epoch
    with pytest.raises(ValueError, match="sorted"):
        replace(
            epoch,
            agreeing_targets=tuple(
                reversed(
                    epoch.agreeing_targets
                )
            ),
        )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"namespace": ""},
        {"max_cas_retries": 0},
        {"max_cas_retries": 129},
        {"max_lineage_epochs": 0},
        {"max_lineage_epochs": 1_000_001},
        {"clock": object()},
    ],
)
def test_store_configuration_validation(kwargs):
    with pytest.raises((ValueError, TypeError)):
        DurableReplicaConsensusHistoryStore(
            InMemoryFencedStore(),
            **kwargs,
        )


def test_source_key_hides_source_identity():
    key = DurableReplicaConsensusHistoryStore._source_key(
        "sensitive-source"
    )
    assert key.startswith("head:")
    assert "sensitive-source" not in key


def test_epoch_key_is_content_addressed():
    key = DurableReplicaConsensusHistoryStore._epoch_key(
        fp("a")
    )
    assert key == "epoch:" + fp("a")


class ConflictOnceBackend:
    def __init__(self):
        self.store = InMemoryFencedStore()
        self.conflicted = False

    def get(self, namespace, key):
        return self.store.get(namespace, key)

    def put_if_absent(self, namespace, key, value):
        return self.store.put_if_absent(
            namespace,
            key,
            value,
        )

    def compare_and_swap(
        self,
        namespace,
        key,
        *,
        expected_revision,
        value,
    ):
        if (
            key.startswith("head:")
            and not self.conflicted
        ):
            self.conflicted = True
            raise DistributedStateConflict(
                "synthetic history race"
            )
        return self.store.compare_and_swap(
            namespace,
            key,
            expected_revision=expected_revision,
            value=value,
        )

    def delete(
        self,
        namespace,
        key,
        *,
        expected_revision,
    ):
        return self.store.delete(
            namespace,
            key,
            expected_revision=expected_revision,
        )


def test_record_retries_head_cas_conflict():
    env = Environment()
    store = DurableReplicaConsensusHistoryStore(
        ConflictOnceBackend(),
        namespace="history",
        clock=lambda: 100.0,
    )
    report = env.consensus_report()
    stored = store.record(
        report,
        journal_chain=env.journal,
        receipt_chain=env.receipts,
    )
    assert stored.epoch.generation == 1
    assert stored.current


class AlwaysConflictBackend(ConflictOnceBackend):
    def compare_and_swap(
        self,
        namespace,
        key,
        *,
        expected_revision,
        value,
    ):
        if key.startswith("head:"):
            raise DistributedStateConflict(
                "always"
            )
        return self.store.compare_and_swap(
            namespace,
            key,
            expected_revision=expected_revision,
            value=value,
        )


def test_record_honors_cas_retry_bound():
    env = Environment()
    store = DurableReplicaConsensusHistoryStore(
        AlwaysConflictBackend(),
        namespace="history",
        max_cas_retries=2,
        clock=lambda: 100.0,
    )
    with pytest.raises(
        DurableReplicaConsensusHistoryError,
        match="retry budget",
    ):
        store.record(
            env.consensus_report(),
            journal_chain=env.journal,
            receipt_chain=env.receipts,
        )


def test_unreachable_losing_epoch_does_not_enter_lineage():
    # A direct immutable candidate without head linkage is not authoritative.
    env = Environment()
    stored = env.record()
    orphan = replace(
        stored.epoch,
        generation=2,
        previous_digest=stored.epoch.digest,
        recorded_at=101.0,
        fleet_state_digest=fp("9"),
    )
    env.history_backend.put_if_absent(
        env.store.namespace,
        env.store._epoch_key(
            orphan.digest
        ),
        orphan,
    )
    assert env.store.lineage(
        "primary"
    ) == (stored.epoch,)


def test_multiple_sources_have_independent_history_heads():
    env = Environment()
    primary = env.record()
    report = replace(
        env.consensus_report(),
        source_id="secondary",
    )
    secondary = env.store.record(
        report,
        journal_chain=env.journal,
        receipt_chain=env.receipts,
    )
    assert primary.epoch.source_id == "primary"
    assert secondary.epoch.source_id == "secondary"
    assert env.store.current(
        "primary"
    ).epoch.generation == 1
    assert env.store.current(
        "secondary"
    ).epoch.generation == 1


def test_chain_surface_validation():
    env = Environment()

    class Missing:
        pass

    with pytest.raises(
        TypeError,
        match="journal chain",
    ):
        env.store.record(
            env.consensus_report(),
            journal_chain=Missing(),
            receipt_chain=env.receipts,
        )


def test_invalid_history_clock_is_rejected():
    env = Environment()
    store = DurableReplicaConsensusHistoryStore(
        InMemoryFencedStore(),
        clock=lambda: float("nan"),
    )
    with pytest.raises(
        DurableReplicaConsensusHistoryError,
        match="clock",
    ):
        store.record(
            env.consensus_report(),
            journal_chain=env.journal,
            receipt_chain=env.receipts,
        )


def test_head_digest_changes_with_either_chain():
    env = Environment()
    first = env.record().epoch
    changed_journal = replace(
        first,
        journal_root=fp("9"),
    )
    changed_receipt = replace(
        first,
        receipt_root=fp("8"),
    )
    assert first.head_digest != changed_journal.head_digest
    assert first.head_digest != changed_receipt.head_digest


def test_policy_only_epoch_keeps_head_digest():
    env = Environment()
    first = env.record(
        env.consensus_report(
            fleet_policy_digest=fp("f"),
        )
    )
    env.now[0] += 1
    second = env.record(
        env.consensus_report(
            fleet_policy_digest=fp("9"),
        )
    )
    assert (
        first.epoch.head_digest
        == second.epoch.head_digest
    )
    assert first.epoch.digest != second.epoch.digest


def test_verify_detects_head_pointing_to_wrong_generation():
    env = Environment()
    stored = env.record()
    head_key = env.store._source_key(
        "primary"
    )
    record = env.history_backend.get(
        env.store.namespace,
        head_key,
    )
    bad = replace(
        record.value,
        generation=2,
    )
    env.history_backend.compare_and_swap(
        env.store.namespace,
        head_key,
        expected_revision=record.revision,
        value=bad,
    )
    assert not env.store.verify(
        "primary",
        journal_chain=env.journal,
        receipt_chain=env.receipts,
    )
    with pytest.raises(
        DurableReplicaConsensusHistoryError,
    ):
        env.store.current("primary")


def test_record_after_growth_preserves_both_prior_roots():
    env = Environment()
    first = env.record().epoch
    prior_journal = first.journal_root
    prior_receipt = first.receipt_root
    env.advance()
    second = env.record().epoch
    assert (
        env.journal.root_for_sequence(
            first.journal_sequence
        )
        == prior_journal
    )
    assert (
        env.receipts.root_for_sequence(
            first.receipt_sequence
        )
        == prior_receipt
    )
    assert second.generation == 2


def test_record_rejects_chain_head_from_different_live_state():
    env = Environment()
    report = env.consensus_report()

    class WrongJournal:
        def head(self):
            return replace(
                env.journal.head(),
                root_hash=fp("9"),
            )

        def root_for_sequence(self, sequence):
            return env.journal.root_for_sequence(
                sequence
            )

    with pytest.raises(
        DurableReplicaConsensusHistoryError,
        match="live head differs",
    ):
        env.store.record(
            report,
            journal_chain=WrongJournal(),
            receipt_chain=env.receipts,
        )


def test_lineage_serializes_monotonic_generations():
    env = Environment()
    env.record()
    for _ in range(4):
        env.advance()
        env.now[0] += 1
        env.record()
    lineage = env.store.lineage(
        "primary"
    )
    assert tuple(
        epoch.generation
        for epoch in lineage
    ) == (1, 2, 3, 4, 5)
    assert tuple(
        epoch.previous_digest
        for epoch in lineage[1:]
    ) == tuple(
        epoch.digest
        for epoch in lineage[:-1]
    )
