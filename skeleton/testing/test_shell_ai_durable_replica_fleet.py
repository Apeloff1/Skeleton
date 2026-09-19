"""Durable replica fleet quorum and failure-domain tests."""

from __future__ import annotations

import pytest

from skeleton.shells.ai.distributed_journal import DistributedAIDecisionJournal
from skeleton.shells.ai.distributed_state import InMemoryFencedStore
from skeleton.shells.ai.durable_replica_fleet import (
    DurableReplicaFleet,
    DurableReplicaFleetError,
    DurableReplicaFleetFinding,
    DurableReplicaFleetMember,
    DurableReplicaFleetMemberReport,
    DurableReplicaFleetMemberRun,
    DurableReplicaFleetPolicy,
    DurableReplicaFleetReport,
    DurableReplicaFleetRun,
)
from skeleton.shells.ai.durable_replication import (
    DurableChainReplicator,
    DurableEvidenceReplicaManager,
    DurableReplicationPolicy,
)
from skeleton.shells.distributed_receipts import DistributedReceiptChain
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


class FleetEnvironment:
    def __init__(self, *, count=3):
        self.now = [100.0]
        self.source_backend = InMemoryFencedStore()
        self.source_journal = DistributedAIDecisionJournal(
            self.source_backend,
            namespace="journal",
            clock=lambda: self.now[0],
        )
        self.source_receipts = DistributedReceiptChain(
            self.source_backend,
            namespace="receipts",
        )
        for index in range(1, count + 1):
            self.source_journal.append(
                f"event.{index}",
                session_id=f"session-{index}",
                intent_id=f"intent-{index}",
                proposal_id=f"proposal-{index}",
            )
            self.source_receipts.append(
                receipt(index)
            )
        self.targets = {}
        self.members = {}
        self.managers = {}
        for target_id, domain in (
            ("replica-a", "zone-a"),
            ("replica-b", "zone-b"),
            ("replica-c", "zone-a"),
        ):
            backend = InMemoryFencedStore()
            journal = DistributedAIDecisionJournal(
                backend,
                namespace="journal",
                clock=lambda: self.now[0],
            )
            receipts = DistributedReceiptChain(
                backend,
                namespace="receipts",
            )
            policy = DurableReplicationPolicy(
                max_batch_items=2,
                max_batches_per_run=16,
            )
            manager = DurableEvidenceReplicaManager(
                DurableChainReplicator(
                    "journal",
                    self.source_journal,
                    journal,
                    policy=policy,
                ),
                DurableChainReplicator(
                    "receipts",
                    self.source_receipts,
                    receipts,
                    policy=policy,
                ),
                policy=policy,
            )
            self.targets[target_id] = (
                backend,
                journal,
                receipts,
            )
            self.managers[target_id] = manager
            self.members[target_id] = (
                DurableReplicaFleetMember(
                    target_id,
                    domain,
                    manager,
                )
            )

    def fleet(
        self,
        *,
        members=None,
        policy=None,
    ):
        selected = tuple(
            self.members[target_id]
            for target_id in (
                members
                if members is not None
                else (
                    "replica-a",
                    "replica-b",
                    "replica-c",
                )
            )
        )
        return DurableReplicaFleet(
            "primary",
            selected,
            policy=(
                policy
                or DurableReplicaFleetPolicy(
                    min_ready_replicas=2,
                    min_ready_failure_domains=2,
                )
            ),
            clock=lambda: self.now[0],
        )

    def sync(self, target_id):
        return self.managers[target_id].sync()


def test_unsynced_fleet_is_blocked():
    env = FleetEnvironment()
    report = env.fleet().inspect()
    assert not report.quorum_ready
    assert report.blocked
    assert not report.degraded
    assert report.ready_targets == ()
    assert report.ready_failure_domains == ()
    assert len(report.findings) == 2


def test_sync_two_independent_domains_reaches_quorum():
    env = FleetEnvironment()
    env.sync("replica-a")
    env.sync("replica-b")
    report = env.fleet().inspect()
    assert report.quorum_ready
    assert not report.blocked
    assert not report.degraded
    assert set(report.ready_targets) == {
        "replica-a",
        "replica-b",
    }
    assert set(report.ready_failure_domains) == {
        "zone-a",
        "zone-b",
    }


def test_two_ready_replicas_same_domain_do_not_meet_domain_quorum():
    env = FleetEnvironment()
    env.sync("replica-a")
    env.sync("replica-c")
    report = env.fleet().inspect()
    assert not report.quorum_ready
    assert report.degraded
    assert set(report.ready_targets) == {
        "replica-a",
        "replica-c",
    }
    assert report.ready_failure_domains == (
        "zone-a",
    )
    assert any(
        finding.code
        == "failure_domain_quorum.insufficient"
        for finding in report.findings
    )


def test_single_ready_replica_is_degraded_not_blocked():
    env = FleetEnvironment()
    env.sync("replica-a")
    report = env.fleet().inspect()
    assert not report.quorum_ready
    assert report.degraded
    assert not report.blocked
    assert report.ready_targets == (
        "replica-a",
    )


def test_all_three_ready_members_are_quorum_ready():
    env = FleetEnvironment()
    fleet = env.fleet()
    run = fleet.sync_all()
    assert run.quorum_ready
    assert run.errors == 0
    assert set(run.after.ready_targets) == {
        "replica-a",
        "replica-b",
        "replica-c",
    }


def test_required_unready_member_blocks_quorum():
    env = FleetEnvironment()
    env.members["replica-c"] = (
        DurableReplicaFleetMember(
            "replica-c",
            "zone-a",
            env.managers["replica-c"],
            required=True,
        )
    )
    env.sync("replica-a")
    env.sync("replica-b")
    report = env.fleet().inspect()
    assert not report.quorum_ready
    assert not report.required_ready
    assert any(
        finding.code
        == "required_replica.unready"
        for finding in report.findings
    )


def test_required_member_can_be_ignored_by_explicit_policy():
    env = FleetEnvironment()
    env.members["replica-c"] = (
        DurableReplicaFleetMember(
            "replica-c",
            "zone-a",
            env.managers["replica-c"],
            required=True,
        )
    )
    env.sync("replica-a")
    env.sync("replica-b")
    fleet = env.fleet(
        policy=DurableReplicaFleetPolicy(
            min_ready_replicas=2,
            min_ready_failure_domains=2,
            require_all_required_members=False,
        )
    )
    report = fleet.inspect()
    assert report.quorum_ready


def test_member_lag_policy_requires_exact_sync_by_default():
    env = FleetEnvironment()
    manager = env.managers["replica-a"]
    manager.journal.sync(max_batches=1)
    manager.receipts.sync(max_batches=1)
    report = env.fleet(
        members=("replica-a",),
        policy=DurableReplicaFleetPolicy(
            min_ready_replicas=1,
            min_ready_failure_domains=1,
        ),
    ).inspect()
    assert not report.members[0].ready


def test_require_quorum_accepts_ready_fleet():
    env = FleetEnvironment()
    env.sync("replica-a")
    env.sync("replica-b")
    report = env.fleet().require_quorum()
    assert report.quorum_ready


def test_require_quorum_rejects_unready_fleet():
    env = FleetEnvironment()
    with pytest.raises(
        DurableReplicaFleetError,
        match="below policy quorum",
    ):
        env.fleet().require_quorum()


def test_require_quorum_specific_target_must_be_ready():
    env = FleetEnvironment()
    env.sync("replica-a")
    env.sync("replica-b")
    fleet = env.fleet()
    assert fleet.require_quorum(
        target_id="replica-a"
    ).quorum_ready
    with pytest.raises(
        DurableReplicaFleetError,
        match="target is not ready",
    ):
        fleet.require_quorum(
            target_id="replica-c"
        )


def test_require_quorum_rejects_unknown_target():
    env = FleetEnvironment()
    env.sync("replica-a")
    env.sync("replica-b")
    with pytest.raises(
        DurableReplicaFleetError,
        match="not a fleet member",
    ):
        env.fleet().require_quorum(
            target_id="unknown"
        )


def test_eligible_targets_are_deterministic_and_sorted():
    env = FleetEnvironment()
    env.sync("replica-c")
    env.sync("replica-b")
    fleet = env.fleet()
    assert fleet.eligible_targets() == (
        "replica-b",
        "replica-c",
    )


def test_member_report_exposes_replication_state():
    env = FleetEnvironment()
    env.sync("replica-a")
    report = env.fleet(
        members=("replica-a",),
        policy=DurableReplicaFleetPolicy(),
    ).inspect()
    member = report.members[0]
    assert member.ready
    assert member.target_id == "replica-a"
    assert member.failure_domain == "zone-a"
    assert member.replication.promotion_ready
    assert member.reason == ""


def test_unready_member_report_has_reason():
    env = FleetEnvironment()
    report = env.fleet(
        members=("replica-a",),
        policy=DurableReplicaFleetPolicy(),
    ).inspect()
    member = report.members[0]
    assert not member.ready
    assert "not promotion ready" in member.reason


def test_report_member_lookup():
    env = FleetEnvironment()
    report = env.fleet().inspect()
    assert report.member(
        "replica-b"
    ).target_id == "replica-b"
    with pytest.raises(KeyError):
        report.member("missing")


def test_report_serialization_contains_quorum_state():
    env = FleetEnvironment()
    env.sync("replica-a")
    env.sync("replica-b")
    report = env.fleet().inspect()
    data = report.to_dict()
    assert data["quorum_ready"] is True
    assert set(data["ready_targets"]) == {
        "replica-a",
        "replica-b",
    }
    assert data["digest"] == report.digest
    assert len(report.digest) == 64


def test_report_digest_is_stable_at_same_observation():
    env = FleetEnvironment()
    env.sync("replica-a")
    env.sync("replica-b")
    fleet = env.fleet()
    first = fleet.inspect()
    second = fleet.inspect()
    assert first == second
    assert first.digest == second.digest


def test_report_digest_changes_when_time_changes():
    env = FleetEnvironment()
    fleet = env.fleet()
    first = fleet.inspect()
    env.now[0] += 1.0
    second = fleet.inspect()
    assert first.digest != second.digest


def test_sync_all_populates_all_members():
    env = FleetEnvironment()
    run = env.fleet().sync_all()
    assert len(run.members) == 3
    assert run.transferred_items == 18
    assert run.errors == 0
    assert run.quorum_ready


def test_sync_all_can_be_bounded_per_member():
    env = FleetEnvironment(count=6)
    run = env.fleet().sync_all(
        max_batches=1
    )
    assert not run.quorum_ready
    assert run.errors == 0
    assert all(
        member.run is not None
        for member in run.members
    )
    assert all(
        not member.run.completed
        for member in run.members
    )


class ExplodingManager(DurableEvidenceReplicaManager):
    def sync(self, *, max_batches=None):
        raise RuntimeError("synthetic sync failure")


def test_sync_all_records_member_error_and_continues():
    env = FleetEnvironment()
    original = env.members["replica-c"]
    exploding = ExplodingManager(
        original.manager.journal,
        original.manager.receipts,
        policy=original.manager.policy,
    )
    env.members["replica-c"] = (
        DurableReplicaFleetMember(
            "replica-c",
            "zone-a",
            exploding,
        )
    )
    run = env.fleet().sync_all()
    assert run.errors == 1
    failed = tuple(
        item
        for item in run.members
        if item.target_id == "replica-c"
    )[0]
    assert not failed.ok
    assert failed.error_type == "RuntimeError"
    assert "synthetic" in failed.error_message
    assert run.after.quorum_ready


def test_sync_all_can_fail_fast_by_policy():
    env = FleetEnvironment()
    original = env.members["replica-a"]
    exploding = ExplodingManager(
        original.manager.journal,
        original.manager.receipts,
        policy=original.manager.policy,
    )
    env.members["replica-a"] = (
        DurableReplicaFleetMember(
            "replica-a",
            "zone-a",
            exploding,
        )
    )
    fleet = env.fleet(
        policy=DurableReplicaFleetPolicy(
            min_ready_replicas=2,
            min_ready_failure_domains=2,
            continue_on_sync_error=False,
        )
    )
    with pytest.raises(
        DurableReplicaFleetError,
        match="sync failed",
    ):
        fleet.sync_all()


def test_source_growth_degrades_previously_ready_fleet():
    env = FleetEnvironment()
    fleet = env.fleet()
    fleet.sync_all()
    assert fleet.inspect().quorum_ready
    index = env.source_journal.length() + 1
    env.source_journal.append(
        f"event.{index}",
        session_id="new",
        intent_id="new",
    )
    env.source_receipts.append(
        receipt(index)
    )
    report = fleet.inspect()
    assert report.blocked
    assert not report.quorum_ready


def test_resync_after_source_growth_restores_quorum():
    env = FleetEnvironment()
    fleet = env.fleet()
    fleet.sync_all()
    index = env.source_journal.length() + 1
    env.source_journal.append(
        f"event.{index}",
        session_id="new",
        intent_id="new",
    )
    env.source_receipts.append(
        receipt(index)
    )
    assert not fleet.inspect().quorum_ready
    run = fleet.sync_all()
    assert run.after.quorum_ready


def test_one_replica_can_fall_behind_without_losing_two_replica_quorum():
    env = FleetEnvironment()
    fleet = env.fleet()
    fleet.sync_all()
    index = env.source_journal.length() + 1
    env.source_journal.append(
        f"event.{index}",
        session_id="new",
        intent_id="new",
    )
    env.source_receipts.append(
        receipt(index)
    )
    env.sync("replica-a")
    env.sync("replica-b")
    report = fleet.inspect()
    assert report.quorum_ready
    assert set(report.ready_targets) == {
        "replica-a",
        "replica-b",
    }
    assert not report.member(
        "replica-c"
    ).ready


def test_same_domain_survivors_lose_domain_quorum():
    env = FleetEnvironment()
    fleet = env.fleet()
    fleet.sync_all()
    index = env.source_journal.length() + 1
    env.source_journal.append(
        f"event.{index}",
        session_id="new",
        intent_id="new",
    )
    env.source_receipts.append(
        receipt(index)
    )
    env.sync("replica-a")
    env.sync("replica-c")
    report = fleet.inspect()
    assert not report.quorum_ready
    assert report.degraded


@pytest.mark.parametrize(
    "kwargs",
    [
        {"min_ready_replicas": 0},
        {"min_ready_replicas": 1025},
        {"min_ready_failure_domains": 0},
        {"min_ready_failure_domains": 1025},
        {"max_member_lag_items": -1},
        {"require_all_required_members": "yes"},
        {"continue_on_sync_error": 1},
    ],
)
def test_policy_validation(kwargs):
    with pytest.raises(ValueError):
        DurableReplicaFleetPolicy(**kwargs)


def test_policy_digest_is_stable():
    first = DurableReplicaFleetPolicy(
        min_ready_replicas=2,
        min_ready_failure_domains=2,
    )
    second = DurableReplicaFleetPolicy(
        min_ready_replicas=2,
        min_ready_failure_domains=2,
    )
    assert first.digest == second.digest


def test_member_validation():
    env = FleetEnvironment()
    manager = env.managers["replica-a"]
    with pytest.raises(ValueError):
        DurableReplicaFleetMember(
            "",
            "zone",
            manager,
        )
    with pytest.raises(ValueError):
        DurableReplicaFleetMember(
            "replica",
            "",
            manager,
        )
    with pytest.raises(TypeError):
        DurableReplicaFleetMember(
            "replica",
            "zone",
            object(),
        )
    with pytest.raises(ValueError):
        DurableReplicaFleetMember(
            "replica",
            "zone",
            manager,
            required="yes",
        )


def test_fleet_rejects_duplicate_targets():
    env = FleetEnvironment()
    member = env.members["replica-a"]
    with pytest.raises(
        ValueError,
        match="unique",
    ):
        DurableReplicaFleet(
            "primary",
            (member, member),
        )


def test_fleet_rejects_empty_members():
    with pytest.raises(
        ValueError,
        match="contain members",
    ):
        DurableReplicaFleet(
            "primary",
            (),
        )


def test_fleet_rejects_quorum_above_member_count():
    env = FleetEnvironment()
    with pytest.raises(
        ValueError,
        match="fleet size",
    ):
        env.fleet(
            members=("replica-a",),
            policy=DurableReplicaFleetPolicy(
                min_ready_replicas=2,
            ),
        )


def test_fleet_rejects_domain_quorum_above_unique_domains():
    env = FleetEnvironment()
    with pytest.raises(
        ValueError,
        match="fleet domains",
    ):
        env.fleet(
            members=(
                "replica-a",
                "replica-c",
            ),
            policy=DurableReplicaFleetPolicy(
                min_ready_replicas=1,
                min_ready_failure_domains=2,
            ),
        )


def test_fleet_requires_callable_clock():
    env = FleetEnvironment()
    with pytest.raises(TypeError, match="clock"):
        DurableReplicaFleet(
            "primary",
            tuple(env.members.values()),
            clock=object(),
        )


@pytest.mark.parametrize(
    "clock_value",
    [-1.0, float("inf"), float("nan")],
)
def test_fleet_rejects_invalid_clock_value(clock_value):
    env = FleetEnvironment()
    fleet = DurableReplicaFleet(
        "primary",
        tuple(env.members.values()),
        policy=DurableReplicaFleetPolicy(
            min_ready_replicas=2,
            min_ready_failure_domains=2,
        ),
        clock=lambda: clock_value,
    )
    with pytest.raises(
        DurableReplicaFleetError,
        match="clock",
    ):
        fleet.inspect()


def test_member_run_validation():
    with pytest.raises(ValueError, match="paired"):
        DurableReplicaFleetMemberRun(
            "replica",
            None,
            "Error",
            "",
        )
    with pytest.raises(ValueError, match="successful"):
        env = FleetEnvironment()
        run = env.managers["replica-a"].sync()
        DurableReplicaFleetMemberRun(
            "replica",
            run,
            "Error",
            "message",
        )


def test_finding_validation():
    with pytest.raises(ValueError):
        DurableReplicaFleetFinding(
            "",
            "message",
        )
    with pytest.raises(ValueError):
        DurableReplicaFleetFinding(
            "code",
            "",
        )


def test_fleet_run_serialization():
    env = FleetEnvironment()
    run = env.fleet().sync_all()
    data = run.to_dict()
    assert data["quorum_ready"] is True
    assert data["errors"] == 0
    assert data["digest"] == run.digest
    assert len(run.digest) == 64


def test_member_report_serialization():
    env = FleetEnvironment()
    env.sync("replica-a")
    report = env.fleet(
        members=("replica-a",),
        policy=DurableReplicaFleetPolicy(),
    ).inspect().members[0]
    data = report.to_dict()
    assert data["target_id"] == "replica-a"
    assert data["ready"] is True
    assert data["digest"] == report.digest


def test_required_members_property():
    env = FleetEnvironment()
    env.members["replica-a"] = (
        DurableReplicaFleetMember(
            "replica-a",
            "zone-a",
            env.managers["replica-a"],
            required=True,
        )
    )
    report = env.fleet().inspect()
    assert tuple(
        item.target_id
        for item in report.required_members
    ) == ("replica-a",)
