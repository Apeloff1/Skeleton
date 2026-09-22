"""End-to-end Jeeves shell AI orchestration over the hardened shell service."""

from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Callable

from skeleton.shells.ai.approval import AIPlanApproval, AIApprovalRegistry
from skeleton.shells.ai.budget import AIBudget
from skeleton.shells.ai.calibration import AICalibration
from skeleton.shells.ai.compiler import AIPlanCompiler, CompiledAIPlan
from skeleton.shells.ai.critic import AIPlanCritic, CritiqueReport
from skeleton.shells.ai.execution_backend import AIPlanExecutionBackend, ShellServiceExecutionBackend
from skeleton.shells.ai.journal import AIDecisionJournal
from skeleton.shells.ai.memory import AIOutcomeMemory
from skeleton.shells.ai.observation import ObservationBuilder
from skeleton.shells.ai.planner import AIPlanner, PlanningResult
from skeleton.shells.ai.provenance import AIDecisionProvenance
from skeleton.shells.ai.schema import schema_digest
from skeleton.shells.ai.session_evidence import SessionEvidenceStore, SessionExecutionEvidence
from skeleton.shells.ai.session import AISessionPhase, AIShellSession
from skeleton.shells.ai.tool_guard import AIToolGuardRegistry
from skeleton.shells.ai.types import AIIntent
from skeleton.shells.ai.verifier import PlanVerifier, VerificationReport
from skeleton.shells.execution_context import ExecutionContext
from skeleton.shells.plan_executor import PlanExecutionReport
from skeleton.shells.shell_service import ShellService


@dataclass(frozen=True)
class AIReviewBundle:
    planning: PlanningResult
    critique: CritiqueReport
    compiled: CompiledAIPlan | None

    def to_dict(self) -> dict[str, object]:
        return {
            "planning": self.planning.to_dict(),
            "critique": self.critique.to_dict(),
            "compiled": None if self.compiled is None else self.compiled.to_dict(),
        }


@dataclass(frozen=True)
class AIExecutionBundle:
    review: AIReviewBundle
    report: PlanExecutionReport
    verification: VerificationReport
    provenance: AIDecisionProvenance

    @property
    def ok(self) -> bool:
        return self.report.ok and self.verification.verified

    def to_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "review": self.review.to_dict(),
            "report": self.report.to_dict(),
            "verification": self.verification.to_dict(),
            "provenance": self.provenance.to_dict(),
        }


class AIShellOrchestrator:
    """AI plans; deterministic layers authorize; ShellService executes."""

    def __init__(
        self,
        *,
        planner: AIPlanner,
        critic: AIPlanCritic,
        compiler: AIPlanCompiler,
        shell_service: ShellService,
        approvals: AIApprovalRegistry | None = None,
        guards: AIToolGuardRegistry | None = None,
        verifier: PlanVerifier | None = None,
        observations: ObservationBuilder | None = None,
        memory: AIOutcomeMemory | None = None,
        calibration: AICalibration | None = None,
        journal: AIDecisionJournal | None = None,
        budget: AIBudget | None = None,
        execution_backend: AIPlanExecutionBackend | None = None,
        session_evidence: SessionEvidenceStore | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.planner = planner
        self.critic = critic
        self.compiler = compiler
        self.shell_service = shell_service
        self.execution_backend = execution_backend or ShellServiceExecutionBackend(shell_service)
        self.session_evidence = session_evidence
        self.approvals = approvals or AIApprovalRegistry(clock=clock)
        self.guards = guards or AIToolGuardRegistry()
        self.verifier = verifier or PlanVerifier()
        self.observations = observations or ObservationBuilder()
        self.memory = memory or AIOutcomeMemory(clock=clock)
        self.calibration = calibration or AICalibration()
        self.journal = journal or AIDecisionJournal(clock=clock)
        self.budget = budget or planner.budget
        self.planner.budget = self.budget
        self._clock = clock

    def review(
        self,
        session: AIShellSession,
        *,
        prior_observations: tuple[dict[str, object], ...] = (),
    ) -> AIReviewBundle:
        if session.phase is AISessionPhase.NEW:
            session.transition(AISessionPhase.PLANNING)
        if session.phase is not AISessionPhase.PLANNING:
            raise RuntimeError("AI session is not in planning phase")

        planning = self.planner.propose(
            session.intent,
            prior_observations=prior_observations,
        )
        session.set_proposal(planning.response.proposal)
        self.journal.append(
            "ai.plan.proposed",
            session_id=session.session_id,
            intent_id=session.intent.intent_id,
            proposal_id=planning.response.proposal.proposal_id,
            summary="model produced structured shell proposal",
            data={
                "model_id": self.planner.model.model_id,
                "proposal_fingerprint": planning.response.proposal.fingerprint,
            },
        )
        session.transition(AISessionPhase.REVIEW)
        self.budget.critique_call()
        critique = self.critic.critique(
            session.intent,
            planning.response.proposal,
            request=planning.request,
            response=planning.response,
        )
        compiled = None
        if critique.guardrails.ok and (
            critique.policy.allowed or critique.policy.requires_approval
        ):
            for action in planning.response.proposal.actions:
                self.guards.check_input(action)
            compiled = self.compiler.compile(session.intent, planning.response.proposal)

        self.journal.append(
            "ai.plan.reviewed",
            session_id=session.session_id,
            intent_id=session.intent.intent_id,
            proposal_id=planning.response.proposal.proposal_id,
            summary="deterministic AI shell review completed",
            data={
                "risk_score": critique.risk.score,
                "risk_band": critique.risk.band.value,
                "allowed": critique.policy.allowed,
                "requires_approval": critique.policy.requires_approval,
                "guardrail_errors": critique.guardrails.errors,
            },
        )
        return AIReviewBundle(planning, critique, compiled)

    def approve(
        self,
        session: AIShellSession,
        review: AIReviewBundle,
        *,
        principal: str,
        approved_by: str,
        ttl_seconds: float = 300.0,
    ) -> AIPlanApproval:
        if not review.critique.policy.requires_approval:
            raise RuntimeError("review does not require human approval")
        proposal = review.planning.response.proposal
        approval = self.approvals.approve(
            principal=principal,
            intent_fingerprint=session.intent.fingerprint,
            proposal_fingerprint=proposal.fingerprint,
            approved_by=approved_by,
            ttl_seconds=ttl_seconds,
        )
        self.journal.append(
            "ai.plan.approved",
            session_id=session.session_id,
            intent_id=session.intent.intent_id,
            proposal_id=proposal.proposal_id,
            summary="human approval bound to exact AI proposal",
            data={"approval_id": approval.approval_id, "approved_by": approved_by},
        )
        return approval

    def execute(
        self,
        session: AIShellSession,
        review: AIReviewBundle,
        *,
        context: ExecutionContext,
        approval: AIPlanApproval | None = None,
        execution_backend: AIPlanExecutionBackend | None = None,
        release_evidence_digest: str = "",
        runtime_trust_digest: str = "",
        authority_health_policy_digest: str = "",
    ) -> AIExecutionBundle:
        if session.phase is not AISessionPhase.REVIEW:
            raise RuntimeError("AI session is not ready for execution decision")
        if review.compiled is None:
            session.transition(AISessionPhase.DENIED, reason="proposal did not compile")
            raise RuntimeError("AI proposal is not executable")
        proposal = review.planning.response.proposal
        approval_id = ""
        if review.critique.policy.allowed:
            session.transition(AISessionPhase.APPROVED, reason="autonomy policy allowed plan")
        elif review.critique.policy.requires_approval:
            if approval is None:
                raise RuntimeError("human approval is required")
            self.approvals.consume(
                approval,
                principal=context.principal,
                intent_fingerprint=session.intent.fingerprint,
                proposal_fingerprint=proposal.fingerprint,
            )
            approval_id = approval.approval_id
            session.transition(AISessionPhase.APPROVED, reason="human approval validated")
        else:
            session.transition(AISessionPhase.DENIED, reason="AI policy denied plan")
            raise RuntimeError("AI policy denied plan")

        session.transition(AISessionPhase.EXECUTING)
        started = self._clock()
        active_backend = execution_backend or self.execution_backend
        try:
            report = active_backend.execute_plan(
                review.compiled.plan,
                context=context,
            )
            duration_ms = max(0.0, (self._clock() - started) * 1000.0)
            session.transition(AISessionPhase.VERIFYING)
            self.budget.verification_round()
            verification = self.verifier.verify(session.intent, report)

            session_evidence_digest = ""
            if self.session_evidence is not None:
                evidence = SessionExecutionEvidence.from_report(
                    session.session_id,
                    report,
                )
                self.session_evidence.put(evidence)
                session_evidence_digest = evidence.digest

            for action, step in zip(proposal.actions, report.steps):
                if step.dispatch is not None:
                    observation = self.observations.dispatch(step.dispatch)
                    self.guards.check_output(action, observation)

            success = report.ok and verification.verified
            self.memory.record(
                intent_fingerprint=session.intent.fingerprint,
                proposal_fingerprint=proposal.fingerprint,
                risk_score=review.critique.risk.score,
                success=success,
                duration_ms=duration_ms,
                verified=verification.verified,
                command_count=len(proposal.actions),
                model_id=proposal.model_id or self.planner.model.model_id,
            )
            model_key = proposal.model_id or self.planner.model.model_id
            self.calibration.record(
                model_key,
                predicted_confidence=proposal.confidence,
                success=report.ok,
                verified=verification.verified,
                latency_ms=duration_ms,
            )
            sandbox_binding = getattr(active_backend, "binding", None)
            sandbox_binding_digest = (
                ""
                if sandbox_binding is None
                else getattr(sandbox_binding, "digest", "")
            )
            provenance = AIDecisionProvenance(
                intent_fingerprint=session.intent.fingerprint,
                proposal_fingerprint=proposal.fingerprint,
                tool_catalog_digest=self.planner.catalog.digest,
                effect_digest=self.compiler.effects.digest,
                policy_fingerprint=self.planner.policy_fingerprint,
                schema_digest=schema_digest(),
                model_id=model_key,
                risk_score=review.critique.risk.score,
                approval_id=approval_id,
                receipt_root=active_backend.receipt_root(),
                execution_backend_id=active_backend.backend_id,
                session_evidence_digest=session_evidence_digest,
                sandbox_binding_digest=sandbox_binding_digest,
                release_evidence_digest=release_evidence_digest,
                runtime_trust_digest=runtime_trust_digest,
                authority_health_policy_digest=authority_health_policy_digest,
            )
            self.journal.append(
                "ai.plan.completed",
                session_id=session.session_id,
                intent_id=session.intent.intent_id,
                proposal_id=proposal.proposal_id,
                summary="AI shell plan execution and verification completed",
                data={
                    "ok": success,
                    "verified": verification.verified,
                    "duration_ms": duration_ms,
                    "provenance_digest": provenance.digest,
                    "execution_backend": active_backend.backend_id,
                    "session_evidence_digest": session_evidence_digest,
                    "sandbox_binding_digest": sandbox_binding_digest,
                    "release_evidence_digest": release_evidence_digest,
                    "runtime_trust_digest": runtime_trust_digest,
                    "authority_health_policy_digest": (
                        authority_health_policy_digest
                    ),
                },
            )
            if success:
                session.transition(AISessionPhase.COMPLETE)
            else:
                session.transition(
                    AISessionPhase.FAILED,
                    reason="execution or verification failed",
                )
            return AIExecutionBundle(review, report, verification, provenance)
        except BaseException as exc:
            if session.phase in {AISessionPhase.EXECUTING, AISessionPhase.VERIFYING}:
                session.transition(
                    AISessionPhase.FAILED,
                    reason=f"AI shell execution failed: {type(exc).__name__}",
                )
            self.journal.append(
                "ai.plan.failed",
                session_id=session.session_id,
                intent_id=session.intent.intent_id,
                proposal_id=proposal.proposal_id,
                summary="AI shell execution path raised before successful completion",
                data={"error_type": type(exc).__name__},
            )
            raise
