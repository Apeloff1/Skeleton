"""Durable recovery health policy and AI service admission tests."""

from __future__ import annotations

from dataclasses import replace
import sys

import pytest

from skeleton.shells.ai.catalog import AIToolCatalog
from skeleton.shells.ai.compiler import AIPlanCompiler
from skeleton.shells.ai.critic import AIPlanCritic
from skeleton.shells.ai.diagnostics import AIShellDiagnostics
from skeleton.shells.ai.durable_health import (
    DurableRecoveryHealthError,
    DurableRecoveryHealthFinding,
    DurableRecoveryHealthGuard,
    DurableRecoveryHealthPolicy,
    DurableRecoveryHealthReport,
    DurableRecoveryHealthSeverity,
)
from skeleton.shells.ai.durable_recovery import (
    DurableRecoveryFinding,
    DurableRecoveryStatus,
    DurableSessionRecoveryReport,
    DurableSessionRecoveryVerifier,
    RecoveryFindingSeverity,
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
from skeleton.shells.ai.types import (
    AIAction,
    AIIntent,
    AIPlanProposal,
)
from skeleton.shells.arguments import ArgumentPolicy
from skeleton.shells.commands import CommandCatalog, CommandDefinition
from skeleton.shells.executor import ShellExecutor
from skeleton.shells.registry import ExecutableSpec
from skeleton.shells.runner import ShellPolicy, ShellRunner
from skeleton.shells.shell_service import ShellService


def fp(value: str) -> str:
    import hashlib

    return hashlib.sha256(value.encode()).hexdigest()


def recovery_report(
    finalization_id: str,
    status: DurableRecoveryStatus,
    *,
    session_id: str | None = None,
    findings: tuple[DurableRecoveryFinding, ...] = (),
) -> DurableSessionRecoveryReport:
    complete = status is DurableRecoveryStatus.VERIFIED
    return DurableSessionRecoveryReport(
        finalization_id,
        session_id or f"session-{finalization_id}",
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
        fp(f"journal-root:{finalization_id}") if complete else "",
        fp(f"receipt-root:{finalization_id}") if complete else "",
        None,
        findings,
    )


class StubVerifier(DurableSessionRecoveryVerifier):
    def __init__(self, reports=None):
        self.reports = dict(reports or {})
        self.calls: list[str] = []

    def verify(self, finalization_id: str):
        self.calls.append(finalization_id)
        return self.reports.get(
            finalization_id,
            recovery_report(
                finalization_id,
                DurableRecoveryStatus.INCOMPLETE,
            ),
        )


def guard(
    reports=None,
    *,
    policy=None,
):
    verifier = StubVerifier(reports)
    return (
        DurableRecoveryHealthGuard(
            verifier,
            policy,
        ),
        verifier,
    )


def test_default_policy_is_strict_for_incomplete():
    policy = DurableRecoveryHealthPolicy()
    assert policy.max_incomplete == 0
    assert policy.minimum_verified == 0
    assert not policy.require_nonempty
    assert policy.reject_manual_review


def test_policy_digest_is_deterministic():
    first = DurableRecoveryHealthPolicy(
        max_finalizations=10,
        max_incomplete=2,
        minimum_verified=3,
        require_nonempty=True,
    )
    second = DurableRecoveryHealthPolicy(
        max_finalizations=10,
        max_incomplete=2,
        minimum_verified=3,
        require_nonempty=True,
    )
    assert first.digest == second.digest
    assert len(first.digest) == 64


def test_policy_digest_changes_with_bound():
    first = DurableRecoveryHealthPolicy(
        max_incomplete=0,
    )
    second = DurableRecoveryHealthPolicy(
        max_incomplete=1,
    )
    assert first.digest != second.digest


@pytest.mark.parametrize(
    "field,value",
    [
        ("max_finalizations", 0),
        ("max_finalizations", -1),
        ("max_finalizations", True),
        ("max_incomplete", -1),
        ("max_incomplete", True),
        ("minimum_verified", -1),
        ("minimum_verified", True),
    ],
)
def test_policy_integer_validation(field, value):
    values = dict(
        max_finalizations=10,
        max_incomplete=1,
        minimum_verified=1,
    )
    values[field] = value
    with pytest.raises(ValueError):
        DurableRecoveryHealthPolicy(**values)


def test_policy_incomplete_cannot_exceed_capacity():
    with pytest.raises(ValueError, match="max_incomplete"):
        DurableRecoveryHealthPolicy(
            max_finalizations=2,
            max_incomplete=3,
        )


def test_policy_minimum_verified_cannot_exceed_capacity():
    with pytest.raises(ValueError, match="minimum_verified"):
        DurableRecoveryHealthPolicy(
            max_finalizations=2,
            minimum_verified=3,
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("require_nonempty", 1),
        ("reject_manual_review", 1),
    ],
)
def test_policy_boolean_validation(field, value):
    values = dict(
        require_nonempty=False,
        reject_manual_review=True,
    )
    values[field] = value
    with pytest.raises(ValueError):
        DurableRecoveryHealthPolicy(**values)


def test_policy_cannot_allow_manual_review():
    with pytest.raises(ValueError, match="manual-review"):
        DurableRecoveryHealthPolicy(
            reject_manual_review=False,
        )


def test_empty_set_allowed_by_default():
    target, verifier = guard()
    report = target.inspect(())
    assert report.allowed
    assert report.verified == 0
    assert report.incomplete == 0
    assert report.manual_review == 0
    assert report.findings == ()
    assert verifier.calls == []


def test_empty_set_denied_when_required():
    target, _ = guard(
        policy=DurableRecoveryHealthPolicy(
            require_nonempty=True,
        )
    )
    report = target.inspect(())
    assert not report.allowed
    assert report.errors == 1
    assert report.findings[0].code == (
        "durable_recovery.empty_required_set"
    )


def test_verified_report_is_allowed():
    reports = {
        "a": recovery_report(
            "a",
            DurableRecoveryStatus.VERIFIED,
        )
    }
    target, verifier = guard(reports)
    report = target.inspect(("a",))
    assert report.allowed
    assert report.verified == 1
    assert report.incomplete == 0
    assert report.manual_review == 0
    assert verifier.calls == ["a"]


def test_multiple_verified_reports_are_canonicalized():
    reports = {
        item: recovery_report(
            item,
            DurableRecoveryStatus.VERIFIED,
        )
        for item in ("a", "b", "c")
    }
    target, verifier = guard(reports)
    report = target.inspect(("c", "a", "b"))
    assert report.finalization_ids == (
        "a",
        "b",
        "c",
    )
    assert tuple(
        item.finalization_id
        for item in report.reports
    ) == ("a", "b", "c")
    assert verifier.calls == ["a", "b", "c"]


def test_duplicate_finalization_id_is_rejected():
    target, _ = guard()
    with pytest.raises(ValueError, match="duplicate"):
        target.inspect(("a", "a"))


@pytest.mark.parametrize(
    "value",
    ["", "x" * 257, 123],
)
def test_invalid_finalization_id_rejected(value):
    target, _ = guard()
    with pytest.raises(ValueError, match="finalization_id"):
        target.inspect((value,))


def test_batch_bound_is_enforced():
    target, _ = guard(
        policy=DurableRecoveryHealthPolicy(
            max_finalizations=2,
        )
    )
    with pytest.raises(ValueError, match="bound"):
        target.inspect(("a", "b", "c"))


def test_incomplete_denied_by_default():
    reports = {
        "a": recovery_report(
            "a",
            DurableRecoveryStatus.INCOMPLETE,
        )
    }
    target, _ = guard(reports)
    report = target.inspect(("a",))
    assert not report.allowed
    assert report.incomplete == 1
    assert report.errors >= 1
    assert any(
        item.code
        == "durable_recovery.incomplete_bound"
        for item in report.findings
    )


def test_bounded_incomplete_can_be_tolerated():
    reports = {
        "a": recovery_report(
            "a",
            DurableRecoveryStatus.INCOMPLETE,
        )
    }
    target, _ = guard(
        reports,
        policy=DurableRecoveryHealthPolicy(
            max_incomplete=1,
        ),
    )
    report = target.inspect(("a",))
    assert report.allowed
    assert report.incomplete == 1
    assert report.warnings >= 1
    assert report.errors == 0
    assert any(
        item.code
        == "durable_recovery.incomplete_tolerated"
        for item in report.findings
    )


def test_incomplete_above_tolerance_is_denied():
    reports = {
        item: recovery_report(
            item,
            DurableRecoveryStatus.INCOMPLETE,
        )
        for item in ("a", "b")
    }
    target, _ = guard(
        reports,
        policy=DurableRecoveryHealthPolicy(
            max_incomplete=1,
        ),
    )
    report = target.inspect(("a", "b"))
    assert not report.allowed
    assert report.incomplete == 2


def test_manual_review_always_denied():
    reports = {
        "a": recovery_report(
            "a",
            DurableRecoveryStatus.MANUAL_REVIEW,
            findings=(
                DurableRecoveryFinding(
                    "tampered",
                    RecoveryFindingSeverity.CORRUPTION,
                    "tampered evidence",
                ),
            ),
        )
    }
    target, _ = guard(
        reports,
        policy=DurableRecoveryHealthPolicy(
            max_incomplete=10,
        ),
    )
    report = target.inspect(("a",))
    assert not report.allowed
    assert report.manual_review == 1
    assert any(
        item.code
        == "durable_recovery.manual_review"
        for item in report.findings
    )


def test_minimum_verified_is_enforced():
    reports = {
        "a": recovery_report(
            "a",
            DurableRecoveryStatus.VERIFIED,
        ),
        "b": recovery_report(
            "b",
            DurableRecoveryStatus.INCOMPLETE,
        ),
    }
    target, _ = guard(
        reports,
        policy=DurableRecoveryHealthPolicy(
            max_incomplete=1,
            minimum_verified=2,
        ),
    )
    report = target.inspect(("a", "b"))
    assert not report.allowed
    assert any(
        item.code
        == "durable_recovery.minimum_verified"
        for item in report.findings
    )


def test_require_returns_allowed_report():
    reports = {
        "a": recovery_report(
            "a",
            DurableRecoveryStatus.VERIFIED,
        )
    }
    target, _ = guard(reports)
    report = target.require(("a",))
    assert report.allowed


def test_require_raises_on_denial():
    reports = {
        "a": recovery_report(
            "a",
            DurableRecoveryStatus.MANUAL_REVIEW,
        )
    }
    target, _ = guard(reports)
    with pytest.raises(
        DurableRecoveryHealthError,
    ):
        target.require(("a",))


def test_report_digest_is_stable():
    reports = {
        "a": recovery_report(
            "a",
            DurableRecoveryStatus.VERIFIED,
        )
    }
    target, _ = guard(reports)
    first = target.inspect(("a",))
    second = target.inspect(("a",))
    assert first.digest == second.digest
    assert first == second


def test_report_digest_changes_when_status_changes():
    verifier = StubVerifier(
        {
            "a": recovery_report(
                "a",
                DurableRecoveryStatus.VERIFIED,
            )
        }
    )
    target = DurableRecoveryHealthGuard(verifier)
    first = target.inspect(("a",))
    verifier.reports["a"] = recovery_report(
        "a",
        DurableRecoveryStatus.INCOMPLETE,
    )
    second = target.inspect(("a",))
    assert first.digest != second.digest


def test_report_to_dict_contains_nested_recovery_reports():
    reports = {
        "a": recovery_report(
            "a",
            DurableRecoveryStatus.VERIFIED,
        )
    }
    target, _ = guard(reports)
    report = target.inspect(("a",))
    data = report.to_dict()
    assert data["allowed"] is True
    assert data["verified"] == 1
    assert data["reports"][0]["finalization_id"] == "a"
    assert data["digest"] == report.digest
    assert data["policy_digest"] == target.policy.digest


def test_health_finding_accepts_string_severity():
    finding = DurableRecoveryHealthFinding(
        "warning",
        "code",
        "message",
    )
    assert (
        finding.severity
        is DurableRecoveryHealthSeverity.WARNING
    )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"code": ""},
        {"code": "x" * 129},
        {"message": ""},
        {"message": "x" * 2049},
        {"finalization_id": "x" * 257},
    ],
)
def test_health_finding_validation(kwargs):
    values = dict(
        severity=DurableRecoveryHealthSeverity.INFO,
        code="code",
        message="message",
        finalization_id="",
    )
    values.update(kwargs)
    with pytest.raises(ValueError):
        DurableRecoveryHealthFinding(**values)


def test_report_rejects_unsorted_ids():
    item = recovery_report(
        "b",
        DurableRecoveryStatus.VERIFIED,
    )
    other = recovery_report(
        "a",
        DurableRecoveryStatus.VERIFIED,
    )
    with pytest.raises(ValueError, match="sorted"):
        DurableRecoveryHealthReport(
            fp("policy"),
            ("b", "a"),
            (item, other),
            (),
        )


def test_report_rejects_duplicate_ids():
    item = recovery_report(
        "a",
        DurableRecoveryStatus.VERIFIED,
    )
    with pytest.raises(ValueError, match="duplicate"):
        DurableRecoveryHealthReport(
            fp("policy"),
            ("a", "a"),
            (item, item),
            (),
        )


def test_report_rejects_report_id_mismatch():
    item = recovery_report(
        "b",
        DurableRecoveryStatus.VERIFIED,
    )
    with pytest.raises(ValueError, match="requested ids"):
        DurableRecoveryHealthReport(
            fp("policy"),
            ("a",),
            (item,),
            (),
        )


def test_report_rejects_bad_policy_digest():
    with pytest.raises(ValueError, match="policy_digest"):
        DurableRecoveryHealthReport(
            "bad",
            (),
            (),
            (),
        )


def test_guard_requires_real_verifier_type():
    with pytest.raises(TypeError, match="verifier"):
        DurableRecoveryHealthGuard(object())


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
    health_guard=None,
    health_ids=(),
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
    tools = AIToolCatalog(
        catalog_value
    )
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
            effects_value
        ),
        shell_service=shell,
    )
    service = AIShellService(
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
        durable_recovery_guard=health_guard,
        durable_recovery_ids=tuple(
            health_ids
        ),
    )
    return service


def test_service_constructor_rejects_ids_without_guard(tmp_path):
    with pytest.raises(
        ValueError,
        match="require a durable recovery guard",
    ):
        build_service(
            tmp_path,
            health_ids=("a",),
        )


def test_service_constructor_rejects_wrong_guard_type(tmp_path):
    with pytest.raises(TypeError, match="durable_recovery_guard"):
        build_service(
            tmp_path,
            health_guard=object(),
        )


def test_service_constructor_rejects_duplicate_health_ids(tmp_path):
    target, _ = guard()
    with pytest.raises(ValueError, match="duplicate"):
        build_service(
            tmp_path,
            health_guard=target,
            health_ids=("a", "a"),
        )


def test_service_constructor_rejects_invalid_health_id(tmp_path):
    target, _ = guard()
    with pytest.raises(ValueError, match="finalization_id"):
        build_service(
            tmp_path,
            health_guard=target,
            health_ids=("",),
        )


def test_service_start_allows_verified_required_state(tmp_path):
    reports = {
        "a": recovery_report(
            "a",
            DurableRecoveryStatus.VERIFIED,
        )
    }
    target, verifier = guard(reports)
    service = build_service(
        tmp_path,
        health_guard=target,
        health_ids=("a",),
    )
    diagnostics = service.start()
    assert diagnostics.ok
    assert service.state.phase is AIServicePhase.READY
    assert verifier.calls == ["a"]
    status = service.status()
    assert status.durable_recovery is not None
    assert status.durable_recovery["allowed"] is True


def test_service_start_fails_on_manual_review_state(tmp_path):
    reports = {
        "a": recovery_report(
            "a",
            DurableRecoveryStatus.MANUAL_REVIEW,
        )
    }
    target, _ = guard(reports)
    service = build_service(
        tmp_path,
        health_guard=target,
        health_ids=("a",),
    )
    service.start()
    assert service.state.phase is AIServicePhase.FAILED
    assert service.status().durable_recovery["allowed"] is False


def test_service_start_fails_on_excess_incomplete_state(tmp_path):
    reports = {
        "a": recovery_report(
            "a",
            DurableRecoveryStatus.INCOMPLETE,
        )
    }
    target, _ = guard(reports)
    service = build_service(
        tmp_path,
        health_guard=target,
        health_ids=("a",),
    )
    service.start()
    assert service.state.phase is AIServicePhase.FAILED


def test_service_start_can_tolerate_bounded_incomplete(tmp_path):
    reports = {
        "a": recovery_report(
            "a",
            DurableRecoveryStatus.INCOMPLETE,
        )
    }
    target, _ = guard(
        reports,
        policy=DurableRecoveryHealthPolicy(
            max_incomplete=1,
        ),
    )
    service = build_service(
        tmp_path,
        health_guard=target,
        health_ids=("a",),
    )
    service.start()
    assert service.state.phase is AIServicePhase.READY
    assert service.status().durable_recovery["warnings"] >= 1


def test_service_live_drift_degrades_before_new_session(tmp_path):
    verifier = StubVerifier(
        {
            "a": recovery_report(
                "a",
                DurableRecoveryStatus.VERIFIED,
            )
        }
    )
    target = DurableRecoveryHealthGuard(
        verifier
    )
    service = build_service(
        tmp_path,
        health_guard=target,
        health_ids=("a",),
    )
    service.start()
    assert service.state.phase is AIServicePhase.READY

    verifier.reports["a"] = recovery_report(
        "a",
        DurableRecoveryStatus.MANUAL_REVIEW,
    )
    with pytest.raises(
        RuntimeError,
        match="durable recovery",
    ):
        service.new_session(
            AIIntent(
                "intent",
                "do work",
            )
        )
    assert service.state.phase is AIServicePhase.DEGRADED
    assert service.status().durable_recovery["allowed"] is False


def test_service_live_incomplete_within_policy_remains_ready(tmp_path):
    verifier = StubVerifier(
        {
            "a": recovery_report(
                "a",
                DurableRecoveryStatus.VERIFIED,
            )
        }
    )
    target = DurableRecoveryHealthGuard(
        verifier,
        DurableRecoveryHealthPolicy(
            max_incomplete=1,
        ),
    )
    service = build_service(
        tmp_path,
        health_guard=target,
        health_ids=("a",),
    )
    service.start()
    verifier.reports["a"] = recovery_report(
        "a",
        DurableRecoveryStatus.INCOMPLETE,
    )
    session = service.new_session(
        AIIntent(
            "intent",
            "do work",
        )
    )
    assert session.session_id
    assert service.state.phase is AIServicePhase.READY
    assert service.status().durable_recovery["warnings"] >= 1


def test_service_health_ids_are_canonicalized(tmp_path):
    reports = {
        item: recovery_report(
            item,
            DurableRecoveryStatus.VERIFIED,
        )
        for item in ("a", "b")
    }
    target, verifier = guard(reports)
    service = build_service(
        tmp_path,
        health_guard=target,
        health_ids=("b", "a"),
    )
    assert service.durable_recovery_ids == ("a", "b")
    service.start()
    assert verifier.calls == ["a", "b"]


def test_service_status_omits_health_when_not_configured(tmp_path):
    service = build_service(tmp_path)
    service.start()
    assert service.status().durable_recovery is None


def test_health_report_properties_match_statuses():
    reports = (
        recovery_report(
            "a",
            DurableRecoveryStatus.VERIFIED,
        ),
        recovery_report(
            "b",
            DurableRecoveryStatus.INCOMPLETE,
        ),
        recovery_report(
            "c",
            DurableRecoveryStatus.MANUAL_REVIEW,
        ),
    )
    report = DurableRecoveryHealthReport(
        fp("policy"),
        ("a", "b", "c"),
        reports,
        (
            DurableRecoveryHealthFinding(
                DurableRecoveryHealthSeverity.ERROR,
                "manual",
                "manual review",
                "c",
            ),
        ),
    )
    assert report.verified == 1
    assert report.incomplete == 1
    assert report.manual_review == 1
    assert report.errors == 1
    assert not report.allowed


def test_health_report_to_dict_without_digest():
    target, _ = guard()
    report = target.inspect(())
    data = report.to_dict(
        include_digest=False
    )
    assert "digest" not in data


def test_per_finalization_finding_tracks_id():
    reports = {
        "a": recovery_report(
            "a",
            DurableRecoveryStatus.INCOMPLETE,
        )
    }
    target, _ = guard(
        reports,
        policy=DurableRecoveryHealthPolicy(
            max_incomplete=1,
        ),
    )
    report = target.inspect(("a",))
    item = next(
        finding
        for finding in report.findings
        if finding.finalization_id
    )
    assert item.finalization_id == "a"
    assert item.severity is DurableRecoveryHealthSeverity.WARNING


def test_manual_review_per_finalization_finding_is_error():
    reports = {
        "a": recovery_report(
            "a",
            DurableRecoveryStatus.MANUAL_REVIEW,
        )
    }
    target, _ = guard(reports)
    report = target.inspect(("a",))
    item = next(
        finding
        for finding in report.findings
        if finding.finalization_id
    )
    assert item.severity is DurableRecoveryHealthSeverity.ERROR


def test_policy_to_dict_round_trip_shape():
    policy = DurableRecoveryHealthPolicy(
        max_finalizations=50,
        max_incomplete=2,
        minimum_verified=3,
        require_nonempty=True,
    )
    assert policy.to_dict() == {
        "max_finalizations": 50,
        "max_incomplete": 2,
        "minimum_verified": 3,
        "require_nonempty": True,
        "reject_manual_review": True,
    }


def test_health_finding_to_dict():
    finding = DurableRecoveryHealthFinding(
        DurableRecoveryHealthSeverity.INFO,
        "code",
        "message",
        "f",
    )
    assert finding.to_dict() == {
        "severity": "info",
        "code": "code",
        "message": "message",
        "finalization_id": "f",
    }


def test_status_serialization_includes_health_report(tmp_path):
    reports = {
        "a": recovery_report(
            "a",
            DurableRecoveryStatus.VERIFIED,
        )
    }
    target, _ = guard(reports)
    service = build_service(
        tmp_path,
        health_guard=target,
        health_ids=("a",),
    )
    service.start()
    data = service.status().to_dict()
    assert "durable_recovery" in data
    assert data["durable_recovery"]["verified"] == 1
    assert data["durable_recovery"]["allowed"] is True


def test_verified_minimum_and_incomplete_tolerance_can_coexist():
    reports = {
        "a": recovery_report(
            "a",
            DurableRecoveryStatus.VERIFIED,
        ),
        "b": recovery_report(
            "b",
            DurableRecoveryStatus.VERIFIED,
        ),
        "c": recovery_report(
            "c",
            DurableRecoveryStatus.INCOMPLETE,
        ),
    }
    target, _ = guard(
        reports,
        policy=DurableRecoveryHealthPolicy(
            minimum_verified=2,
            max_incomplete=1,
        ),
    )
    report = target.inspect(
        ("c", "a", "b")
    )
    assert report.allowed
    assert report.verified == 2
    assert report.incomplete == 1


def test_health_decision_is_independent_of_input_order():
    reports = {
        item: recovery_report(
            item,
            DurableRecoveryStatus.VERIFIED,
        )
        for item in ("a", "b", "c")
    }
    target, _ = guard(reports)
    first = target.inspect(("a", "b", "c"))
    second = target.inspect(("c", "a", "b"))
    assert first.digest == second.digest
    assert first == second
