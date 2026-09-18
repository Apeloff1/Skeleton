"""Long-lived AI shell service facade over planning and shell execution."""

from __future__ import annotations

from dataclasses import dataclass
import uuid

from skeleton.shells.ai.approval_quorum import AIApprovalQuorumStore, QuorumApproval
from skeleton.shells.ai.assurance import AIExecutionAssuranceInspector
from skeleton.shells.ai.diagnostics import AIDiagnosticsReport, AIShellDiagnostics
from skeleton.shells.ai.execution_backend import AIPlanExecutionBackend
from skeleton.shells.ai.execution_seal import ExecutionSeal, ExecutionSealAuthority
from skeleton.shells.ai.governance import AIShellGovernance
from skeleton.shells.ai.lifecycle import AIServicePhase, AIServiceState
from skeleton.shells.ai.orchestrator import AIExecutionBundle, AIReviewBundle, AIShellOrchestrator
from skeleton.shells.ai.preconditions import Preconditions, PreconditionChecker, PreconditionReport
from skeleton.shells.ai.review import AIReviewBuilder, AIReviewView
from skeleton.shells.ai.sandbox_backend import VerifiedSandboxExecutionBackend
from skeleton.shells.ai.seal_registry import ExecutionSealRegistry, SealUse
from skeleton.shells.ai.session import AIShellSession
from skeleton.shells.ai.stale_guard import AIPlanStaleGuard, PlanPin
from skeleton.shells.ai.startup_release import AIStartupReleaseGuard, RuntimeReleaseExpectation, StartupReleaseReport
from skeleton.shells.ai.types import AIIntent
from skeleton.shells.execution_context import ExecutionContext


@dataclass(frozen=True)
class AIServiceStatus:
    phase: AIServicePhase
    diagnostics: dict[str, object]
    governance: dict[str, object]
    shell_phase: str
    release: dict[str, object] | None = None

    def to_dict(self) -> dict[str, object]:
        data = {
            "phase": self.phase.value,
            "diagnostics": dict(self.diagnostics),
            "governance": dict(self.governance),
            "shell_phase": self.shell_phase,
        }
        if self.release is not None:
            data["release"] = dict(self.release)
        return data


class AIShellService:
    """Explicit service boundary for Jeeves shell planning and execution."""

    def __init__(
        self,
        orchestrator: AIShellOrchestrator,
        diagnostics: AIShellDiagnostics,
        governance: AIShellGovernance,
        *,
        release_guard: AIStartupReleaseGuard | None = None,
        release_expectation: RuntimeReleaseExpectation | None = None,
        assurance: AIExecutionAssuranceInspector | None = None,
        approval_quorum: AIApprovalQuorumStore | None = None,
    ) -> None:
        if (release_guard is None) != (release_expectation is None):
            raise ValueError("release_guard and release_expectation must be configured together")
        self.orchestrator = orchestrator
        self.diagnostics = diagnostics
        self.governance = governance
        self.release_guard = release_guard
        self.release_expectation = release_expectation
        self.assurance = assurance
        self.approval_quorum = approval_quorum
        self._release_report: StartupReleaseReport | None = None
        self.state = AIServiceState()
        self.review_builder = AIReviewBuilder(orchestrator.compiler.effects)
        self.stale_guard = AIPlanStaleGuard()
        self._pins: dict[str, PlanPin] = {}
        self._max_pins = 10000

    def start(self) -> AIDiagnosticsReport:
        if self.state.phase is AIServicePhase.NEW:
            self.state.transition(AIServicePhase.STARTING)
        if self.state.phase is not AIServicePhase.STARTING:
            return self.diagnostics.inspect()
        report = self.diagnostics.inspect()
        shell_ready = self.orchestrator.shell_service.state.ready()
        if report.errors:
            self.state.transition(AIServicePhase.FAILED, reason="AI diagnostics failed")
            return report
        if not shell_ready:
            self.state.transition(AIServicePhase.DEGRADED, reason="shell service is not ready")
            return report
        if self.release_guard is not None and self.release_expectation is not None:
            self._release_report = self.release_guard.inspect(self.release_expectation)
            if not self._release_report.allowed:
                self.state.transition(
                    AIServicePhase.FAILED,
                    reason="AI release/channel verification failed",
                )
                return report
        self.state.transition(AIServicePhase.READY)
        return report

    def _release_digest(self) -> str:
        return "" if self._release_report is None else self._release_report.evidence_digest

    def _require_release_current(self) -> None:
        if self.release_guard is None or self.release_expectation is None:
            return
        report = self.release_guard.inspect(self.release_expectation)
        self._release_report = report
        if report.allowed:
            return
        if self.state.phase is AIServicePhase.READY:
            self.state.transition(
                AIServicePhase.DEGRADED,
                reason="AI release/channel drift detected",
            )
        raise RuntimeError("AI release/channel verification failed")

    def new_session(self, intent: AIIntent, *, session_id: str | None = None) -> AIShellSession:
        if not self.state.ready():
            raise RuntimeError("AI shell service is not ready")
        self._require_release_current()
        return AIShellSession(session_id or uuid.uuid4().hex, intent)

    def review(self, session: AIShellSession) -> tuple[AIReviewBundle, AIReviewView]:
        if not self.state.ready():
            raise RuntimeError("AI shell service is not ready")
        self._require_release_current()
        bundle = self.orchestrator.review(session)
        proposal = bundle.planning.response.proposal
        self.governance.require_not_quarantined(
            model_id=proposal.model_id or self.orchestrator.planner.model.model_id,
            proposal_fingerprint=proposal.fingerprint,
            commands=tuple(action.command for action in proposal.actions),
        )
        view = self.review_builder.build(session.intent, proposal, bundle.critique)
        if bundle.compiled is not None:
            if session.session_id not in self._pins and len(self._pins) >= self._max_pins:
                raise RuntimeError("AI shell plan-pin capacity exhausted")
            self._pins[session.session_id] = self.stale_guard.pin(
                session.intent,
                proposal,
                bundle.compiled,
                self.orchestrator.planner.catalog,
                self.orchestrator.compiler.effects,
                self.governance.current_policy(),
            )
        return bundle, view

    def _quorum_digest(
        self,
        session: AIShellSession,
        review: AIReviewBundle,
        *,
        principal: str,
        quorum_approval: QuorumApproval | None,
    ) -> str:
        if quorum_approval is None:
            return ""
        if self.approval_quorum is None:
            raise RuntimeError("quorum approval store is not configured")
        proposal = review.planning.response.proposal
        current = self.approval_quorum.require(
            quorum_approval,
            principal=principal,
            intent_fingerprint=session.intent.fingerprint,
            proposal_fingerprint=proposal.fingerprint,
        )
        return current.digest

    def seal_review(
        self,
        session: AIShellSession,
        review: AIReviewBundle,
        *,
        principal: str,
        authority: ExecutionSealAuthority,
        preconditions: Preconditions | None = None,
        approval=None,
        quorum_approval: QuorumApproval | None = None,
        ttl_seconds: float = 60.0,
    ) -> ExecutionSeal:
        """Issue short-lived signed authority for one exact reviewed plan.

        Issuance performs no execution. Approval is validated but not consumed;
        normal execution consumes it after the seal is consumed.
        """

        if not self.state.ready():
            raise RuntimeError("AI shell service is not ready")
        self._require_release_current()
        if review.compiled is None:
            raise RuntimeError("AI shell proposal is not executable")
        proposal = review.planning.response.proposal
        pin = self._pins.get(session.session_id)
        if pin is None:
            raise RuntimeError("AI shell reviewed plan has no execution pin")
        self.stale_guard.require_current(
            pin,
            intent=session.intent,
            proposal=proposal,
            compiled=review.compiled,
            catalog=self.orchestrator.planner.catalog,
            effects=self.orchestrator.compiler.effects,
            policy=self.governance.current_policy(),
        )
        approval_id = ""
        if review.critique.policy.requires_approval:
            if approval is None:
                raise RuntimeError("human approval is required before execution sealing")
            self.orchestrator.approvals.require(
                approval,
                principal=principal,
                intent_fingerprint=session.intent.fingerprint,
                proposal_fingerprint=proposal.fingerprint,
            )
            approval_id = approval.approval_id
        quorum_digest = self._quorum_digest(
            session,
            review,
            principal=principal,
            quorum_approval=quorum_approval,
        )
        return authority.issue(
            principal=principal,
            session_id=session.session_id,
            plan_pin=pin,
            preconditions_digest="" if preconditions is None else preconditions.digest,
            approval_id=approval_id,
            release_evidence_digest=self._release_digest(),
            assurance_digest=quorum_digest,
            ttl_seconds=ttl_seconds,
        )

    def execute_sealed(
        self,
        session: AIShellSession,
        review: AIReviewBundle,
        *,
        context: ExecutionContext,
        seal: ExecutionSeal,
        seal_registry: ExecutionSealRegistry,
        preconditions: Preconditions | None = None,
        precondition_checker: PreconditionChecker | None = None,
        approval=None,
        execution_backend: AIPlanExecutionBackend | None = None,
    ) -> tuple[AIExecutionBundle, PreconditionReport | None, SealUse]:
        """Execute only after preconditions and a single-use signed seal pass."""

        if not self.state.ready():
            raise RuntimeError("AI shell service is not ready")
        self._require_release_current()
        if review.compiled is None:
            raise RuntimeError("AI shell proposal is not executable")
        pin = self._pins.get(session.session_id)
        if pin is None:
            raise RuntimeError("AI shell reviewed plan has no execution pin")
        precondition_report = None
        precondition_digest = ""
        if preconditions is not None:
            if precondition_checker is None:
                raise RuntimeError("precondition checker is required")
            precondition_report = precondition_checker.require(preconditions)
            precondition_digest = preconditions.digest
        approval_id = "" if approval is None else approval.approval_id
        self._require_assurance(
            review,
            execution_backend=execution_backend,
            sealed=True,
            preconditions_verified=(
                precondition_report is not None and precondition_report.ok
            ),
            human_approved=(
                review.critique.policy.requires_approval
                and approval is not None
            ),
        )
        use = seal_registry.consume(
            seal,
            principal=context.principal,
            session_id=session.session_id,
            plan_pin=pin,
            preconditions_digest=precondition_digest,
            approval_id=approval_id,
            release_evidence_digest=self._release_digest(),
        )
        result = self._execute_reviewed(
            session,
            review,
            context=context,
            approval=approval,
            execution_backend=execution_backend,
            sealed=True,
            preconditions_verified=(
                precondition_report is not None and precondition_report.ok
            ),
            human_approved=(
                review.critique.policy.requires_approval
                and approval is not None
            ),
        )
        return result, precondition_report, use

    def _require_assurance(
        self,
        review: AIReviewBundle,
        *,
        execution_backend: AIPlanExecutionBackend | None,
        sealed: bool,
        preconditions_verified: bool = False,
        human_approved: bool = False,
    ) -> None:
        if self.assurance is None:
            return
        active_backend = execution_backend or self.orchestrator.execution_backend
        self.assurance.require(
            review.critique.risk.band,
            sealed=sealed,
            sandbox_verified=isinstance(
                active_backend,
                VerifiedSandboxExecutionBackend,
            ),
            backend_id=active_backend.backend_id,
            release_verified=(
                self._release_report is not None
                and self._release_report.allowed
            ),
            preconditions_verified=preconditions_verified,
            human_approved=human_approved,
        )

    def execute(
        self,
        session: AIShellSession,
        review: AIReviewBundle,
        *,
        context: ExecutionContext,
        approval=None,
        execution_backend: AIPlanExecutionBackend | None = None,
    ) -> AIExecutionBundle:
        return self._execute_reviewed(
            session,
            review,
            context=context,
            approval=approval,
            execution_backend=execution_backend,
            sealed=False,
            preconditions_verified=False,
            human_approved=(
                review.critique.policy.requires_approval
                and approval is not None
            ),
        )

    def _execute_reviewed(
        self,
        session: AIShellSession,
        review: AIReviewBundle,
        *,
        context: ExecutionContext,
        approval=None,
        execution_backend: AIPlanExecutionBackend | None = None,
        sealed: bool,
        preconditions_verified: bool = False,
        human_approved: bool = False,
    ) -> AIExecutionBundle:
        if not self.state.ready():
            raise RuntimeError("AI shell service is not ready")
        self._require_release_current()
        self._require_assurance(
            review,
            execution_backend=execution_backend,
            sealed=sealed,
            preconditions_verified=preconditions_verified,
            human_approved=human_approved,
        )
        proposal = review.planning.response.proposal
        pin = self._pins.get(session.session_id)
        if review.compiled is not None:
            if pin is None:
                raise RuntimeError("AI shell reviewed plan has no execution pin")
            self.stale_guard.require_current(
                pin,
                intent=session.intent,
                proposal=proposal,
                compiled=review.compiled,
                catalog=self.orchestrator.planner.catalog,
                effects=self.orchestrator.compiler.effects,
                policy=self.governance.current_policy(),
            )
        self.governance.require_not_quarantined(
            model_id=proposal.model_id or self.orchestrator.planner.model.model_id,
            proposal_fingerprint=proposal.fingerprint,
            commands=tuple(action.command for action in proposal.actions),
        )
        try:
            return self.orchestrator.execute(
                session,
                review,
                context=context,
                approval=approval,
                execution_backend=execution_backend,
                release_evidence_digest=self._release_digest(),
            )
        finally:
            if session.phase.value in {"complete", "failed", "denied", "cancelled"}:
                self._pins.pop(session.session_id, None)

    def status(self) -> AIServiceStatus:
        return AIServiceStatus(
            self.state.phase,
            self.diagnostics.inspect().to_dict(),
            self.governance.snapshot().to_dict(),
            self.orchestrator.shell_service.state.phase.value,
            None if self._release_report is None else self._release_report.to_dict(),
        )
