"""Service admission contracts for durable evidence lifecycle state."""

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
from skeleton.shells.ai.durable_archive import DurableArchiveManifestBuilder
from skeleton.shells.ai.durable_archive_store import DurableArchiveRepository
from skeleton.shells.ai.durable_checkpoint import DurableChainCheckpointStore
from skeleton.shells.ai.durable_compaction import (
    DurableCompactionPlanner,
    DurableCompactionPolicy,
)
from skeleton.shells.ai.durable_lifecycle import (
    DurableEvidenceLifecycleCoordinator,
    DurableLifecycleState,
)
from skeleton.shells.ai.durable_retention import (
    DurableRetentionPlanner,
    DurableRetentionPolicy,
)
from skeleton.shells.ai.effects import EffectContract, EffectKind, EffectRegistry
from skeleton.shells.ai.execution_seal import ExecutionSealAuthority
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
from skeleton.shells.execution_context import ExecutionContext
from skeleton.shells.executor import ShellExecutor
from skeleton.shells.receipts import ExecutionReceipt
from skeleton.shells.registry import ExecutableSpec
from skeleton.shells.runner import ShellPolicy, ShellRunner
from skeleton.shells.shell_service import ShellService


def fp(value: str) -> str:
    import hashlib

    return hashlib.sha256(value.encode()).hexdigest()


def append_events(
    journal: DistributedAIDecisionJournal,
    count: int,
    *,
    start: int = 0,
) -> tuple[object, ...]:
    items = []
    for index in range(start, start + count):
        items.append(
            journal.append(
                "service.lifecycle",
                session_id=f"lifecycle-session-{index}",
                intent_id=f"lifecycle-intent-{index}",
                proposal_id=f"lifecycle-proposal-{index}",
                summary=f"lifecycle event {index}",
            )
        )
    return tuple(items)


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


class LifecycleFixture:
    def __init__(
        self,
        *,
        journal_capacity=10,
        receipt_capacity=10,
        minimum_live_tail=2,
        target_utilization=0.5,
    ):
        self.backend = InMemoryFencedStore()
        self.journal = DistributedAIDecisionJournal(
            self.backend,
            namespace="lifecycle-journal",
            max_events=journal_capacity,
            clock=lambda: 10.0,
        )
        self.receipts = DistributedReceiptChain(
            self.backend,
            namespace="lifecycle-receipts",
            max_receipts=receipt_capacity,
        )
        self.checkpoints = DurableChainCheckpointStore(
            self.backend,
            ArtifactSigner(
                "lifecycle-checkpoints",
                b"c" * 32,
                clock=lambda: 100.0,
            ),
            namespace="lifecycle-checkpoints",
            clock=lambda: 100.0,
        )
        self.retention = DurableRetentionPlanner(
            self.checkpoints,
            DurableRetentionPolicy(
                minimum_live_tail=minimum_live_tail,
                minimum_archive_batch=2,
                target_utilization=target_utilization,
                warning_utilization=max(0.8, target_utilization),
                critical_utilization=0.95,
                max_protected_roots=32,
            ),
        )
        self.archive_signer = ArtifactSigner(
            "lifecycle-archive",
            b"a" * 32,
            clock=lambda: 200.0,
        )
        self.archive_builder = DurableArchiveManifestBuilder(
            self.checkpoints,
            self.archive_signer,
            clock=lambda: 200.0,
        )
        self.archives = DurableArchiveRepository(
            self.backend,
            self.checkpoints,
            self.archive_signer,
            namespace="lifecycle-archives",
            clock=lambda: 300.0,
        )
        self.compaction = DurableCompactionPlanner(
            self.archives,
            DurableCompactionPolicy(
                minimum_live_tail=minimum_live_tail,
                maximum_candidate_nodes=max(
                    journal_capacity,
                    receipt_capacity,
                ),
                max_protected_roots=32,
            ),
        )
        self.coordinator = DurableEvidenceLifecycleCoordinator(
            self.checkpoints,
            self.retention,
            self.archive_builder,
            self.archives,
            self.compaction,
        )

    def archive_checkpoint(
        self,
        chain_id: str,
        chain,
    ):
        checkpoint = self.checkpoints.publish(
            chain_id,
            chain,
        )
        archive = self.archive_builder.build(
            checkpoint,
            chain,
        )
        self.archives.put(
            archive,
            checkpoint,
            chain,
        )
        return checkpoint, archive

    def prepare_journal_ready(self):
        first = append_events(
            self.journal,
            6,
        )
        checkpoint, archive = self.archive_checkpoint(
            "journal",
            self.journal,
        )
        append_events(
            self.journal,
            2,
            start=6,
        )
        report = self.coordinator.inspect(
            "journal",
            self.journal,
        )
        assert (
            report.state
            is DurableLifecycleState.COMPACTION_READY
        )
        return first, checkpoint, archive, report

    def prepare_receipts_ready(self):
        first = tuple(
            self.receipts.append(
                receipt(index)
            )
            for index in range(6)
        )
        checkpoint, archive = self.archive_checkpoint(
            "receipts",
            self.receipts,
        )
        tuple(
            self.receipts.append(
                receipt(index)
            )
            for index in range(6, 8)
        )
        report = self.coordinator.inspect(
            "receipts",
            self.receipts,
        )
        assert (
            report.state
            is DurableLifecycleState.COMPACTION_READY
        )
        return first, checkpoint, archive, report


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
    counter = {"value": 0}

    def propose(request):
        counter["value"] += 1
        suffix = counter["value"]
        return AIModelResponse(
            request.request_id,
            AIPlanProposal(
                f"proposal-{suffix}",
                request.intent.intent_id,
                (
                    AIAction(
                        f"step-{suffix}",
                        "python",
                        (
                            "-c",
                            "print('LIFECYCLE_SERVICE_OK')",
                        ),
                        timeout_seconds=1,
                    ),
                ),
                confidence=0.95,
                uncertainty=0.05,
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
    coordinator=None,
    chains=(),
    protected_roots=None,
    capacities=None,
) -> AIShellService:
    catalog_value = command_catalog()
    effects_value = effects()
    tools = AIToolCatalog(
        catalog_value
    )
    policy = AIShellPolicy(
        autonomy=AutonomyMode.LOW_RISK_AUTONOMOUS,
    )
    model_value = model()
    root = tmp_path / (
        f"root-{abs(hash(tuple(item[0] for item in chains))) % 100000}"
    )
    root.mkdir(
        exist_ok=True,
    )
    shell = ShellService(
        ShellExecutor(
            ShellRunner(
                ShellPolicy(
                    executables={
                        "python": sys.executable,
                    },
                    cwd_roots=(root,),
                    default_timeout=2,
                    max_timeout=4,
                    max_output_bytes=4096,
                    max_input_bytes=4096,
                    max_env_bytes=4096,
                    max_args=32,
                    max_arg_bytes=4096,
                )
            )
        )
    )
    shell.start()
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
        durable_lifecycle_coordinator=coordinator,
        durable_lifecycle_chains=tuple(
            chains
        ),
        durable_lifecycle_protected_roots=(
            protected_roots
        ),
        durable_lifecycle_capacities=(
            capacities
        ),
    )


def intent(
    intent_id="intent",
) -> AIIntent:
    return AIIntent(
        intent_id,
        "execute bounded lifecycle-gated work",
    )


def test_service_without_lifecycle_omits_status(tmp_path):
    service = build_service(
        tmp_path,
    )
    service.start()
    assert service.state.phase is AIServicePhase.READY
    assert service.status().durable_lifecycle is None
    assert (
        "durable_lifecycle"
        not in service.status().to_dict()
    )


def test_lifecycle_chains_require_coordinator(tmp_path):
    fixture = LifecycleFixture()
    with pytest.raises(
        ValueError,
        match="require a durable lifecycle coordinator",
    ):
        build_service(
            tmp_path,
            chains=(
                ("journal", fixture.journal),
            ),
        )


def test_coordinator_requires_nonempty_chain_set(tmp_path):
    fixture = LifecycleFixture()
    with pytest.raises(
        ValueError,
        match="at least one chain",
    ):
        build_service(
            tmp_path,
            coordinator=fixture.coordinator,
        )


def test_wrong_coordinator_type_is_rejected(tmp_path):
    fixture = LifecycleFixture()
    with pytest.raises(
        TypeError,
        match="durable_lifecycle_coordinator",
    ):
        build_service(
            tmp_path,
            coordinator=object(),
            chains=(
                ("journal", fixture.journal),
            ),
        )


def test_malformed_chain_entry_is_rejected(tmp_path):
    fixture = LifecycleFixture()
    with pytest.raises(
        ValueError,
        match="pairs",
    ):
        build_service(
            tmp_path,
            coordinator=fixture.coordinator,
            chains=(("journal",),),
        )


def test_duplicate_chain_id_is_rejected(tmp_path):
    fixture = LifecycleFixture()
    with pytest.raises(
        ValueError,
        match="duplicate durable lifecycle chain_id",
    ):
        build_service(
            tmp_path,
            coordinator=fixture.coordinator,
            chains=(
                ("same", fixture.journal),
                ("same", fixture.receipts),
            ),
        )


@pytest.mark.parametrize(
    "chain_id",
    ["", "x" * 129, 1],
)
def test_invalid_chain_id_is_rejected(tmp_path, chain_id):
    fixture = LifecycleFixture()
    with pytest.raises(
        ValueError,
        match="invalid durable lifecycle chain_id",
    ):
        build_service(
            tmp_path,
            coordinator=fixture.coordinator,
            chains=(
                (chain_id, fixture.journal),
            ),
        )


def test_unknown_protected_chain_is_rejected(tmp_path):
    fixture = LifecycleFixture()
    with pytest.raises(
        ValueError,
        match="protected roots reference unknown chain",
    ):
        build_service(
            tmp_path,
            coordinator=fixture.coordinator,
            chains=(
                ("journal", fixture.journal),
            ),
            protected_roots={
                "missing": (fp("root"),),
            },
        )


def test_duplicate_protected_root_is_rejected(tmp_path):
    fixture = LifecycleFixture()
    value = fp("root")
    with pytest.raises(
        ValueError,
        match="duplicate durable lifecycle protected root",
    ):
        build_service(
            tmp_path,
            coordinator=fixture.coordinator,
            chains=(
                ("journal", fixture.journal),
            ),
            protected_roots={
                "journal": (value, value),
            },
        )


@pytest.mark.parametrize(
    "root",
    ["bad", "", 1],
)
def test_invalid_protected_root_is_rejected(tmp_path, root):
    fixture = LifecycleFixture()
    with pytest.raises(
        ValueError,
        match="invalid durable lifecycle protected root",
    ):
        build_service(
            tmp_path,
            coordinator=fixture.coordinator,
            chains=(
                ("journal", fixture.journal),
            ),
            protected_roots={
                "journal": (root,),
            },
        )


def test_unknown_capacity_chain_is_rejected(tmp_path):
    fixture = LifecycleFixture()
    with pytest.raises(
        ValueError,
        match="capacities reference unknown chain",
    ):
        build_service(
            tmp_path,
            coordinator=fixture.coordinator,
            chains=(
                ("journal", fixture.journal),
            ),
            capacities={
                "missing": 100,
            },
        )


@pytest.mark.parametrize(
    "capacity",
    [0, -1, True, 1.5],
)
def test_invalid_capacity_is_rejected(tmp_path, capacity):
    fixture = LifecycleFixture()
    with pytest.raises(
        ValueError,
        match="positive integers",
    ):
        build_service(
            tmp_path,
            coordinator=fixture.coordinator,
            chains=(
                ("journal", fixture.journal),
            ),
            capacities={
                "journal": capacity,
            },
        )


def test_service_canonicalizes_lifecycle_chain_order(tmp_path):
    fixture = LifecycleFixture()
    service = build_service(
        tmp_path,
        coordinator=fixture.coordinator,
        chains=(
            ("receipts", fixture.receipts),
            ("journal", fixture.journal),
        ),
    )
    assert tuple(
        chain_id
        for chain_id, _
        in service.durable_lifecycle_chains
    ) == (
        "journal",
        "receipts",
    )


def test_healthy_lifecycle_allows_start(tmp_path):
    fixture = LifecycleFixture(
        journal_capacity=100,
        target_utilization=0.8,
    )
    append_events(
        fixture.journal,
        2,
    )
    service = build_service(
        tmp_path,
        coordinator=fixture.coordinator,
        chains=(
            ("journal", fixture.journal),
        ),
    )
    diagnostics = service.start()
    assert diagnostics.ok
    assert service.state.phase is AIServicePhase.READY
    lifecycle = service.status().durable_lifecycle
    assert lifecycle is not None
    assert lifecycle["allowed"] is True
    assert (
        lifecycle["chains"]["journal"]["state"]
        == "healthy"
    )


def test_compaction_ready_lifecycle_allows_start(tmp_path):
    fixture = LifecycleFixture()
    fixture.prepare_journal_ready()
    service = build_service(
        tmp_path,
        coordinator=fixture.coordinator,
        chains=(
            ("journal", fixture.journal),
        ),
    )
    service.start()
    assert service.state.phase is AIServicePhase.READY
    assert (
        service.status()
        .durable_lifecycle["chains"]["journal"]["state"]
        == "compaction_ready"
    )


def test_two_compaction_ready_chains_allow_start(tmp_path):
    fixture = LifecycleFixture()
    fixture.prepare_journal_ready()
    fixture.prepare_receipts_ready()
    service = build_service(
        tmp_path,
        coordinator=fixture.coordinator,
        chains=(
            ("receipts", fixture.receipts),
            ("journal", fixture.journal),
        ),
    )
    service.start()
    assert service.state.phase is AIServicePhase.READY
    status = service.status().durable_lifecycle
    assert status["allowed"] is True
    assert tuple(
        status["chains"]
    ) == (
        "journal",
        "receipts",
    )
    assert all(
        item["state"] == "compaction_ready"
        for item in status["chains"].values()
    )


def test_checkpoint_required_blocks_start_without_mutation(tmp_path):
    fixture = LifecycleFixture()
    append_events(
        fixture.journal,
        8,
    )
    before = fixture.checkpoints.length()
    assert before == 0
    service = build_service(
        tmp_path,
        coordinator=fixture.coordinator,
        chains=(
            ("journal", fixture.journal),
        ),
    )
    service.start()
    assert service.state.phase is AIServicePhase.FAILED
    assert fixture.checkpoints.length() == before
    assert fixture.archives.latest("journal") is None
    lifecycle = service.status().durable_lifecycle
    assert lifecycle["allowed"] is False
    assert (
        lifecycle["chains"]["journal"]["state"]
        == "checkpoint_required"
    )


def test_archive_required_blocks_start_without_archive_mutation(tmp_path):
    fixture = LifecycleFixture()
    append_events(
        fixture.journal,
        6,
    )
    checkpoint = fixture.checkpoints.publish(
        "journal",
        fixture.journal,
    )
    append_events(
        fixture.journal,
        2,
        start=6,
    )
    assert fixture.archives.latest("journal") is None
    service = build_service(
        tmp_path,
        coordinator=fixture.coordinator,
        chains=(
            ("journal", fixture.journal),
        ),
    )
    service.start()
    assert service.state.phase is AIServicePhase.FAILED
    assert fixture.archives.latest("journal") is None
    assert (
        fixture.checkpoints.latest("journal")
        == checkpoint
    )
    assert (
        service.status()
        .durable_lifecycle["chains"]["journal"]["state"]
        == "archive_required"
    )


def test_service_never_calls_prepare_at_start(tmp_path, monkeypatch):
    fixture = LifecycleFixture()
    append_events(
        fixture.journal,
        8,
    )
    calls = {"prepare": 0}

    def forbidden_prepare(*args, **kwargs):
        calls["prepare"] += 1
        raise AssertionError(
            "service must not mutate lifecycle state"
        )

    monkeypatch.setattr(
        fixture.coordinator,
        "prepare",
        forbidden_prepare,
    )
    service = build_service(
        tmp_path,
        coordinator=fixture.coordinator,
        chains=(
            ("journal", fixture.journal),
        ),
    )
    service.start()
    assert service.state.phase is AIServicePhase.FAILED
    assert calls["prepare"] == 0
    assert fixture.checkpoints.length() == 0


def test_status_serialization_includes_lifecycle_chains(tmp_path):
    fixture = LifecycleFixture(
        journal_capacity=100,
        target_utilization=0.8,
    )
    append_events(fixture.journal, 1)
    service = build_service(
        tmp_path,
        coordinator=fixture.coordinator,
        chains=(
            ("journal", fixture.journal),
        ),
    )
    service.start()
    data = service.status().to_dict()
    assert data["durable_lifecycle"]["allowed"] is True
    assert (
        data["durable_lifecycle"]
        ["chains"]["journal"]["state"]
        == "healthy"
    )
    assert (
        data["durable_lifecycle"]
        ["chains"]["journal"]
        ["destructive_action_authorized"]
        is False
    )


def test_healthy_chain_growth_to_checkpoint_pressure_degrades_before_new_session(
    tmp_path,
):
    fixture = LifecycleFixture()
    append_events(
        fixture.journal,
        2,
    )
    service = build_service(
        tmp_path,
        coordinator=fixture.coordinator,
        chains=(
            ("journal", fixture.journal),
        ),
    )
    service.start()
    assert service.state.phase is AIServicePhase.READY

    append_events(
        fixture.journal,
        6,
        start=2,
    )
    with pytest.raises(
        RuntimeError,
        match="durable evidence lifecycle",
    ):
        service.new_session(
            intent("new-work")
        )
    assert service.state.phase is AIServicePhase.DEGRADED
    assert (
        service.status()
        .durable_lifecycle["allowed"]
        is False
    )


def test_drift_after_session_creation_blocks_review(tmp_path):
    fixture = LifecycleFixture()
    append_events(fixture.journal, 2)
    service = build_service(
        tmp_path,
        coordinator=fixture.coordinator,
        chains=(("journal", fixture.journal),),
    )
    service.start()
    session = service.new_session(
        intent("review-drift")
    )
    append_events(
        fixture.journal,
        6,
        start=2,
    )
    with pytest.raises(
        RuntimeError,
        match="durable evidence lifecycle",
    ):
        service.review(session)
    assert service.state.phase is AIServicePhase.DEGRADED


def test_drift_after_review_blocks_seal_before_consumption(tmp_path):
    fixture = LifecycleFixture()
    append_events(fixture.journal, 2)
    service = build_service(
        tmp_path,
        coordinator=fixture.coordinator,
        chains=(("journal", fixture.journal),),
    )
    service.start()
    session = service.new_session(
        intent("seal-drift")
    )
    review, _ = service.review(
        session
    )
    authority = ExecutionSealAuthority(
        b"k" * 32
    )
    append_events(
        fixture.journal,
        6,
        start=2,
    )
    with pytest.raises(
        RuntimeError,
        match="durable evidence lifecycle",
    ):
        service.seal_review(
            session,
            review,
            principal="alice",
            authority=authority,
        )
    assert service.state.phase is AIServicePhase.DEGRADED


def test_drift_after_review_blocks_direct_child_before_receipt(tmp_path):
    fixture = LifecycleFixture()
    append_events(fixture.journal, 2)
    service = build_service(
        tmp_path,
        coordinator=fixture.coordinator,
        chains=(("journal", fixture.journal),),
    )
    service.start()
    session = service.new_session(
        intent("execute-drift")
    )
    review, _ = service.review(
        session
    )
    before_receipts = (
        service.orchestrator.shell_service
        .receipts.snapshot()
    )
    append_events(
        fixture.journal,
        6,
        start=2,
    )
    with pytest.raises(
        RuntimeError,
        match="durable evidence lifecycle",
    ):
        service.execute(
            session,
            review,
            context=ExecutionContext(
                "context",
                principal="alice",
            ),
        )
    after_receipts = (
        service.orchestrator.shell_service
        .receipts.snapshot()
    )
    assert after_receipts == before_receipts
    assert service.state.phase is AIServicePhase.DEGRADED


def test_archive_tamper_after_start_degrades_before_session(tmp_path):
    fixture = LifecycleFixture()
    first, _, _, _ = (
        fixture.prepare_journal_ready()
    )
    service = build_service(
        tmp_path,
        coordinator=fixture.coordinator,
        chains=(("journal", fixture.journal),),
    )
    service.start()
    assert service.state.phase is AIServicePhase.READY

    node_hash = first[-1].event_hash
    key = fixture.archives._node_key(
        "journal",
        node_hash,
    )
    record = fixture.backend.get(
        fixture.archives.namespace,
        key,
    )
    raw = dict(record.value)
    payload = dict(raw["payload"])
    payload["summary"] = "tampered"
    raw["payload"] = payload
    fixture.backend.compare_and_swap(
        fixture.archives.namespace,
        key,
        expected_revision=record.revision,
        value=raw,
    )

    with pytest.raises(
        RuntimeError,
        match="durable evidence lifecycle",
    ):
        service.new_session(
            intent("tampered-archive")
        )
    assert service.state.phase is AIServicePhase.DEGRADED


def test_protected_root_is_forwarded_through_service_gate(tmp_path):
    fixture = LifecycleFixture()
    first, _, _, _ = (
        fixture.prepare_journal_ready()
    )
    protected = first[1].event_hash
    service = build_service(
        tmp_path,
        coordinator=fixture.coordinator,
        chains=(("journal", fixture.journal),),
        protected_roots={
            "journal": (protected,),
        },
    )
    service.start()
    assert service.state.phase is AIServicePhase.READY
    report = (
        service._durable_lifecycle_reports[
            "journal"
        ]
    )
    assert report.compaction is not None
    assert (
        report.compaction.protected_roots[0]
        .root_hash
        == protected
    )


def test_explicit_capacity_is_forwarded_to_lifecycle(tmp_path):
    fixture = LifecycleFixture(
        journal_capacity=100,
        target_utilization=0.5,
    )
    append_events(fixture.journal, 8)
    # Chain-native capacity would be healthy (8/100). Override to 10 means
    # lifecycle pressure must be visible.
    service = build_service(
        tmp_path,
        coordinator=fixture.coordinator,
        chains=(("journal", fixture.journal),),
        capacities={"journal": 10},
    )
    service.start()
    assert service.state.phase is AIServicePhase.FAILED
    assert (
        service.status()
        .durable_lifecycle["chains"]["journal"]["state"]
        == "checkpoint_required"
    )


def test_lifecycle_status_updates_on_successful_recheck(tmp_path):
    fixture = LifecycleFixture(
        journal_capacity=100,
        target_utilization=0.8,
    )
    append_events(fixture.journal, 1)
    service = build_service(
        tmp_path,
        coordinator=fixture.coordinator,
        chains=(("journal", fixture.journal),),
    )
    service.start()
    first_digest = (
        service._durable_lifecycle_reports[
            "journal"
        ].digest
    )
    append_events(
        fixture.journal,
        1,
        start=1,
    )
    session = service.new_session(
        intent("status-refresh")
    )
    assert session.session_id
    second_digest = (
        service._durable_lifecycle_reports[
            "journal"
        ].digest
    )
    assert second_digest != first_digest
    assert service.state.phase is AIServicePhase.READY


def test_receipt_lifecycle_drift_degrades_service(tmp_path):
    fixture = LifecycleFixture()
    tuple(
        fixture.receipts.append(
            receipt(index)
        )
        for index in range(2)
    )
    service = build_service(
        tmp_path,
        coordinator=fixture.coordinator,
        chains=(
            ("receipts", fixture.receipts),
        ),
    )
    service.start()
    assert service.state.phase is AIServicePhase.READY

    tuple(
        fixture.receipts.append(
            receipt(index)
        )
        for index in range(2, 8)
    )
    with pytest.raises(
        RuntimeError,
        match="durable evidence lifecycle",
    ):
        service.new_session(
            intent("receipt-pressure")
        )
    assert service.state.phase is AIServicePhase.DEGRADED


def test_one_bad_chain_blocks_multi_chain_start(tmp_path):
    fixture = LifecycleFixture()
    append_events(
        fixture.journal,
        8,
    )
    tuple(
        fixture.receipts.append(
            receipt(index)
        )
        for index in range(2)
    )
    service = build_service(
        tmp_path,
        coordinator=fixture.coordinator,
        chains=(
            ("journal", fixture.journal),
            ("receipts", fixture.receipts),
        ),
    )
    service.start()
    assert service.state.phase is AIServicePhase.FAILED
    status = service.status().durable_lifecycle
    assert status["allowed"] is False
    assert (
        status["chains"]["journal"]["state"]
        == "checkpoint_required"
    )
    assert (
        status["chains"]["receipts"]["state"]
        == "healthy"
    )


def test_service_lifecycle_inspection_exception_fails_start(tmp_path, monkeypatch):
    fixture = LifecycleFixture(
        journal_capacity=100,
        target_utilization=0.8,
    )
    append_events(fixture.journal, 1)

    def broken(*args, **kwargs):
        raise RuntimeError("synthetic lifecycle outage")

    monkeypatch.setattr(
        fixture.coordinator,
        "inspect",
        broken,
    )
    service = build_service(
        tmp_path,
        coordinator=fixture.coordinator,
        chains=(("journal", fixture.journal),),
    )
    with pytest.raises(
        RuntimeError,
        match="synthetic lifecycle outage",
    ):
        # Startup currently performs direct inspection and surfaces inspection
        # exceptions; the state remains STARTING until the service handles it.
        service.start()


def test_live_recheck_exception_degrades_service(tmp_path, monkeypatch):
    fixture = LifecycleFixture(
        journal_capacity=100,
        target_utilization=0.8,
    )
    append_events(fixture.journal, 1)
    service = build_service(
        tmp_path,
        coordinator=fixture.coordinator,
        chains=(("journal", fixture.journal),),
    )
    service.start()
    assert service.state.phase is AIServicePhase.READY

    def broken(*args, **kwargs):
        raise RuntimeError("synthetic lifecycle outage")

    monkeypatch.setattr(
        fixture.coordinator,
        "inspect",
        broken,
    )
    with pytest.raises(
        RuntimeError,
        match="durable evidence lifecycle",
    ):
        service.new_session(
            intent("outage")
        )
    assert service.state.phase is AIServicePhase.DEGRADED


def test_service_status_dataclass_round_trip_lifecycle(tmp_path):
    fixture = LifecycleFixture(
        journal_capacity=100,
        target_utilization=0.8,
    )
    service = build_service(
        tmp_path,
        coordinator=fixture.coordinator,
        chains=(("journal", fixture.journal),),
    )
    service.start()
    status = service.status()
    data = status.to_dict()
    assert data["phase"] == "ready"
    assert (
        data["durable_lifecycle"]
        == status.durable_lifecycle
    )


def test_lifecycle_service_gate_never_sets_destructive_authority(tmp_path):
    fixture = LifecycleFixture()
    fixture.prepare_journal_ready()
    service = build_service(
        tmp_path,
        coordinator=fixture.coordinator,
        chains=(("journal", fixture.journal),),
    )
    service.start()
    report = service._durable_lifecycle_reports[
        "journal"
    ]
    assert report.ok
    assert not report.destructive_action_authorized
    assert (
        report.compaction is not None
        and not report.compaction
        .destructive_action_authorized
    )
