"""Long-lived AI shell service facade over planning and shell execution."""

from __future__ import annotations

from dataclasses import dataclass
import uuid

from skeleton.shells.ai.diagnostics import AIDiagnosticsReport, AIShellDiagnostics
from skeleton.shells.ai.governance import AIShellGovernance
from skeleton.shells.ai.lifecycle import AIServicePhase, AIServiceState
from skeleton.shells.ai.orchestrator import AIExecutionBundle, AIReviewBundle, AIShellOrchestrator
from skeleton.shells.ai.review import AIReviewBuilder, AIReviewView
from skeleton.shells.ai.session import AIShellSession
from skeleton.shells.ai.types import AIIntent
from skeleton.shells.execution_context import ExecutionContext


@dataclass(frozen=True)
class AIServiceStatus:
    phase: AIServicePhase
    diagnostics: dict[str, object]
    governance: dict[str, object]
    shell_phase: str

    def to_dict(self) -> dict[str, object]:
        return {
            "phase": self.phase.value,
            "diagnostics": dict(self.diagnostics),
            "governance": dict(self.governance),
            "shell_phase": self.shell_phase,
        }


class AIShellService:
    """Explicit service boundary for Jeeves shell planning and execution."""

    def __init__(
        self,
        orchestrator: AIShellOrchestrator,
        diagnostics: AIShellDiagnostics,
        governance: AIShellGovernance,
    ) -> None:
        self.orchestrator = orchestrator
        self.diagnostics = diagnostics
        self.governance = governance
        self.state = AIServiceState()
        self.review_builder = AIReviewBuilder(orchestrator.compiler.effects)

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
        self.state.transition(AIServicePhase.READY)
        return report

    def new_session(self, intent: AIIntent, *, session_id: str | None = None) -> AIShellSession:
        if not self.state.ready():
            raise RuntimeError("AI shell service is not ready")
        return AIShellSession(session_id or uuid.uuid4().hex, intent)

    def review(self, session: AIShellSession) -> tuple[AIReviewBundle, AIReviewView]:
        if not self.state.ready():
            raise RuntimeError("AI shell service is not ready")
        bundle = self.orchestrator.review(session)
        proposal = bundle.planning.response.proposal
        self.governance.require_not_quarantined(
            model_id=proposal.model_id or self.orchestrator.planner.model.model_id,
            proposal_fingerprint=proposal.fingerprint,
            commands=tuple(action.command for action in proposal.actions),
        )
        view = self.review_builder.build(session.intent, proposal, bundle.critique)
        return bundle, view

    def execute(
        self,
        session: AIShellSession,
        review: AIReviewBundle,
        *,
        context: ExecutionContext,
        approval=None,
    ) -> AIExecutionBundle:
        if not self.state.ready():
            raise RuntimeError("AI shell service is not ready")
        proposal = review.planning.response.proposal
        self.governance.require_not_quarantined(
            model_id=proposal.model_id or self.orchestrator.planner.model.model_id,
            proposal_fingerprint=proposal.fingerprint,
            commands=tuple(action.command for action in proposal.actions),
        )
        return self.orchestrator.execute(
            session,
            review,
            context=context,
            approval=approval,
        )

    def status(self) -> AIServiceStatus:
        return AIServiceStatus(
            self.state.phase,
            self.diagnostics.inspect().to_dict(),
            self.governance.snapshot().to_dict(),
            self.orchestrator.shell_service.state.phase.value,
        )
