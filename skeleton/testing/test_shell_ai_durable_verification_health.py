"""Fleet health and AI service admission tests for durable verification cursors."""

from __future__ import annotations

from dataclasses import replace
import sys

import pytest

from skeleton.shells.ai.catalog import AIToolCatalog
from skeleton.shells.ai.compiler import AIPlanCompiler
from skeleton.shells.ai.critic import AIPlanCritic
from skeleton.shells.ai.diagnostics import AIShellDiagnostics
from skeleton.shells.ai.distributed_journal import (
    DistributedAIDecisionJournal,
    DistributedJournalHead,
)
from skeleton.shells.ai.distributed_state import InMemoryFencedStore
from skeleton.shells.ai.durable_verification_cursor import (
    DurableIncrementalVerifier,
    DurableVerificationCursorStore,
    DurableVerificationPolicy,
    DurableVerificationStatus,
)
from skeleton.shells.ai.durable_verification_health import (
    DurableChainVerificationHealth,
    DurableVerificationFinding,
    DurableVerificationFleetError,
    DurableVerificationFleetGuard,
    DurableVerificationFleetPolicy,
    DurableVerificationFleetReport,
    DurableVerificationSeverity,
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
from skeleton.shells.commands import (
    CommandCatalog,
    CommandDefinition,
)
from skeleton.shells.distributed_receipts import (
    DistributedReceiptChain,
    DistributedReceiptHead,
)
from skeleton.shells.execution_context import ExecutionContext
from skeleton.shells.executor import ShellExecutor
from skeleton.shells.receipts import ExecutionReceipt
from skeleton.shells.registry import ExecutableSpec
from skeleton.shells.runner import ShellPolicy, ShellRunner
from skeleton.shells.shell_service import ShellService


def fp(value: str) -> str:
    import hashlib

    return hashlib.sha256(value.encode()).hexdigest()


def append_event(
    journal: DistributedAIDecisionJournal,
    index: int,
):
    return journal.append(
        "verification.health",
        session_id=f"session-{index}",
        intent_id=f"intent-{index}",
        proposal_id=f"proposal-{index}",
        summary=f"event {index}",
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
        attempt=index + 1,
        receipt_id=f"receipt-{index}",
    )


def guard_fixture(
    *,
    clock=None,
    verification_policy=None,
    fleet_policy=None,
):
    backend = InMemoryFencedStore()
    signer = ArtifactSigner(
        "verification-health",
        b"h" * 32,
        clock=clock or (lambda: 10.0),
    )
    store = DurableVerificationCursorStore(
        backend,
        signer,
        namespace="verification-health",
    )
    verifier = DurableIncrementalVerifier(
        store,
        verification_policy,
        clock=clock or (lambda: 10.0),
    )
    guard = DurableVerificationFleetGuard(
        verifier,
        fleet_policy,
    )
    return backend, store, verifier, guard


def test_default_fleet_policy():
    policy = DurableVerificationFleetPolicy()
    assert policy.max_chains == 32
    assert policy.max_findings == 256
    assert policy.require_cursor_current
    assert policy.tail_pending_is_warning
    assert policy.full_required_is_warning


@pytest.mark.parametrize(
    "field,value",
    [
        ("max_chains", 0),
        ("max_chains", -1),
        ("max_chains", True),
        ("max_findings", 0),
        ("max_findings", -1),
        ("max_findings", True),
        ("require_cursor_current", "yes"),
        ("tail_pending_is_warning", "yes"),
        ("full_required_is_warning", "yes"),
    ],
)
def test_fleet_policy_validation(field, value):
    values = dict(
        max_chains=8,
        max_findings=32,
        require_cursor_current=True,
        tail_pending_is_warning=True,
        full_required_is_warning=True,
    )
    values[field] = value
    with pytest.raises(ValueError):
        DurableVerificationFleetPolicy(
            **values
        )


def test_fleet_policy_digest_is_stable():
    first = DurableVerificationFleetPolicy(
        max_chains=7,
        max_findings=22,
    )
    second = DurableVerificationFleetPolicy(
        max_chains=7,
        max_findings=22,
    )
    assert first.digest == second.digest
    assert first.to_dict() == second.to_dict()


def test_inspect_missing_cursor_is_not_allowed():
    journal = DistributedAIDecisionJournal(
        InMemoryFencedStore()
    )
    _, _, _, guard = guard_fixture()
    report = guard.inspect(
        (("journal", journal),)
    )
    assert not report.allowed
    assert not report.advanced
    assert report.errors == 1
    assert report.chains[0].status is (
        DurableVerificationStatus.NO_CURSOR
    )
    assert report.chains[0].findings[0].code == (
        "durable_verification.cursor_missing"
    )


def test_require_bootstraps_missing_cursor():
    journal = DistributedAIDecisionJournal(
        InMemoryFencedStore(),
        clock=lambda: 1.0,
    )
    append_event(journal, 0)
    _, _, _, guard = guard_fixture()
    report = guard.require(
        (("journal", journal),)
    )
    assert report.allowed
    assert report.advanced
    assert report.verified == 1
    assert report.errors == 0
    assert report.chains[0].verified
    assert report.chains[0].status is (
        DurableVerificationStatus.FULL_VERIFIED
    )


def test_inspect_current_cursor_is_allowed():
    journal = DistributedAIDecisionJournal(
        InMemoryFencedStore(),
        clock=lambda: 1.0,
    )
    append_event(journal, 0)
    _, _, _, guard = guard_fixture()
    guard.require(
        (("journal", journal),)
    )
    report = guard.inspect(
        (("journal", journal),)
    )
    assert report.allowed
    assert report.chains[0].status is (
        DurableVerificationStatus.CURRENT
    )
    assert report.chains[0].verified


def test_inspect_tail_pending_is_not_yet_allowed():
    journal = DistributedAIDecisionJournal(
        InMemoryFencedStore(),
        clock=lambda: 1.0,
    )
    append_event(journal, 0)
    _, _, _, guard = guard_fixture()
    guard.require(
        (("journal", journal),)
    )
    append_event(journal, 1)
    report = guard.inspect(
        (("journal", journal),)
    )
    assert not report.allowed
    assert report.errors == 0
    assert report.warnings == 1
    assert not report.chains[0].verified
    assert report.chains[0].status is (
        DurableVerificationStatus.TAIL_PENDING
    )


def test_require_advances_tail():
    journal = DistributedAIDecisionJournal(
        InMemoryFencedStore(),
        clock=lambda: 1.0,
    )
    append_event(journal, 0)
    _, _, _, guard = guard_fixture()
    guard.require(
        (("journal", journal),)
    )
    append_event(journal, 1)
    report = guard.require(
        (("journal", journal),)
    )
    assert report.allowed
    assert report.advanced
    assert report.chains[0].status is (
        DurableVerificationStatus.TAIL_VERIFIED
    )
    assert report.chains[0].tail_items == 1


def test_multi_chain_require_is_sorted():
    backend = InMemoryFencedStore()
    journal = DistributedAIDecisionJournal(
        backend,
        namespace="journal",
        clock=lambda: 1.0,
    )
    receipts = DistributedReceiptChain(
        backend,
        namespace="receipts",
    )
    append_event(journal, 0)
    receipts.append(receipt(0))
    _, _, _, guard = guard_fixture()
    report = guard.require(
        (
            ("receipts", receipts),
            ("journal", journal),
        )
    )
    assert report.allowed
    assert [
        item.chain_id
        for item in report.chains
    ] == ["journal", "receipts"]
    assert report.verified == 2


def test_one_invalid_chain_denies_fleet():
    journal = DistributedAIDecisionJournal(
        InMemoryFencedStore(),
        clock=lambda: 1.0,
    )
    append_event(journal, 0)

    class InvalidChain:
        def head(self):
            return DistributedJournalHead(
                1,
                fp("invalid-root"),
            )

        def verify(self):
            return False

        def snapshot_segment(
            self,
            start_exclusive_root,
            end_inclusive_root="",
            *,
            max_items=4096,
        ):
            raise RuntimeError("invalid chain")

    _, _, _, guard = guard_fixture()
    with pytest.raises(
        DurableVerificationFleetError,
    ):
        guard.require(
            (
                ("good", journal),
                ("bad", InvalidChain()),
            )
        )


def test_empty_fleet_rejected():
    _, _, _, guard = guard_fixture()
    with pytest.raises(
        ValueError,
        match="at least one",
    ):
        guard.inspect(())


def test_duplicate_fleet_chain_id_rejected():
    chain = DistributedAIDecisionJournal(
        InMemoryFencedStore()
    )
    _, _, _, guard = guard_fixture()
    with pytest.raises(
        ValueError,
        match="duplicate",
    ):
        guard.inspect(
            (
                ("same", chain),
                ("same", chain),
            )
        )


@pytest.mark.parametrize(
    "chain_id",
    ["", "x" * 129, 1],
)
def test_invalid_fleet_chain_id_rejected(chain_id):
    chain = DistributedAIDecisionJournal(
        InMemoryFencedStore()
    )
    _, _, _, guard = guard_fixture()
    with pytest.raises(
        ValueError,
        match="chain_id",
    ):
        guard.inspect(
            ((chain_id, chain),)
        )


def test_malformed_fleet_entry_rejected():
    _, _, _, guard = guard_fixture()
    with pytest.raises(
        ValueError,
        match="pairs",
    ):
        guard.inspect(
            (("journal",),)
        )


def test_non_protocol_chain_rejected():
    _, _, _, guard = guard_fixture()
    with pytest.raises(
        TypeError,
        match="incremental protocol",
    ):
        guard.inspect(
            (("bad", object()),)
        )


def test_fleet_bound_enforced():
    policy = DurableVerificationFleetPolicy(
        max_chains=1,
    )
    _, _, _, guard = guard_fixture(
        fleet_policy=policy,
    )
    first = DistributedAIDecisionJournal(
        InMemoryFencedStore()
    )
    second = DistributedAIDecisionJournal(
        InMemoryFencedStore()
    )
    with pytest.raises(
        DurableVerificationFleetError,
        match="bound",
    ):
        guard.inspect(
            (
                ("one", first),
                ("two", second),
            )
        )


def test_guard_constructor_validation():
    with pytest.raises(TypeError, match="verifier"):
        DurableVerificationFleetGuard(
            object()
        )
    _, _, verifier, _ = guard_fixture()
    with pytest.raises(TypeError, match="policy"):
        DurableVerificationFleetGuard(
            verifier,
            object(),
        )


def test_finding_validation():
    with pytest.raises(ValueError):
        DurableVerificationFinding(
            DurableVerificationSeverity.ERROR,
            "",
            "message",
        )
    with pytest.raises(ValueError):
        DurableVerificationFinding(
            DurableVerificationSeverity.ERROR,
            "code",
            "",
        )
    finding = DurableVerificationFinding(
        "warning",
        "code",
        "message",
        "chain",
    )
    assert finding.severity is (
        DurableVerificationSeverity.WARNING
    )
    assert finding.to_dict()["chain_id"] == "chain"


def test_chain_health_properties():
    finding = DurableVerificationFinding(
        DurableVerificationSeverity.WARNING,
        "warning",
        "warning",
        "journal",
    )
    health = DurableChainVerificationHealth(
        "journal",
        DurableVerificationStatus.CURRENT,
        True,
        1,
        fp("root"),
        1,
        fp("root"),
        fp("cursor"),
        0,
        1.0,
        0,
        False,
        (finding,),
    )
    assert health.ok
    assert health.errors == 0
    assert health.warnings == 1
    assert health.to_dict()["status"] == "current"


def test_fleet_report_digest_is_stable():
    journal = DistributedAIDecisionJournal(
        InMemoryFencedStore(),
        clock=lambda: 1.0,
    )
    append_event(journal, 0)
    _, _, _, guard = guard_fixture()
    guard.require(
        (("journal", journal),)
    )
    first = guard.inspect(
        (("journal", journal),)
    )
    second = guard.inspect(
        (("journal", journal),)
    )
    assert first.digest == second.digest
    assert first == second


def test_fleet_report_serialization():
    journal = DistributedAIDecisionJournal(
        InMemoryFencedStore(),
        clock=lambda: 1.0,
    )
    append_event(journal, 0)
    _, _, _, guard = guard_fixture()
    report = guard.require(
        (("journal", journal),)
    )
    data = report.to_dict()
    assert data["allowed"] is True
    assert data["advanced"] is True
    assert data["total_chains"] == 1
    assert data["verified"] == 1
    assert data["digest"] == report.digest


class CountingChain:
    def __init__(self, delegate):
        self.delegate = delegate
        self.verify_calls = 0
        self.segment_calls = 0

    def head(self):
        return self.delegate.head()

    def verify(self):
        self.verify_calls += 1
        return self.delegate.verify()

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


def test_fleet_current_recheck_does_not_full_verify():
    journal = DistributedAIDecisionJournal(
        InMemoryFencedStore(),
        clock=lambda: 1.0,
    )
    append_event(journal, 0)
    counted = CountingChain(journal)
    _, _, _, guard = guard_fixture()
    guard.require(
        (("journal", counted),)
    )
    assert counted.verify_calls == 1
    for _ in range(5):
        report = guard.require(
            (("journal", counted),)
        )
        assert report.allowed
    assert counted.verify_calls == 1
    assert counted.segment_calls == 0


def test_fleet_tail_recheck_only_hashes_tail():
    journal = DistributedAIDecisionJournal(
        InMemoryFencedStore(),
        clock=lambda: 1.0,
    )
    append_event(journal, 0)
    counted = CountingChain(journal)
    _, _, _, guard = guard_fixture()
    guard.require(
        (("journal", counted),)
    )
    append_event(journal, 1)
    append_event(journal, 2)
    report = guard.require(
        (("journal", counted),)
    )
    assert report.allowed
    assert counted.verify_calls == 1
    assert counted.segment_calls == 1
    assert report.chains[0].tail_items == 2


def test_fleet_periodic_full_refresh():
    clock = [10.0]
    journal = DistributedAIDecisionJournal(
        InMemoryFencedStore(),
        clock=lambda: 1.0,
    )
    append_event(journal, 0)
    counted = CountingChain(journal)
    policy = DurableVerificationPolicy(
        max_full_verification_age_seconds=5.0,
    )
    _, _, _, guard = guard_fixture(
        clock=lambda: clock[0],
        verification_policy=policy,
    )
    guard.require(
        (("journal", counted),)
    )
    assert counted.verify_calls == 1
    clock[0] = 20.0
    report = guard.require(
        (("journal", counted),)
    )
    assert report.allowed
    assert counted.verify_calls == 2
    assert report.chains[0].status is (
        DurableVerificationStatus.FULL_VERIFIED
    )


def test_fleet_disabled_full_refresh_denies():
    clock = [10.0]
    journal = DistributedAIDecisionJournal(
        InMemoryFencedStore(),
        clock=lambda: 1.0,
    )
    append_event(journal, 0)
    policy = DurableVerificationPolicy(
        max_full_verification_age_seconds=5.0,
        allow_full_refresh=False,
    )
    _, _, _, guard = guard_fixture(
        clock=lambda: clock[0],
        verification_policy=policy,
    )
    guard.require(
        (("journal", journal),)
    )
    clock[0] = 20.0
    with pytest.raises(
        DurableVerificationFleetError,
    ):
        guard.require(
            (("journal", journal),)
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
                    {
                        EffectKind.READ_FILESYSTEM,
                    }
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
                        ("-c", "print('verification')"),
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
    verification_guard=None,
    verification_chains=(),
):
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
        "verification-root-"
        + str(
            abs(
                hash(
                    tuple(
                        item[0]
                        for item in verification_chains
                        if (
                            isinstance(item, tuple)
                            and item
                        )
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
        durable_verification_guard=(
            verification_guard
        ),
        durable_verification_chains=tuple(
            verification_chains
        ),
    )


def service_intent(
    intent_id="intent",
) -> AIIntent:
    return AIIntent(
        intent_id,
        "perform verification-gated work",
    )


def service_guard(
    *,
    clock=None,
    policy=None,
):
    return guard_fixture(
        clock=clock,
        verification_policy=policy,
    )


def test_service_without_verification_omits_status(tmp_path):
    service = build_service(
        tmp_path,
    )
    service.start()
    assert service.state.phase is AIServicePhase.READY
    assert (
        service.status().durable_verification
        is None
    )
    assert (
        "durable_verification"
        not in service.status().to_dict()
    )


def test_service_chains_require_guard(tmp_path):
    journal = DistributedAIDecisionJournal(
        InMemoryFencedStore()
    )
    with pytest.raises(
        ValueError,
        match="require a durable verification guard",
    ):
        build_service(
            tmp_path,
            verification_chains=(
                ("journal", journal),
            ),
        )


def test_service_guard_requires_chains(tmp_path):
    _, _, _, guard = service_guard()
    with pytest.raises(
        ValueError,
        match="at least one chain",
    ):
        build_service(
            tmp_path,
            verification_guard=guard,
        )


def test_service_rejects_wrong_guard_type(tmp_path):
    journal = DistributedAIDecisionJournal(
        InMemoryFencedStore()
    )
    with pytest.raises(
        TypeError,
        match="durable_verification_guard",
    ):
        build_service(
            tmp_path,
            verification_guard=object(),
            verification_chains=(
                ("journal", journal),
            ),
        )


def test_service_rejects_malformed_chain(tmp_path):
    _, _, _, guard = service_guard()
    with pytest.raises(
        ValueError,
        match="pairs",
    ):
        build_service(
            tmp_path,
            verification_guard=guard,
            verification_chains=(
                ("journal",),
            ),
        )


def test_service_rejects_duplicate_chain_id(tmp_path):
    journal = DistributedAIDecisionJournal(
        InMemoryFencedStore()
    )
    _, _, _, guard = service_guard()
    with pytest.raises(
        ValueError,
        match="duplicate durable verification chain_id",
    ):
        build_service(
            tmp_path,
            verification_guard=guard,
            verification_chains=(
                ("same", journal),
                ("same", journal),
            ),
        )


@pytest.mark.parametrize(
    "chain_id",
    ["", "x" * 129, 1],
)
def test_service_rejects_invalid_chain_id(
    tmp_path,
    chain_id,
):
    journal = DistributedAIDecisionJournal(
        InMemoryFencedStore()
    )
    _, _, _, guard = service_guard()
    with pytest.raises(
        ValueError,
        match="invalid durable verification chain_id",
    ):
        build_service(
            tmp_path,
            verification_guard=guard,
            verification_chains=(
                (chain_id, journal),
            ),
        )


def test_service_canonicalizes_chain_order(tmp_path):
    backend = InMemoryFencedStore()
    journal = DistributedAIDecisionJournal(
        backend,
        namespace="journal",
    )
    receipts = DistributedReceiptChain(
        backend,
        namespace="receipts",
    )
    _, _, _, guard = service_guard()
    service = build_service(
        tmp_path,
        verification_guard=guard,
        verification_chains=(
            ("receipts", receipts),
            ("journal", journal),
        ),
    )
    assert [
        item[0]
        for item in service.durable_verification_chains
    ] == ["journal", "receipts"]


def test_service_start_bootstraps_verification(tmp_path):
    journal = DistributedAIDecisionJournal(
        InMemoryFencedStore(),
        clock=lambda: 1.0,
    )
    append_event(journal, 0)
    _, _, _, guard = service_guard()
    service = build_service(
        tmp_path,
        verification_guard=guard,
        verification_chains=(
            ("journal", journal),
        ),
    )
    service.start()
    assert service.state.phase is AIServicePhase.READY
    status = service.status()
    assert status.durable_verification is not None
    assert status.durable_verification["allowed"] is True
    assert (
        status.durable_verification["chains"][0]["status"]
        == "full_verified"
    )


def test_service_start_blocks_unverifiable_chain(tmp_path):
    class InvalidChain:
        def head(self):
            return DistributedJournalHead(
                1,
                fp("root"),
            )

        def verify(self):
            return False

        def snapshot_segment(
            self,
            start_exclusive_root,
            end_inclusive_root="",
            *,
            max_items=4096,
        ):
            raise RuntimeError("invalid")

    _, _, _, guard = service_guard()
    service = build_service(
        tmp_path,
        verification_guard=guard,
        verification_chains=(
            ("bad", InvalidChain()),
        ),
    )
    service.start()
    assert service.state.phase is AIServicePhase.FAILED
    assert "verification" in service.state.reason


def test_service_repeated_new_session_does_not_full_replay(tmp_path):
    journal = DistributedAIDecisionJournal(
        InMemoryFencedStore(),
        clock=lambda: 1.0,
    )
    append_event(journal, 0)
    counted = CountingChain(journal)
    _, _, _, guard = service_guard()
    service = build_service(
        tmp_path,
        verification_guard=guard,
        verification_chains=(
            ("journal", counted),
        ),
    )
    service.start()
    assert counted.verify_calls == 1
    for index in range(5):
        session = service.new_session(
            service_intent(
                f"intent-{index}"
            ),
            session_id=f"session-{index}",
        )
        assert session.session_id == (
            f"session-{index}"
        )
    assert counted.verify_calls == 1
    assert counted.segment_calls == 0


def test_service_new_tail_is_incrementally_verified(tmp_path):
    journal = DistributedAIDecisionJournal(
        InMemoryFencedStore(),
        clock=lambda: 1.0,
    )
    append_event(journal, 0)
    counted = CountingChain(journal)
    _, _, _, guard = service_guard()
    service = build_service(
        tmp_path,
        verification_guard=guard,
        verification_chains=(
            ("journal", counted),
        ),
    )
    service.start()
    append_event(journal, 1)
    session = service.new_session(
        service_intent(),
        session_id="work",
    )
    assert session.session_id == "work"
    assert counted.verify_calls == 1
    assert counted.segment_calls == 1
    status = service.status()
    assert (
        status.durable_verification["chains"][0]["status"]
        == "tail_verified"
    )


def test_service_review_rechecks_tail(tmp_path):
    journal = DistributedAIDecisionJournal(
        InMemoryFencedStore(),
        clock=lambda: 1.0,
    )
    append_event(journal, 0)
    counted = CountingChain(journal)
    _, _, _, guard = service_guard()
    service = build_service(
        tmp_path,
        verification_guard=guard,
        verification_chains=(
            ("journal", counted),
        ),
    )
    service.start()
    session = service.new_session(
        service_intent(),
        session_id="review",
    )
    append_event(journal, 1)
    review, _ = service.review(session)
    assert review is not None
    assert counted.segment_calls == 1


def test_service_direct_execute_rechecks_verification(tmp_path):
    journal = DistributedAIDecisionJournal(
        InMemoryFencedStore(),
        clock=lambda: 1.0,
    )
    append_event(journal, 0)
    counted = CountingChain(journal)
    _, _, _, guard = service_guard()
    service = build_service(
        tmp_path,
        verification_guard=guard,
        verification_chains=(
            ("journal", counted),
        ),
    )
    service.start()
    session = service.new_session(
        service_intent(),
        session_id="execute",
    )
    review, _ = service.review(session)
    append_event(journal, 1)
    result = service.execute(
        session,
        review,
        context=ExecutionContext(
            "context",
            principal="alice",
        ),
    )
    assert result.ok
    assert counted.segment_calls == 1


def test_service_runtime_fork_degrades_before_session(tmp_path):
    journal = DistributedAIDecisionJournal(
        InMemoryFencedStore(),
        clock=lambda: 1.0,
    )
    append_event(journal, 0)
    counted = CountingChain(journal)
    _, _, _, guard = service_guard()
    service = build_service(
        tmp_path,
        verification_guard=guard,
        verification_chains=(
            ("journal", counted),
        ),
    )
    service.start()
    counted.head = lambda: DistributedJournalHead(
        1,
        fp("fork"),
    )
    with pytest.raises(
        RuntimeError,
        match="durable verification",
    ):
        service.new_session(
            service_intent(),
            session_id="blocked",
        )
    assert (
        service.state.phase
        is AIServicePhase.DEGRADED
    )


def test_service_runtime_regression_degrades(tmp_path):
    journal = DistributedAIDecisionJournal(
        InMemoryFencedStore(),
        clock=lambda: 1.0,
    )
    first = append_event(journal, 0)
    append_event(journal, 1)
    counted = CountingChain(journal)
    _, _, _, guard = service_guard()
    service = build_service(
        tmp_path,
        verification_guard=guard,
        verification_chains=(
            ("journal", counted),
        ),
    )
    service.start()
    counted.head = lambda: DistributedJournalHead(
        1,
        first.event_hash,
    )
    with pytest.raises(RuntimeError):
        service.new_session(
            service_intent(),
            session_id="blocked",
        )
    assert (
        service.state.phase
        is AIServicePhase.DEGRADED
    )


def test_service_periodic_full_refresh(tmp_path):
    clock = [10.0]
    journal = DistributedAIDecisionJournal(
        InMemoryFencedStore(),
        clock=lambda: 1.0,
    )
    append_event(journal, 0)
    counted = CountingChain(journal)
    policy = DurableVerificationPolicy(
        max_full_verification_age_seconds=5.0,
    )
    _, _, _, guard = service_guard(
        clock=lambda: clock[0],
        policy=policy,
    )
    service = build_service(
        tmp_path,
        verification_guard=guard,
        verification_chains=(
            ("journal", counted),
        ),
    )
    service.start()
    assert counted.verify_calls == 1
    clock[0] = 20.0
    service.new_session(
        service_intent(),
        session_id="refresh",
    )
    assert counted.verify_calls == 2
    assert (
        service.status()
        .durable_verification["chains"][0]["status"]
        == "full_verified"
    )


def test_service_disabled_refresh_degrades(tmp_path):
    clock = [10.0]
    journal = DistributedAIDecisionJournal(
        InMemoryFencedStore(),
        clock=lambda: 1.0,
    )
    append_event(journal, 0)
    policy = DurableVerificationPolicy(
        max_full_verification_age_seconds=5.0,
        allow_full_refresh=False,
    )
    _, _, _, guard = service_guard(
        clock=lambda: clock[0],
        policy=policy,
    )
    service = build_service(
        tmp_path,
        verification_guard=guard,
        verification_chains=(
            ("journal", journal),
        ),
    )
    service.start()
    clock[0] = 20.0
    with pytest.raises(RuntimeError):
        service.new_session(
            service_intent(),
            session_id="blocked",
        )
    assert (
        service.state.phase
        is AIServicePhase.DEGRADED
    )


def test_service_two_chains_bootstrap(tmp_path):
    backend = InMemoryFencedStore()
    journal = DistributedAIDecisionJournal(
        backend,
        namespace="journal",
        clock=lambda: 1.0,
    )
    receipts = DistributedReceiptChain(
        backend,
        namespace="receipts",
    )
    append_event(journal, 0)
    receipts.append(receipt(0))
    _, _, _, guard = service_guard()
    service = build_service(
        tmp_path,
        verification_guard=guard,
        verification_chains=(
            ("journal", journal),
            ("receipts", receipts),
        ),
    )
    service.start()
    assert service.state.phase is AIServicePhase.READY
    status = service.status().durable_verification
    assert status["total_chains"] == 2
    assert [
        item["chain_id"]
        for item in status["chains"]
    ] == ["journal", "receipts"]


def test_service_one_bad_chain_blocks_multi_chain_start(tmp_path):
    backend = InMemoryFencedStore()
    journal = DistributedAIDecisionJournal(
        backend,
        namespace="journal",
    )

    class BadReceiptChain:
        def head(self):
            return DistributedReceiptHead(
                1,
                fp("bad"),
            )

        def verify(self):
            return False

        def snapshot_segment(
            self,
            start_exclusive_root,
            end_inclusive_root="",
            *,
            max_items=4096,
        ):
            raise RuntimeError("bad")

    _, _, _, guard = service_guard()
    service = build_service(
        tmp_path,
        verification_guard=guard,
        verification_chains=(
            ("journal", journal),
            ("receipts", BadReceiptChain()),
        ),
    )
    service.start()
    assert service.state.phase is AIServicePhase.FAILED


def test_service_status_updates_after_incremental_recheck(tmp_path):
    journal = DistributedAIDecisionJournal(
        InMemoryFencedStore(),
        clock=lambda: 1.0,
    )
    append_event(journal, 0)
    _, _, _, guard = service_guard()
    service = build_service(
        tmp_path,
        verification_guard=guard,
        verification_chains=(
            ("journal", journal),
        ),
    )
    service.start()
    first = service.status().durable_verification
    append_event(journal, 1)
    service.new_session(
        service_intent(),
        session_id="next",
    )
    second = service.status().durable_verification
    assert (
        first["chains"][0]["cursor_sequence"]
        == 1
    )
    assert (
        second["chains"][0]["cursor_sequence"]
        == 2
    )
    assert first["digest"] != second["digest"]


def test_status_dataclass_round_trip_verification(tmp_path):
    journal = DistributedAIDecisionJournal(
        InMemoryFencedStore()
    )
    _, _, _, guard = service_guard()
    service = build_service(
        tmp_path,
        verification_guard=guard,
        verification_chains=(
            ("journal", journal),
        ),
    )
    service.start()
    status = service.status()
    data = status.to_dict()
    assert (
        data["durable_verification"]
        == status.durable_verification
    )
    assert data["durable_verification"]["allowed"] is True


def test_service_guard_never_mutates_evidence_chain_at_current_head(tmp_path):
    journal = DistributedAIDecisionJournal(
        InMemoryFencedStore(),
        clock=lambda: 1.0,
    )
    first = append_event(journal, 0)
    _, _, _, guard = service_guard()
    service = build_service(
        tmp_path,
        verification_guard=guard,
        verification_chains=(
            ("journal", journal),
        ),
    )
    service.start()
    before = journal.snapshot()
    for index in range(3):
        service.new_session(
            service_intent(
                f"intent-{index}"
            ),
            session_id=f"session-{index}",
        )
    assert journal.snapshot() == before
    assert journal.snapshot()[0] == first


def test_fleet_finding_bound_enforced():
    chains = tuple(
        (
            f"chain-{index}",
            DistributedAIDecisionJournal(
                InMemoryFencedStore()
            ),
        )
        for index in range(3)
    )
    policy = DurableVerificationFleetPolicy(
        max_chains=3,
        max_findings=2,
    )
    _, _, _, guard = guard_fixture(
        fleet_policy=policy,
    )
    with pytest.raises(
        DurableVerificationFleetError,
        match="finding bound",
    ):
        guard.inspect(chains)


def test_inspection_error_is_fail_closed():
    class ExplodingChain:
        def head(self):
            raise RuntimeError("boom")

        def verify(self):
            return True

        def snapshot_segment(
            self,
            start_exclusive_root,
            end_inclusive_root="",
            *,
            max_items=4096,
        ):
            return ()

    _, _, _, guard = guard_fixture()
    report = guard.inspect(
        (("boom", ExplodingChain()),)
    )
    assert not report.allowed
    assert report.errors == 1
    assert report.chains[0].status is (
        DurableVerificationStatus.INVALID
    )
    assert report.chains[0].findings[0].code == (
        "durable_verification.inspect_error"
    )


def test_require_error_is_fail_closed():
    class ExplodingChain:
        def head(self):
            raise RuntimeError("boom")

        def verify(self):
            raise RuntimeError("boom")

        def snapshot_segment(
            self,
            start_exclusive_root,
            end_inclusive_root="",
            *,
            max_items=4096,
        ):
            raise RuntimeError("boom")

    _, _, _, guard = guard_fixture()
    with pytest.raises(
        DurableVerificationFleetError,
    ):
        guard.require(
            (("boom", ExplodingChain()),)
        )
