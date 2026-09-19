"""Lifecycle acceleration contracts for signed durable verification heads."""

from __future__ import annotations

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
from skeleton.shells.ai.durable_verification_cursor import (
    DurableIncrementalVerifier,
    DurableVerificationCursorStore,
)
from skeleton.shells.ai.durable_verification_health import (
    DurableVerificationFleetGuard,
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
from skeleton.shells.ai.types import (
    AIAction,
    AIIntent,
    AIPlanProposal,
)
from skeleton.shells.arguments import ArgumentPolicy
from skeleton.shells.commands import CommandCatalog, CommandDefinition
from skeleton.shells.registry import ExecutableSpec
from skeleton.shells.runner import ShellPolicy, ShellRunner
from skeleton.shells.executor import ShellExecutor
from skeleton.shells.shell_service import ShellService


def fp(value: str) -> str:
    import hashlib

    return hashlib.sha256(value.encode()).hexdigest()


def append_events(
    chain: DistributedAIDecisionJournal,
    count: int,
    *,
    start: int = 0,
):
    values = []
    for index in range(start, start + count):
        values.append(
            chain.append(
                "lifecycle.verified",
                session_id=f"session-{index}",
                intent_id=f"intent-{index}",
                proposal_id=f"proposal-{index}",
                summary=f"event {index}",
            )
        )
    return tuple(values)


class CountingLifecycleChain:
    def __init__(self, delegate):
        self.delegate = delegate
        self.verify_calls = 0
        self.verify_root_calls = 0
        self.ancestor_calls = 0
        self.snapshot_at_calls = 0
        self.segment_calls = 0

    @property
    def max_events(self):
        return self.delegate.max_events

    def head(self):
        return self.delegate.head()

    def verify(self):
        self.verify_calls += 1
        return self.delegate.verify()

    def verify_root(self, root_hash):
        self.verify_root_calls += 1
        return self.delegate.verify_root(
            root_hash
        )

    def root_is_ancestor(self, root_hash):
        self.ancestor_calls += 1
        return self.delegate.root_is_ancestor(
            root_hash
        )

    def snapshot_at(self, root_hash):
        self.snapshot_at_calls += 1
        return self.delegate.snapshot_at(
            root_hash
        )

    def snapshot_segment(
        self,
        start_exclusive_root,
        end_inclusive_root="",
        *,
        max_items=4096,
    ):
        self.segment_calls += 1
        return self.delegate.snapshot_segment(
            start_exclusive_root,
            end_inclusive_root,
            max_items=max_items,
        )

    def root_hash(self):
        return self.delegate.root_hash()

    def length(self):
        return self.delegate.length()


class LifecycleVerificationFixture:
    def __init__(
        self,
        *,
        capacity=100,
        target_utilization=0.8,
        warning_utilization=0.9,
    ):
        self.backend = InMemoryFencedStore()
        self.raw = DistributedAIDecisionJournal(
            self.backend,
            namespace="journal",
            max_events=capacity,
            clock=lambda: 10.0,
        )
        self.chain = CountingLifecycleChain(
            self.raw
        )
        self.checkpoints = DurableChainCheckpointStore(
            self.backend,
            ArtifactSigner(
                "checkpoint",
                b"c" * 32,
                clock=lambda: 100.0,
            ),
            namespace="checkpoints",
            clock=lambda: 100.0,
        )
        self.retention = DurableRetentionPlanner(
            self.checkpoints,
            DurableRetentionPolicy(
                minimum_live_tail=2,
                minimum_archive_batch=2,
                target_utilization=target_utilization,
                warning_utilization=warning_utilization,
                critical_utilization=0.98,
                max_protected_roots=16,
            ),
        )
        self.archive_signer = ArtifactSigner(
            "archive",
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
            namespace="archives",
            clock=lambda: 300.0,
        )
        self.compaction = DurableCompactionPlanner(
            self.archives,
            DurableCompactionPolicy(
                minimum_live_tail=2,
                maximum_candidate_nodes=capacity,
                max_protected_roots=16,
            ),
        )
        self.coordinator = DurableEvidenceLifecycleCoordinator(
            self.checkpoints,
            self.retention,
            self.archive_builder,
            self.archives,
            self.compaction,
        )
        self.cursor_store = DurableVerificationCursorStore(
            self.backend,
            ArtifactSigner(
                "cursor",
                b"v" * 32,
                clock=lambda: 100.0,
            ),
            namespace="cursors",
        )
        self.guard = DurableVerificationFleetGuard(
            DurableIncrementalVerifier(
                self.cursor_store,
                clock=lambda: 100.0,
            )
        )


def test_lifecycle_inspect_with_signed_head_skips_full_replay():
    fixture = LifecycleVerificationFixture()
    append_events(
        fixture.raw,
        3,
    )
    fixture.guard.require(
        (("journal", fixture.chain),)
    )
    health = fixture.guard.inspect(
        (("journal", fixture.chain),)
    ).chains[0]
    before = fixture.chain.verify_calls
    report = fixture.coordinator.inspect(
        "journal",
        fixture.chain,
        verified_head=health,
    )
    assert report.ok
    assert report.state is (
        DurableLifecycleState.HEALTHY
    )
    assert fixture.chain.verify_calls == before


def test_lifecycle_without_signed_head_still_full_verifies():
    fixture = LifecycleVerificationFixture()
    append_events(
        fixture.raw,
        3,
    )
    assert fixture.chain.verify_calls == 0
    report = fixture.coordinator.inspect(
        "journal",
        fixture.chain,
    )
    assert report.ok
    assert fixture.chain.verify_calls == 1


def test_lifecycle_rejects_stale_signed_head():
    fixture = LifecycleVerificationFixture()
    append_events(
        fixture.raw,
        2,
    )
    fixture.guard.require(
        (("journal", fixture.chain),)
    )
    health = fixture.guard.inspect(
        (("journal", fixture.chain),)
    ).chains[0]
    append_events(
        fixture.raw,
        1,
        start=2,
    )
    with pytest.raises(
        Exception,
        match="differs from live head",
    ):
        fixture.coordinator.inspect(
            "journal",
            fixture.chain,
            verified_head=health,
        )


def test_lifecycle_protected_root_keeps_historical_checks():
    fixture = LifecycleVerificationFixture()
    events = append_events(
        fixture.raw,
        4,
    )
    fixture.guard.require(
        (("journal", fixture.chain),)
    )
    health = fixture.guard.inspect(
        (("journal", fixture.chain),)
    ).chains[0]
    before = (
        fixture.chain.ancestor_calls,
        fixture.chain.snapshot_at_calls,
    )
    report = fixture.coordinator.inspect(
        "journal",
        fixture.chain,
        protected_roots=(
            events[1].event_hash,
        ),
        verified_head=health,
    )
    assert report.ok
    assert (
        fixture.chain.ancestor_calls
        > before[0]
    )
    assert (
        fixture.chain.snapshot_at_calls
        > before[1]
    )


def test_checkpoint_prepare_still_full_verifies_mutating_transition():
    fixture = LifecycleVerificationFixture(
        capacity=10,
        target_utilization=0.5,
        warning_utilization=0.7,
    )
    append_events(
        fixture.raw,
        6,
    )
    fixture.guard.require(
        (("journal", fixture.chain),)
    )
    health = fixture.guard.inspect(
        (("journal", fixture.chain),)
    ).chains[0]
    before = fixture.chain.verify_calls
    report = fixture.coordinator.prepare(
        "journal",
        fixture.chain,
        verified_head=health,
    )
    # Checkpoint publication is a stronger state transition and intentionally
    # retains its own full verification requirement.
    assert fixture.chain.verify_calls > before
    assert report.state in {
        DurableLifecycleState.CHECKPOINT_PRIMED,
        DurableLifecycleState.ARCHIVE_REQUIRED,
        DurableLifecycleState.HEALTHY,
    }


def test_lifecycle_require_operational_accepts_signed_head():
    fixture = LifecycleVerificationFixture()
    append_events(
        fixture.raw,
        2,
    )
    fixture.guard.require(
        (("journal", fixture.chain),)
    )
    health = fixture.guard.inspect(
        (("journal", fixture.chain),)
    ).chains[0]
    before = fixture.chain.verify_calls
    report = fixture.coordinator.require_operational(
        "journal",
        fixture.chain,
        verified_head=health,
    )
    assert report.ok
    assert fixture.chain.verify_calls == before


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
                        ("-c", "print('lifecycle')"),
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
    fixture: LifecycleVerificationFixture,
    *,
    verification_chain=None,
    lifecycle_chain=None,
):
    verification_chain = (
        fixture.chain
        if verification_chain is None
        else verification_chain
    )
    lifecycle_chain = (
        fixture.chain
        if lifecycle_chain is None
        else lifecycle_chain
    )
    catalog_value = command_catalog()
    effects_value = effects()
    tools = AIToolCatalog(
        catalog_value
    )
    policy = AIShellPolicy(
        autonomy=AutonomyMode.LOW_RISK_AUTONOMOUS,
        min_confidence=0.5,
        max_uncertainty=0.5,
    )
    model_value = model()
    root = tmp_path / (
        "verification-lifecycle-root-"
        + str(
            abs(
                hash(
                    (
                        id(verification_chain),
                        id(lifecycle_chain),
                    )
                )
            )
            % 100000
        )
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
        durable_verification_guard=fixture.guard,
        durable_verification_chains=(
            ("journal", verification_chain),
        ),
        durable_lifecycle_coordinator=fixture.coordinator,
        durable_lifecycle_chains=(
            ("journal", lifecycle_chain),
        ),
    )


def intent(
    value="intent",
) -> AIIntent:
    return AIIntent(
        value,
        "perform cursor-gated lifecycle work",
    )


def test_service_rejects_same_chain_id_with_different_objects(tmp_path):
    fixture = LifecycleVerificationFixture()
    other = CountingLifecycleChain(
        fixture.raw
    )
    with pytest.raises(
        ValueError,
        match="chain object differs",
    ):
        build_service(
            tmp_path,
            fixture,
            lifecycle_chain=other,
        )


def test_service_start_with_lifecycle_performs_one_full_replay(tmp_path):
    fixture = LifecycleVerificationFixture()
    append_events(
        fixture.raw,
        3,
    )
    service = build_service(
        tmp_path,
        fixture,
    )
    service.start()
    assert service.state.phase is AIServicePhase.READY
    assert fixture.chain.verify_calls == 1
    status = service.status()
    assert status.durable_verification is not None
    assert status.durable_lifecycle is not None


def test_service_repeated_admissions_with_lifecycle_do_not_full_replay(tmp_path):
    fixture = LifecycleVerificationFixture()
    append_events(
        fixture.raw,
        3,
    )
    service = build_service(
        tmp_path,
        fixture,
    )
    service.start()
    assert fixture.chain.verify_calls == 1
    for index in range(5):
        session = service.new_session(
            intent(
                f"intent-{index}"
            ),
            session_id=f"session-{index}",
        )
        assert session.session_id == (
            f"session-{index}"
        )
    assert fixture.chain.verify_calls == 1
    assert fixture.chain.segment_calls == 0


def test_service_tail_growth_uses_segment_then_lifecycle_fast_path(tmp_path):
    fixture = LifecycleVerificationFixture()
    append_events(
        fixture.raw,
        2,
    )
    service = build_service(
        tmp_path,
        fixture,
    )
    service.start()
    full_before = fixture.chain.verify_calls
    append_events(
        fixture.raw,
        2,
        start=2,
    )
    service.new_session(
        intent(),
        session_id="next",
    )
    assert fixture.chain.segment_calls == 1
    assert fixture.chain.verify_calls == full_before


def test_service_review_after_tail_growth_keeps_full_replay_flat(tmp_path):
    fixture = LifecycleVerificationFixture()
    append_events(
        fixture.raw,
        2,
    )
    service = build_service(
        tmp_path,
        fixture,
    )
    service.start()
    session = service.new_session(
        intent(),
        session_id="review",
    )
    append_events(
        fixture.raw,
        1,
        start=2,
    )
    before = fixture.chain.verify_calls
    review, _ = service.review(
        session
    )
    assert review is not None
    assert fixture.chain.verify_calls == before
    assert fixture.chain.segment_calls == 1


def test_service_status_lifecycle_and_verification_heads_match(tmp_path):
    fixture = LifecycleVerificationFixture()
    append_events(
        fixture.raw,
        3,
    )
    service = build_service(
        tmp_path,
        fixture,
    )
    service.start()
    status = service.status()
    verification = (
        status.durable_verification
        ["chains"][0]
    )
    lifecycle = (
        status.durable_lifecycle
        ["chains"]["journal"]
    )
    assert (
        verification["current_sequence"]
        == lifecycle["retention"]["current_sequence"]
    )
    assert (
        verification["current_root"]
        == lifecycle["retention"]["current_root"]
    )


def test_service_lifecycle_protected_root_still_historical(tmp_path):
    fixture = LifecycleVerificationFixture()
    events = append_events(
        fixture.raw,
        4,
    )
    # Build explicitly so protected roots can be configured.
    catalog_value = command_catalog()
    effects_value = effects()
    tools = AIToolCatalog(
        catalog_value
    )
    policy = AIShellPolicy(
        autonomy=AutonomyMode.LOW_RISK_AUTONOMOUS,
    )
    model_value = model()
    root = tmp_path / "protected-root"
    root.mkdir()
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
    service = AIShellService(
        AIShellOrchestrator(
            planner=planner,
            critic=AIPlanCritic(
                effects_value,
                policy,
            ),
            compiler=AIPlanCompiler(
                effects_value,
            ),
            shell_service=shell,
        ),
        AIShellDiagnostics(
            tools,
            effects_value,
            policy,
            model_value,
        ),
        AIShellGovernance(
            AIPolicyStore(policy)
        ),
        durable_verification_guard=fixture.guard,
        durable_verification_chains=(
            ("journal", fixture.chain),
        ),
        durable_lifecycle_coordinator=fixture.coordinator,
        durable_lifecycle_chains=(
            ("journal", fixture.chain),
        ),
        durable_lifecycle_protected_roots={
            "journal": (
                events[1].event_hash,
            ),
        },
    )
    before = fixture.chain.snapshot_at_calls
    service.start()
    assert service.state.phase is AIServicePhase.READY
    assert (
        fixture.chain.snapshot_at_calls
        > before
    )


class FullVerifyBombLifecycleChain(
    CountingLifecycleChain
):
    def verify(self):
        self.verify_calls += 1
        raise AssertionError(
            "unexpected lifecycle full replay"
        )


def test_lifecycle_fast_path_accepts_bomb_view_at_verified_head():
    fixture = LifecycleVerificationFixture()
    append_events(
        fixture.raw,
        3,
    )
    fixture.guard.require(
        (("journal", fixture.chain),)
    )
    bomb = FullVerifyBombLifecycleChain(
        fixture.raw
    )
    # Cursor trust is head-specific. A different view over the same durable
    # chain can be inspected without replaying the whole prefix.
    health = fixture.guard.inspect(
        (("journal", bomb),)
    ).chains[0]
    report = fixture.coordinator.inspect(
        "journal",
        bomb,
        verified_head=health,
    )
    assert report.ok
    assert bomb.verify_calls == 0


def test_lifecycle_fast_path_never_sets_local_deletion_safe():
    fixture = LifecycleVerificationFixture()
    append_events(
        fixture.raw,
        3,
    )
    fixture.guard.require(
        (("journal", fixture.chain),)
    )
    health = fixture.guard.inspect(
        (("journal", fixture.chain),)
    ).chains[0]
    report = fixture.coordinator.inspect(
        "journal",
        fixture.chain,
        verified_head=health,
    )
    assert not report.retention.local_deletion_safe


def test_service_verification_guard_does_not_prepare_lifecycle(tmp_path):
    fixture = LifecycleVerificationFixture(
        capacity=10,
        target_utilization=0.5,
        warning_utilization=0.7,
    )
    append_events(
        fixture.raw,
        6,
    )
    before_checkpoints = (
        fixture.checkpoints.length()
    )
    service = build_service(
        tmp_path,
        fixture,
    )
    service.start()
    # Service startup only inspects lifecycle. It does not publish a checkpoint,
    # archive, or compaction certificate on the user's behalf.
    assert (
        fixture.checkpoints.length()
        == before_checkpoints
    )


def test_service_chain_identity_check_only_applies_to_overlapping_ids(tmp_path):
    fixture = LifecycleVerificationFixture()
    other_backend = InMemoryFencedStore()
    other_raw = DistributedAIDecisionJournal(
        other_backend,
        namespace="other",
    )
    other_chain = CountingLifecycleChain(
        other_raw
    )
    # Different IDs are allowed to represent different durable chains. The
    # lifecycle chain simply will not receive a verification health attestation
    # for an unmatched ID.
    catalog_value = command_catalog()
    effects_value = effects()
    tools = AIToolCatalog(catalog_value)
    policy = AIShellPolicy(
        autonomy=AutonomyMode.LOW_RISK_AUTONOMOUS,
    )
    model_value = model()
    root = tmp_path / "non-overlap"
    root.mkdir()
    shell = ShellService(
        ShellExecutor(
            ShellRunner(
                ShellPolicy(
                    executables={"python": sys.executable},
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
    service = AIShellService(
        AIShellOrchestrator(
            planner=planner,
            critic=AIPlanCritic(
                effects_value,
                policy,
            ),
            compiler=AIPlanCompiler(
                effects_value,
            ),
            shell_service=shell,
        ),
        AIShellDiagnostics(
            tools,
            effects_value,
            policy,
            model_value,
        ),
        AIShellGovernance(
            AIPolicyStore(policy)
        ),
        durable_verification_guard=fixture.guard,
        durable_verification_chains=(
            ("journal", fixture.chain),
        ),
        durable_lifecycle_coordinator=fixture.coordinator,
        durable_lifecycle_chains=(
            ("other", other_chain),
        ),
    )
    # Constructor identity validation accepts the non-overlapping IDs.
    assert (
        service.durable_lifecycle_chains[0][0]
        == "other"
    )
