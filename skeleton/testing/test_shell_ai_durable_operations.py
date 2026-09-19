"""Durable evidence operations diagnostics and service gate tests."""

from __future__ import annotations

from dataclasses import replace
import sys

import pytest

from skeleton.shells.ai.catalog import AIToolCatalog
from skeleton.shells.ai.compiler import AIPlanCompiler
from skeleton.shells.ai.critic import AIPlanCritic
from skeleton.shells.ai.diagnostics import AIShellDiagnostics
from skeleton.shells.ai.distributed_journal import DistributedAIDecisionJournal
from skeleton.shells.ai.distributed_state import InMemoryFencedStore
from skeleton.shells.ai.durable_checkpoint import DurableChainCheckpointStore
from skeleton.shells.ai.durable_health import (
    DurableRecoveryHealthGuard,
    DurableRecoveryHealthPolicy,
)
from skeleton.shells.ai.durable_operations import (
    DurableChainOperationalState,
    DurableChainOperationsReport,
    DurableEvidenceOperationsError,
    DurableEvidenceOperationsInspector,
    DurableEvidenceOperationsReport,
    DurableOperationsFinding,
    DurableOperationsPolicy,
    DurableOperationsSeverity,
)
from skeleton.shells.ai.durable_recovery import (
    DurableRecoveryStatus,
    DurableSessionRecoveryReport,
    DurableSessionRecoveryVerifier,
)
from skeleton.shells.ai.durable_retention import (
    DurableRetentionPlanner,
    DurableRetentionPolicy,
    DurableRetentionState,
)
from skeleton.shells.ai.effects import (
    EffectContract,
    EffectKind,
    EffectRegistry,
)
from skeleton.shells.ai.governance import AIShellGovernance
from skeleton.shells.ai.lifecycle import AIServicePhase
from skeleton.shells.ai.model_port import CallableAIModelPort
from skeleton.shells.ai.orchestrator import AIShellOrchestrator
from skeleton.shells.ai.planner import AIPlanner
from skeleton.shells.ai.policy import AIShellPolicy, AutonomyMode
from skeleton.shells.ai.policy_store import AIPolicyStore
from skeleton.shells.ai.protocol import AIModelResponse
from skeleton.shells.ai.router import AIToolRouter
from skeleton.shells.ai.service import AIShellService
from skeleton.shells.ai.signed_artifact import ArtifactSigner
from skeleton.shells.ai.types import AIAction, AIIntent, AIPlanProposal
from skeleton.shells.arguments import ArgumentPolicy
from skeleton.shells.commands import CommandCatalog, CommandDefinition
from skeleton.shells.distributed_receipts import DistributedReceiptChain
from skeleton.shells.executor import ShellExecutor
from skeleton.shells.receipts import ExecutionReceipt
from skeleton.shells.registry import ExecutableSpec
from skeleton.shells.runner import ShellPolicy, ShellRunner
from skeleton.shells.shell_service import ShellService


def fp(value: str) -> str:
    import hashlib

    return hashlib.sha256(value.encode()).hexdigest()


def signer() -> ArtifactSigner:
    return ArtifactSigner(
        "checkpoint-key",
        b"k" * 32,
        clock=lambda: 100.0,
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
        stdout_bytes=1,
        stderr_bytes=0,
        attempt=1,
        receipt_id=f"receipt-{index}",
    )


def append_events(
    chain: DistributedAIDecisionJournal,
    count: int,
) -> None:
    for index in range(count):
        chain.append(
            "ops.event",
            session_id=f"session-{index}",
            intent_id=f"intent-{index}",
            proposal_id=f"proposal-{index}",
            summary=f"event {index}",
        )


def fixture(
    *,
    journal_capacity=20,
    receipt_capacity=20,
    retention_policy=None,
    operations_policy=None,
    recovery_health=None,
):
    backend = InMemoryFencedStore()
    journal = DistributedAIDecisionJournal(
        backend,
        namespace="journal",
        max_events=journal_capacity,
        clock=lambda: 10.0,
    )
    receipts = DistributedReceiptChain(
        backend,
        namespace="receipts",
        max_receipts=receipt_capacity,
    )
    checkpoints = DurableChainCheckpointStore(
        backend,
        signer(),
        namespace="checkpoints",
        clock=lambda: 100.0,
    )
    retention = DurableRetentionPlanner(
        checkpoints,
        retention_policy
        or DurableRetentionPolicy(
            minimum_live_tail=2,
            minimum_archive_batch=1,
            target_utilization=0.50,
            warning_utilization=0.70,
            critical_utilization=0.90,
        ),
    )
    inspector = DurableEvidenceOperationsInspector(
        checkpoints,
        retention,
        recovery_health=recovery_health,
        policy=operations_policy,
    )
    return (
        backend,
        journal,
        receipts,
        checkpoints,
        retention,
        inspector,
    )


def test_default_operations_policy():
    policy = DurableOperationsPolicy()
    assert policy.block_capacity_critical
    assert not policy.require_checkpoint_above_warning
    assert not policy.require_recovery_health
    assert policy.max_findings == 512


def test_operations_policy_digest_is_stable():
    first = DurableOperationsPolicy(
        block_capacity_critical=False,
        require_checkpoint_above_warning=True,
        require_recovery_health=True,
        max_findings=42,
    )
    second = DurableOperationsPolicy(
        block_capacity_critical=False,
        require_checkpoint_above_warning=True,
        require_recovery_health=True,
        max_findings=42,
    )
    assert first.digest == second.digest
    assert len(first.digest) == 64


@pytest.mark.parametrize(
    "field,value",
    [
        ("block_capacity_critical", 1),
        ("require_checkpoint_above_warning", "yes"),
        ("require_recovery_health", 1),
    ],
)
def test_operations_policy_boolean_validation(field, value):
    values = dict(
        block_capacity_critical=True,
        require_checkpoint_above_warning=False,
        require_recovery_health=False,
    )
    values[field] = value
    with pytest.raises(ValueError, match="bool"):
        DurableOperationsPolicy(**values)


@pytest.mark.parametrize("value", [0, -1, True, 1.5])
def test_operations_policy_finding_bound(value):
    with pytest.raises(ValueError, match="max_findings"):
        DurableOperationsPolicy(max_findings=value)


def test_finding_accepts_string_severity():
    item = DurableOperationsFinding(
        "warning",
        "code",
        "message",
        "journal",
    )
    assert item.severity is DurableOperationsSeverity.WARNING


@pytest.mark.parametrize(
    "changes",
    [
        {"code": ""},
        {"code": "x" * 129},
        {"message": ""},
        {"message": "x" * 2049},
        {"chain_id": "x" * 129},
    ],
)
def test_finding_validation(changes):
    values = dict(
        severity=DurableOperationsSeverity.INFO,
        code="code",
        message="message",
        chain_id="",
    )
    values.update(changes)
    with pytest.raises(ValueError):
        DurableOperationsFinding(**values)


def test_finding_to_dict():
    item = DurableOperationsFinding(
        DurableOperationsSeverity.ERROR,
        "broken",
        "chain broken",
        "journal",
    )
    assert item.to_dict() == {
        "severity": "error",
        "code": "broken",
        "message": "chain broken",
        "chain_id": "journal",
    }


def test_empty_chain_set_is_rejected():
    *_, inspector = fixture()
    with pytest.raises(ValueError, match="at least one"):
        inspector.inspect(())


def test_duplicate_chain_id_is_rejected():
    _, journal, receipts, _, _, inspector = fixture()
    with pytest.raises(ValueError, match="duplicate"):
        inspector.inspect(
            (
                ("same", journal),
                ("same", receipts),
            )
        )


@pytest.mark.parametrize("chain_id", ["", "x" * 129, 1])
def test_invalid_chain_id_is_rejected(chain_id):
    _, journal, _, _, _, inspector = fixture()
    with pytest.raises(ValueError, match="chain_id"):
        inspector.inspect(((chain_id, journal),))


def test_unknown_protected_root_chain_is_rejected():
    _, journal, _, _, _, inspector = fixture()
    with pytest.raises(ValueError, match="unknown"):
        inspector.inspect(
            (("journal", journal),),
            protected_roots={
                "missing": (fp("root"),),
            },
        )


def test_healthy_empty_journal():
    _, journal, _, _, _, inspector = fixture()
    report = inspector.inspect(
        (("journal", journal),)
    )
    assert report.allowed
    assert report.errors == 0
    assert report.warnings == 0
    chain = report.chains[0]
    assert chain.state is DurableChainOperationalState.HEALTHY
    assert chain.chain_valid
    assert chain.sequence == 0
    assert chain.utilization == 0
    assert chain.latest_checkpoint_digest == ""
    assert chain.checkpoint_valid is None


def test_healthy_two_chains_are_sorted():
    _, journal, receipts, _, _, inspector = fixture()
    report = inspector.inspect(
        (
            ("receipts", receipts),
            ("journal", journal),
        )
    )
    assert tuple(item.chain_id for item in report.chains) == (
        "journal",
        "receipts",
    )
    assert report.allowed


def test_report_digest_is_input_order_independent():
    _, journal, receipts, _, _, inspector = fixture()
    first = inspector.inspect(
        (
            ("journal", journal),
            ("receipts", receipts),
        )
    )
    second = inspector.inspect(
        (
            ("receipts", receipts),
            ("journal", journal),
        )
    )
    assert first.digest == second.digest
    assert first == second


def test_checkpoint_is_verified_in_operations_report():
    _, journal, _, checkpoints, _, inspector = fixture()
    append_events(journal, 2)
    checkpoint = checkpoints.publish(
        "journal",
        journal,
    )
    report = inspector.inspect(
        (("journal", journal),)
    )
    chain = report.chains[0]
    assert chain.latest_checkpoint_digest == checkpoint.checkpoint.digest
    assert chain.checkpoint_valid is True
    assert chain.checkpoint_verification is not None
    assert report.allowed


def test_checkpoint_remains_valid_after_chain_growth():
    _, journal, _, checkpoints, _, inspector = fixture()
    append_events(journal, 2)
    checkpoint = checkpoints.publish(
        "journal",
        journal,
    )
    append_events(journal, 2)
    report = inspector.inspect(
        (("journal", journal),)
    )
    chain = report.chains[0]
    assert chain.checkpoint_valid is True
    assert (
        chain.latest_checkpoint_digest
        == checkpoint.checkpoint.digest
    )
    assert (
        chain.checkpoint_verification.root_is_ancestor
        is True
    )


def test_archive_recommendation_is_warning_not_error():
    _, journal, _, checkpoints, _, inspector = fixture(
        journal_capacity=10,
    )
    append_events(journal, 4)
    checkpoints.publish("journal", journal)
    append_events(journal, 2)
    report = inspector.inspect(
        (("journal", journal),)
    )
    chain = report.chains[0]
    assert chain.retention.state is (
        DurableRetentionState.ARCHIVE_RECOMMENDED
    )
    assert chain.state is DurableChainOperationalState.WARNING
    assert chain.errors == 0
    assert chain.warnings >= 1
    assert report.allowed


def test_checkpoint_required_is_warning_by_default():
    _, journal, _, _, _, inspector = fixture(
        journal_capacity=10,
    )
    append_events(journal, 6)
    report = inspector.inspect(
        (("journal", journal),)
    )
    chain = report.chains[0]
    assert chain.retention.state is (
        DurableRetentionState.CHECKPOINT_REQUIRED
    )
    assert chain.state is DurableChainOperationalState.WARNING
    assert report.allowed


def test_checkpoint_required_above_warning_can_be_error():
    policy = DurableOperationsPolicy(
        require_checkpoint_above_warning=True,
    )
    _, journal, _, _, _, inspector = fixture(
        journal_capacity=10,
        operations_policy=policy,
    )
    append_events(journal, 8)
    report = inspector.inspect(
        (("journal", journal),)
    )
    chain = report.chains[0]
    assert not report.allowed
    assert chain.errors >= 1
    assert any(
        item.code
        == "durable_checkpoint.required_above_warning"
        for item in chain.findings
    )


def test_critical_capacity_blocks_by_default():
    _, journal, _, checkpoints, _, inspector = fixture(
        journal_capacity=10,
    )
    append_events(journal, 7)
    checkpoints.publish("journal", journal)
    append_events(journal, 2)
    report = inspector.inspect(
        (("journal", journal),)
    )
    chain = report.chains[0]
    assert chain.retention.state is (
        DurableRetentionState.CAPACITY_CRITICAL
    )
    assert chain.state is DurableChainOperationalState.INVALID
    assert chain.errors >= 1
    assert not report.allowed


def test_critical_capacity_can_be_warning_by_policy():
    policy = DurableOperationsPolicy(
        block_capacity_critical=False,
    )
    _, journal, _, checkpoints, _, inspector = fixture(
        journal_capacity=10,
        operations_policy=policy,
    )
    append_events(journal, 7)
    checkpoints.publish("journal", journal)
    append_events(journal, 2)
    report = inspector.inspect(
        (("journal", journal),)
    )
    chain = report.chains[0]
    assert chain.state is DurableChainOperationalState.CRITICAL
    assert chain.errors == 0
    assert chain.warnings >= 1
    assert report.allowed


def test_invalid_chain_is_denied():
    backend, journal, _, _, _, inspector = fixture()
    append_events(journal, 1)
    root = journal.root_hash()
    key = journal._event_key(root)
    record = backend.get(
        journal.namespace,
        key,
    )
    backend.compare_and_swap(
        journal.namespace,
        key,
        expected_revision=record.revision,
        value=replace(
            record.value,
            summary="tampered",
        ),
    )
    report = inspector.inspect(
        (("journal", journal),)
    )
    chain = report.chains[0]
    assert not chain.chain_valid
    assert chain.state is DurableChainOperationalState.INVALID
    assert not report.allowed


def test_invalid_checkpoint_registry_is_denied():
    backend, journal, _, checkpoints, _, inspector = fixture()
    append_events(journal, 2)
    checkpoints.publish("journal", journal)
    node = checkpoints._chain.snapshot()[0]
    record = backend.get(
        checkpoints._chain.namespace,
        f"node:{node.node_hash}",
    )
    payload = dict(node.payload)
    signature = dict(payload["signature"])
    signature["signature"] = fp("tampered")
    payload["signature"] = signature
    backend.compare_and_swap(
        checkpoints._chain.namespace,
        f"node:{node.node_hash}",
        expected_revision=record.revision,
        value=replace(
            node,
            payload=payload,
        ),
    )
    report = inspector.inspect(
        (("journal", journal),)
    )
    chain = report.chains[0]
    assert not report.allowed
    assert any(
        item.code
        == "durable_checkpoint.inspect_error"
        for item in chain.findings
    )


def test_invalid_protected_root_surfaces_retention_error():
    _, journal, _, _, _, inspector = fixture()
    append_events(journal, 2)
    report = inspector.inspect(
        (("journal", journal),),
        protected_roots={
            "journal": (fp("missing"),),
        },
    )
    chain = report.chains[0]
    assert not report.allowed
    assert any(
        item.code
        == "durable_retention.inspect_error"
        for item in chain.findings
    )


def test_receipt_chain_operations_report():
    _, _, receipts, checkpoints, _, inspector = fixture(
        receipt_capacity=10,
    )
    for index in range(4):
        receipts.append(receipt(index))
    checkpoints.publish(
        "receipts",
        receipts,
    )
    for index in range(4, 6):
        receipts.append(receipt(index))
    report = inspector.inspect(
        (("receipts", receipts),)
    )
    chain = report.chains[0]
    assert chain.sequence == 6
    assert chain.retention.archive_recommended
    assert chain.warnings >= 1
    assert report.allowed


def test_report_serialization_contains_retention_and_checkpoint():
    _, journal, _, checkpoints, _, inspector = fixture(
        journal_capacity=10,
    )
    append_events(journal, 4)
    checkpoints.publish("journal", journal)
    append_events(journal, 2)
    report = inspector.inspect(
        (("journal", journal),)
    )
    data = report.to_dict()
    chain = data["chains"][0]
    assert data["allowed"] is True
    assert chain["checkpoint_valid"] is True
    assert chain["retention"] is not None
    assert chain["digest"] == report.chains[0].digest
    assert data["digest"] == report.digest


def test_require_returns_allowed_report():
    _, journal, _, _, _, inspector = fixture()
    report = inspector.require(
        (("journal", journal),)
    )
    assert report.allowed


def test_require_raises_when_chain_is_denied():
    _, journal, _, checkpoints, _, inspector = fixture(
        journal_capacity=10,
    )
    append_events(journal, 7)
    checkpoints.publish("journal", journal)
    append_events(journal, 2)
    with pytest.raises(
        DurableEvidenceOperationsError,
    ):
        inspector.require(
            (("journal", journal),)
        )


class StubRecoveryVerifier(DurableSessionRecoveryVerifier):
    def __init__(self, reports):
        self.reports = dict(reports)

    def verify(self, finalization_id):
        return self.reports[finalization_id]


def recovery_report(
    finalization_id: str,
    status: DurableRecoveryStatus,
):
    complete = status is DurableRecoveryStatus.VERIFIED
    return DurableSessionRecoveryReport(
        finalization_id,
        f"session-{finalization_id}",
        status,
        "complete" if complete else "started",
        1,
        1 if complete else None,
        1 if complete else None,
        fp(f"finalization:{finalization_id}") if complete else "",
        fp(f"recovery:{finalization_id}") if complete else "",
        fp(f"session:{finalization_id}") if complete else "",
        fp(f"journal:{finalization_id}") if complete else "",
        fp(f"integrity:{finalization_id}") if complete else "",
        fp(f"signed:{finalization_id}") if complete else "",
        fp(f"jr:{finalization_id}") if complete else "",
        fp(f"rr:{finalization_id}") if complete else "",
        None,
        (),
    )


def recovery_guard(reports, *, max_incomplete=0):
    return DurableRecoveryHealthGuard(
        StubRecoveryVerifier(reports),
        DurableRecoveryHealthPolicy(
            max_incomplete=max_incomplete,
        ),
    )


def test_required_recovery_health_without_guard_is_denied():
    policy = DurableOperationsPolicy(
        require_recovery_health=True,
    )
    _, journal, _, _, _, inspector = fixture(
        operations_policy=policy,
    )
    report = inspector.inspect(
        (("journal", journal),)
    )
    assert not report.allowed
    assert any(
        item.code
        == "durable_recovery.health_required"
        for item in report.findings
    )


def test_recovery_ids_without_guard_are_denied():
    _, journal, _, _, _, inspector = fixture()
    report = inspector.inspect(
        (("journal", journal),),
        recovery_finalization_ids=("a",),
    )
    assert not report.allowed
    assert any(
        item.code
        == "durable_recovery.guard_missing"
        for item in report.findings
    )


def test_verified_recovery_health_is_composed():
    health = recovery_guard(
        {
            "a": recovery_report(
                "a",
                DurableRecoveryStatus.VERIFIED,
            )
        }
    )
    _, journal, _, _, _, inspector = fixture(
        recovery_health=health,
    )
    report = inspector.inspect(
        (("journal", journal),),
        recovery_finalization_ids=("a",),
    )
    assert report.allowed
    assert report.recovery_health is not None
    assert report.recovery_health.verified == 1


def test_recovery_health_warning_is_operations_warning():
    health = recovery_guard(
        {
            "a": recovery_report(
                "a",
                DurableRecoveryStatus.INCOMPLETE,
            )
        },
        max_incomplete=1,
    )
    _, journal, _, _, _, inspector = fixture(
        recovery_health=health,
    )
    report = inspector.inspect(
        (("journal", journal),),
        recovery_finalization_ids=("a",),
    )
    assert report.allowed
    assert report.warnings >= 1
    assert any(
        item.code
        == "durable_recovery.health_warning"
        for item in report.findings
    )


def test_denied_recovery_health_denies_operations():
    health = recovery_guard(
        {
            "a": recovery_report(
                "a",
                DurableRecoveryStatus.INCOMPLETE,
            )
        }
    )
    _, journal, _, _, _, inspector = fixture(
        recovery_health=health,
    )
    report = inspector.inspect(
        (("journal", journal),),
        recovery_finalization_ids=("a",),
    )
    assert not report.allowed
    assert any(
        item.code
        == "durable_recovery.health_denied"
        for item in report.findings
    )


def test_chain_report_digest_stable():
    _, journal, _, _, _, inspector = fixture()
    first = inspector.inspect(
        (("journal", journal),)
    ).chains[0]
    second = inspector.inspect(
        (("journal", journal),)
    ).chains[0]
    assert first.digest == second.digest
    assert first == second


def test_chain_report_digest_changes_when_chain_advances():
    _, journal, _, _, _, inspector = fixture()
    first = inspector.inspect(
        (("journal", journal),)
    ).chains[0]
    append_events(journal, 1)
    second = inspector.inspect(
        (("journal", journal),)
    ).chains[0]
    assert first.digest != second.digest


def test_operations_report_validation_sorted_chains():
    report_a = DurableChainOperationsReport(
        "a",
        DurableChainOperationalState.HEALTHY,
        True,
        0,
        "0" * 64,
        10,
        0.0,
        "",
        None,
        None,
        (),
    )
    report_b = replace(
        report_a,
        chain_id="b",
    )
    with pytest.raises(ValueError, match="sorted"):
        DurableEvidenceOperationsReport(
            fp("policy"),
            (report_b, report_a),
            None,
            (),
        )


def test_operations_report_validation_duplicate_chains():
    item = DurableChainOperationsReport(
        "a",
        DurableChainOperationalState.HEALTHY,
        True,
        0,
        "0" * 64,
        10,
        0.0,
        "",
        None,
        None,
        (),
    )
    with pytest.raises(ValueError, match="duplicate"):
        DurableEvidenceOperationsReport(
            fp("policy"),
            (item, item),
            None,
            (),
        )


def test_chain_report_validation():
    with pytest.raises(ValueError, match="chain_id"):
        DurableChainOperationsReport(
            "",
            DurableChainOperationalState.HEALTHY,
            True,
            0,
            "0" * 64,
            10,
            0.0,
            "",
            None,
            None,
            (),
        )
    with pytest.raises(ValueError, match="root_hash"):
        DurableChainOperationsReport(
            "a",
            DurableChainOperationalState.HEALTHY,
            True,
            0,
            "bad",
            10,
            0.0,
            "",
            None,
            None,
            (),
        )
    with pytest.raises(ValueError, match="capacity"):
        DurableChainOperationsReport(
            "a",
            DurableChainOperationalState.HEALTHY,
            True,
            0,
            "0" * 64,
            0,
            0.0,
            "",
            None,
            None,
            (),
        )


def test_inspector_constructor_validation():
    _, _, _, checkpoints, retention, _ = fixture()
    with pytest.raises(TypeError, match="checkpoints"):
        DurableEvidenceOperationsInspector(
            object(),
            retention,
        )
    with pytest.raises(TypeError, match="retention"):
        DurableEvidenceOperationsInspector(
            checkpoints,
            object(),
        )
    with pytest.raises(TypeError, match="recovery_health"):
        DurableEvidenceOperationsInspector(
            checkpoints,
            retention,
            recovery_health=object(),
        )


class UnknownCapacityChain:
    def head(self):
        return type(
            "Head",
            (),
            {
                "sequence": 0,
                "root_hash": "0" * 64,
            },
        )()

    def verify(self):
        return True

    def verify_root(self, root_hash):
        return True

    def root_is_ancestor(self, root_hash):
        return True

    def snapshot_at(self, root_hash):
        return ()


def test_missing_chain_capacity_is_fail_closed():
    _, _, _, checkpoints, retention, _ = fixture()
    inspector = DurableEvidenceOperationsInspector(
        checkpoints,
        retention,
    )
    report = inspector.inspect(
        (("unknown", UnknownCapacityChain()),)
    )
    chain = report.chains[0]
    assert not report.allowed
    assert chain.state is DurableChainOperationalState.INVALID
    assert chain.errors == 1


def test_protected_root_is_forwarded_to_retention():
    _, journal, _, checkpoints, _, inspector = fixture(
        journal_capacity=10,
    )
    append_events(journal, 2)
    root = journal.root_hash()
    checkpoints.publish(
        "journal",
        journal,
    )
    report = inspector.inspect(
        (("journal", journal),),
        protected_roots={
            "journal": (root,),
        },
    )
    chain = report.chains[0]
    assert chain.retention.protected_roots[0].root_hash == root


def test_finding_bound_is_enforced():
    policy = DurableOperationsPolicy(
        max_findings=1,
    )
    health = recovery_guard(
        {
            "a": recovery_report(
                "a",
                DurableRecoveryStatus.INCOMPLETE,
            )
        },
        max_incomplete=1,
    )
    _, journal, _, _, _, inspector = fixture(
        journal_capacity=10,
        operations_policy=policy,
        recovery_health=health,
    )
    append_events(journal, 6)
    with pytest.raises(
        DurableEvidenceOperationsError,
        match="finding bound",
    ):
        inspector.inspect(
            (("journal", journal),),
            recovery_finalization_ids=("a",),
        )


def command_catalog() -> CommandCatalog:
    return CommandCatalog(
        (
            CommandDefinition(
                ExecutableSpec(
                    "python",
                    sys.executable,
                ),
                ArgumentPolicy.allow_any(),
                description="python",
            ),
        )
    )


def effects() -> EffectRegistry:
    return EffectRegistry(
        (
            EffectContract(
                "python",
                frozenset(
                    {EffectKind.READ_FILESYSTEM}
                ),
                idempotent=True,
                reversible=True,
            ),
        )
    )


def model():
    def propose(request):
        return AIModelResponse(
            request.request_id,
            AIPlanProposal(
                "proposal",
                request.intent.intent_id,
                (
                    AIAction(
                        "step",
                        "python",
                        ("-V",),
                    ),
                ),
                confidence=0.9,
                uncertainty=0.1,
                model_id="model",
            ),
        )

    return CallableAIModelPort(
        "model",
        propose,
    )


def build_service(
    tmp_path,
    *,
    operations_inspector=None,
    operations_chains=(),
    protected_roots=None,
):
    catalog_value = command_catalog()
    effects_value = effects()
    policy = AIShellPolicy(
        autonomy=AutonomyMode.LOW_RISK_AUTONOMOUS,
    )
    model_value = model()
    root = tmp_path / "root"
    root.mkdir()
    shell = ShellService(
        ShellExecutor(
            ShellRunner(
                ShellPolicy(
                    executables={
                        "python": sys.executable
                    },
                    cwd_roots=(root,),
                )
            )
        )
    )
    shell.start()
    tools = AIToolCatalog(catalog_value)
    planner = AIPlanner(
        model_value,
        tools,
        AIToolRouter(
            tools,
            effects_value,
        ),
        policy_fingerprint=policy.fingerprint,
    )
    orchestrator = AIShellOrchestrator(
        planner=planner,
        critic=AIPlanCritic(
            effects_value,
            policy,
        ),
        compiler=AIPlanCompiler(
            effects_value,
        ),
        shell_service=shell,
    )
    return AIShellService(
        orchestrator,
        AIShellDiagnostics(
            tools,
            effects_value,
            policy,
            model_value,
        ),
        AIShellGovernance(
            AIPolicyStore(policy)
        ),
        durable_operations_inspector=operations_inspector,
        durable_operations_chains=tuple(
            operations_chains
        ),
        durable_operations_protected_roots=(
            protected_roots
        ),
    )


def test_service_requires_inspector_for_operations_chains(tmp_path):
    _, journal, _, _, _, _ = fixture()
    with pytest.raises(ValueError, match="require"):
        build_service(
            tmp_path,
            operations_chains=(
                ("journal", journal),
            ),
        )


def test_service_inspector_requires_nonempty_chain_set(tmp_path):
    *_, inspector = fixture()
    with pytest.raises(ValueError, match="at least one chain"):
        build_service(
            tmp_path,
            operations_inspector=inspector,
        )


def test_service_rejects_wrong_operations_inspector(tmp_path):
    _, journal, _, _, _, _ = fixture()
    with pytest.raises(TypeError, match="durable_operations_inspector"):
        build_service(
            tmp_path,
            operations_inspector=object(),
            operations_chains=(
                ("journal", journal),
            ),
        )


def test_service_rejects_malformed_chain_entry(tmp_path):
    *_, inspector = fixture()
    with pytest.raises(ValueError, match="pairs"):
        build_service(
            tmp_path,
            operations_inspector=inspector,
            operations_chains=(
                ("journal",),
            ),
        )


def test_service_rejects_duplicate_chain_id(tmp_path):
    _, journal, receipts, _, _, inspector = fixture()
    with pytest.raises(ValueError, match="duplicate"):
        build_service(
            tmp_path,
            operations_inspector=inspector,
            operations_chains=(
                ("same", journal),
                ("same", receipts),
            ),
        )


def test_service_rejects_unknown_protected_chain(tmp_path):
    _, journal, _, _, _, inspector = fixture()
    with pytest.raises(ValueError, match="unknown"):
        build_service(
            tmp_path,
            operations_inspector=inspector,
            operations_chains=(
                ("journal", journal),
            ),
            protected_roots={
                "missing": (fp("root"),),
            },
        )


def test_service_canonicalizes_operation_chain_order(tmp_path):
    _, journal, receipts, _, _, inspector = fixture()
    service = build_service(
        tmp_path,
        operations_inspector=inspector,
        operations_chains=(
            ("receipts", receipts),
            ("journal", journal),
        ),
    )
    assert tuple(
        item[0]
        for item in service.durable_operations_chains
    ) == ("journal", "receipts")


def test_service_start_allows_healthy_operations(tmp_path):
    _, journal, receipts, _, _, inspector = fixture()
    service = build_service(
        tmp_path,
        operations_inspector=inspector,
        operations_chains=(
            ("journal", journal),
            ("receipts", receipts),
        ),
    )
    diagnostics = service.start()
    assert diagnostics.ok
    assert service.state.phase is AIServicePhase.READY
    status = service.status()
    assert status.durable_operations is not None
    assert status.durable_operations["allowed"] is True


def test_service_start_blocks_critical_capacity(tmp_path):
    _, journal, _, checkpoints, _, inspector = fixture(
        journal_capacity=10,
    )
    append_events(journal, 7)
    checkpoints.publish("journal", journal)
    append_events(journal, 2)
    service = build_service(
        tmp_path,
        operations_inspector=inspector,
        operations_chains=(
            ("journal", journal),
        ),
    )
    service.start()
    assert service.state.phase is AIServicePhase.FAILED
    assert service.status().durable_operations["allowed"] is False


def test_service_start_allows_archive_warning(tmp_path):
    _, journal, _, checkpoints, _, inspector = fixture(
        journal_capacity=10,
    )
    append_events(journal, 4)
    checkpoints.publish("journal", journal)
    append_events(journal, 2)
    service = build_service(
        tmp_path,
        operations_inspector=inspector,
        operations_chains=(
            ("journal", journal),
        ),
    )
    service.start()
    assert service.state.phase is AIServicePhase.READY
    assert service.status().durable_operations["warnings"] >= 1


def test_service_live_chain_corruption_degrades_before_session(tmp_path):
    backend, journal, _, _, _, inspector = fixture()
    append_events(journal, 1)
    service = build_service(
        tmp_path,
        operations_inspector=inspector,
        operations_chains=(
            ("journal", journal),
        ),
    )
    service.start()
    assert service.state.phase is AIServicePhase.READY

    root = journal.root_hash()
    key = journal._event_key(root)
    record = backend.get(journal.namespace, key)
    backend.compare_and_swap(
        journal.namespace,
        key,
        expected_revision=record.revision,
        value=replace(
            record.value,
            summary="tampered",
        ),
    )
    with pytest.raises(
        RuntimeError,
        match="durable evidence operations",
    ):
        service.new_session(
            AIIntent(
                "intent",
                "do work",
            )
        )
    assert service.state.phase is AIServicePhase.DEGRADED


def test_service_live_capacity_growth_can_degrade(tmp_path):
    _, journal, _, checkpoints, _, inspector = fixture(
        journal_capacity=10,
    )
    append_events(journal, 4)
    checkpoints.publish("journal", journal)
    service = build_service(
        tmp_path,
        operations_inspector=inspector,
        operations_chains=(
            ("journal", journal),
        ),
    )
    service.start()
    assert service.state.phase is AIServicePhase.READY

    append_events(journal, 5)
    with pytest.raises(RuntimeError):
        service.new_session(
            AIIntent(
                "intent",
                "do work",
            )
        )
    assert service.state.phase is AIServicePhase.DEGRADED


def test_service_status_omits_operations_when_not_configured(tmp_path):
    service = build_service(tmp_path)
    service.start()
    assert service.status().durable_operations is None


def test_service_status_serialization_includes_operations(tmp_path):
    _, journal, _, _, _, inspector = fixture()
    service = build_service(
        tmp_path,
        operations_inspector=inspector,
        operations_chains=(
            ("journal", journal),
        ),
    )
    service.start()
    data = service.status().to_dict()
    assert data["durable_operations"]["allowed"] is True
    assert data["durable_operations"]["chains"][0]["chain_id"] == "journal"


def test_service_live_archive_warning_does_not_degrade(tmp_path):
    _, journal, _, checkpoints, _, inspector = fixture(
        journal_capacity=10,
    )
    append_events(journal, 4)
    checkpoints.publish("journal", journal)
    service = build_service(
        tmp_path,
        operations_inspector=inspector,
        operations_chains=(
            ("journal", journal),
        ),
    )
    service.start()
    append_events(journal, 2)
    session = service.new_session(
        AIIntent(
            "intent",
            "do work",
        )
    )
    assert session.session_id
    assert service.state.phase is AIServicePhase.READY
    assert service.status().durable_operations["warnings"] >= 1


def test_operations_policy_to_dict():
    policy = DurableOperationsPolicy(
        block_capacity_critical=False,
        require_checkpoint_above_warning=True,
        require_recovery_health=True,
        max_findings=9,
    )
    assert policy.to_dict() == {
        "block_capacity_critical": False,
        "require_checkpoint_above_warning": True,
        "require_recovery_health": True,
        "max_findings": 9,
    }


def test_operations_report_to_dict_without_digest():
    _, journal, _, _, _, inspector = fixture()
    report = inspector.inspect(
        (("journal", journal),)
    )
    assert "digest" not in report.to_dict(
        include_digest=False
    )
    assert "digest" not in report.chains[0].to_dict(
        include_digest=False
    )
