"""Grand Jeeves session state machine with evidence-backed arbitration."""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Sequence
from skeleton.school.ai_pipeline import PipelineKind, PipelineRequest, plan_pipeline
from skeleton.school.cocoding import CodingPhase, CoCodingContext, HandoffStage, choose_action, next_handoff
from skeleton.school.curriculum import CurriculumGraph
from skeleton.school.decision_ledger import DecisionDisposition, DecisionLedger, EvidenceKind, EvidenceRef
from skeleton.school.decision_policy import EvidenceSignal, arbitrate
from skeleton.school.epistemics import EpistemicEngine, EvidencePolarity, EpistemicEvidence
from skeleton.school.jeeves import JeevesControlPlane, JeevesSessionPlan
from skeleton.school.knowledge import KnowledgeGraph, KnowledgeState, rank_knowledge
from skeleton.school.outcomes import OutcomeResult, SessionOutcome
from skeleton.school.student import StudentProfile


class SessionPhase(str, Enum):
    INTAKE="intake"; DIAGNOSE="diagnose"; ORIENT="orient"; TEACH="teach"; PRACTICE="practice"; CHALLENGE="challenge"; VERIFY="verify"; REFLECT="reflect"; COMMIT="commit"; SCHEDULE="schedule"; RECOVER="recover"; COMPLETE="complete"

class TransitionKind(str, Enum):
    ADVANCE="advance"; REPAIR="repair"; ESCALATE="escalate"; DEESCALATE="deescalate"; PAUSE="pause"; COMPLETE="complete"

@dataclass(frozen=True)
class EvidenceGate:
    gate_id: str
    description: str
    required: bool = True
    satisfied: bool = False

@dataclass(frozen=True)
class SessionEvent:
    sequence: int
    phase: SessionPhase
    event: str
    payload: tuple[tuple[str, str], ...] = ()

@dataclass(frozen=True)
class SessionTransition:
    source: SessionPhase
    target: SessionPhase
    kind: TransitionKind
    rationale: str
    gates: tuple[EvidenceGate, ...] = ()

@dataclass(frozen=True)
class RuntimePlan:
    session_id: str
    control: JeevesSessionPlan
    phase: SessionPhase
    pipeline_kind: PipelineKind
    pipeline_stages: tuple[str, ...]
    knowledge_candidates: tuple[str, ...]
    co_coding_action: str
    handoff_stage: str
    arbitration_action: str
    arbitration_confidence: float
    gates: tuple[EvidenceGate, ...]
    transitions: tuple[SessionTransition, ...]
    selected_policy: str = ""
    policy_margin: float = 0.0
    rejected_policies: tuple[str, ...] = ()

@dataclass
class JeevesSessionRuntime:
    control: JeevesControlPlane
    curriculum: CurriculumGraph
    knowledge: KnowledgeGraph = field(default_factory=KnowledgeGraph)
    knowledge_state: KnowledgeState = field(default_factory=KnowledgeState)
    ledger: DecisionLedger = field(default_factory=DecisionLedger)
    events: list[SessionEvent] = field(default_factory=list)
    phase: SessionPhase = SessionPhase.INTAKE
    session_id: str = ""
    _sequence: int = 0
    _last_decision_id: str | None = None
    _selected_policy: str | None = None

    @property
    def epistemics(self) -> EpistemicEngine:
        return self.control.epistemics

    def begin(self, student: StudentProfile, *, session_id: str, query_terms: Sequence[str] = (), pipeline_kind: PipelineKind = PipelineKind.LESSON, cocoding: CoCodingContext | None = None) -> RuntimePlan:
        self.session_id = session_id
        control = self.control.plan(student, query_terms=query_terms)
        primary = control.primary_skill
        candidates = rank_knowledge(self.knowledge, self.knowledge_state, query_terms=query_terms, goals=student.goals)
        objective = primary or (query_terms[0] if query_terms else "advance the learner's current objective")
        pipeline = plan_pipeline(PipelineRequest(kind=pipeline_kind, objective=objective, learner_skill=primary, require_tests=pipeline_kind not in {PipelineKind.LESSON, PipelineKind.ASSESS}))
        context = cocoding or CoCodingContext(CodingPhase.UNDERSTAND, HandoffStage.DEMONSTRATE)
        action = choose_action(context)
        handoff = next_handoff(context.handoff, successful=False, learner_explained=False)
        signals: list[EvidenceSignal] = []
        if primary in self.knowledge_state.misconceptions:
            signals.append(EvidenceSignal("contradiction", 1.0))
        arbitration = arbitrate(self.knowledge_state, primary or objective, signals=signals)
        gates = self._gates(control, pipeline_kind, objective)
        transitions = self._transitions(gates, pipeline_kind)
        selected_policy = control.policy_competition.selected.action.value if control.policy_competition else arbitration.action.value
        self._selected_policy = selected_policy
        rejected_policies = tuple(c.action.value for c in control.policy_competition.rejected) if control.policy_competition else ()
        self._emit(SessionPhase.INTAKE, "session_opened", {"session_id": session_id})
        self.phase = SessionPhase.DIAGNOSE
        self._emit(self.phase, "control_plan_ready", {"primary_skill": primary or "none", "arbitration": selected_policy, "policy": selected_policy})
        self._record_decision(
            decision_id=f"{session_id}:orient", action=selected_policy,
            rationale=(control.policy_competition.rationale if control.policy_competition else arbitration.rationale),
            state={"skill": primary or objective, "mastery": self.knowledge_state.mastery(primary or objective)},
            policy={"confidence": arbitration.confidence, "counterfactual_margin": control.policy_competition.margin if control.policy_competition else 0.0, "calibrated_reliability": control.policy_calibrator.snapshot(), "rejected_policies": rejected_policies, "executed_policy": selected_policy},
        )
        if control.policy_competition:
            for candidate in control.policy_competition.rejected:
                self._record_decision(
                    decision_id=f"{session_id}:alternative:{candidate.action.value}", action=candidate.action.value,
                    rationale=candidate.rationale + ("counterfactual alternative", "not executed"),
                    state={"skill": primary or objective},
                    policy={"selected": selected_policy, "counterfactual": True, "calibrated_reliability": control.policy_calibrator.snapshot()},
                    disposition=DecisionDisposition.REJECTED,
                )
        return RuntimePlan(session_id, control, self.phase, pipeline_kind, tuple(s.stage.value for s in pipeline.steps), tuple(c.node_id for c in candidates), action.pattern.value, handoff.value, selected_policy, arbitration.confidence, gates, transitions, selected_policy, control.policy_competition.margin if control.policy_competition else 0.0, rejected_policies)

    def record_outcome(self, student: StudentProfile, outcome: SessionOutcome) -> OutcomeResult:
        if not self.session_id:
            raise ValueError("begin a session before recording an outcome")
        policy = self._selected_policy
        result = self.control.record_outcome(student, outcome, policy_action=policy)
        outcome_id = f"{self.session_id}:outcome:{self._sequence + 1}"
        self.ledger.register_evidence(EvidenceRef(outcome_id, EvidenceKind.ASSESSMENT, outcome.skill_id, outcome.kind.value, max(0.0, min(1.0, outcome.score)), "outcome"))
        self._record_decision(decision_id=f"{self.session_id}:outcome:{self._sequence + 1}", action=f"outcome:{outcome.kind.value}", rationale=(f"score={outcome.score:.3f}", f"policy={policy or 'unknown'}"), evidence=(outcome_id,), state={"skill": outcome.skill_id, "score": outcome.score}, policy={"executed_policy": policy or "unknown", "calibration": self.control.policy_calibrator.snapshot()}, disposition=DecisionDisposition.ACCEPTED)
        self._emit(self.phase, "outcome_recorded", {"kind": outcome.kind.value, "skill": outcome.skill_id, "policy": policy or "unknown"})
        return result

    def transition(self, target: SessionPhase, *, rationale: str, evidence: Sequence[EvidenceGate] = ()) -> SessionTransition:
        allowed = {SessionPhase.INTAKE:{SessionPhase.DIAGNOSE}, SessionPhase.DIAGNOSE:{SessionPhase.ORIENT,SessionPhase.RECOVER}, SessionPhase.ORIENT:{SessionPhase.TEACH,SessionPhase.PRACTICE}, SessionPhase.TEACH:{SessionPhase.PRACTICE,SessionPhase.VERIFY,SessionPhase.RECOVER}, SessionPhase.PRACTICE:{SessionPhase.CHALLENGE,SessionPhase.VERIFY,SessionPhase.RECOVER}, SessionPhase.CHALLENGE:{SessionPhase.VERIFY,SessionPhase.RECOVER}, SessionPhase.VERIFY:{SessionPhase.REFLECT,SessionPhase.RECOVER,SessionPhase.CHALLENGE}, SessionPhase.REFLECT:{SessionPhase.COMMIT,SessionPhase.RECOVER}, SessionPhase.COMMIT:{SessionPhase.SCHEDULE,SessionPhase.COMPLETE}, SessionPhase.SCHEDULE:{SessionPhase.COMPLETE}, SessionPhase.RECOVER:{SessionPhase.TEACH,SessionPhase.PRACTICE,SessionPhase.ORIENT}, SessionPhase.COMPLETE:set()}
        if target == self.phase: raise ValueError("session is already in requested phase")
        if target not in allowed[self.phase]: raise ValueError(f"invalid session transition: {self.phase.value} -> {target.value}")
        gate_set = tuple(evidence)
        if target in {SessionPhase.VERIFY, SessionPhase.COMMIT} and any(g.required and not g.satisfied for g in gate_set): raise ValueError("required evidence gate is unsatisfied")
        source = self.phase; kind = self._transition_kind(source, target); self.phase = target
        self._emit(target, f"transition:{kind.value}", {"from": source.value, "rationale": rationale})
        self._record_decision(decision_id=f"{self.session_id}:transition:{self._sequence}", action=f"{kind.value}:{target.value}", rationale=(rationale,), state={"source":source.value,"target":target.value}, policy={"gate_count":len(gate_set), "selected_policy": self._selected_policy or "unknown"})
        return SessionTransition(source, target, kind, rationale, gate_set)

    def record_evidence(self, *, event: str, subject: str = "", claim: str = "", score: float | None = None, polarity: EvidencePolarity = EvidencePolarity.NEUTRAL, source_id: str = "runtime", **payload: str) -> SessionEvent:
        if claim:
            evidence_id = f"{self.session_id}:evidence:{self._sequence + 1}"
            strength = 1.0 if score is None else max(0.0, min(1.0, score))
            update = self.epistemics.observe(EpistemicEvidence(evidence_id=evidence_id, claim=claim, polarity=polarity, strength=strength, source_id=source_id, step=self._sequence))
            self.ledger.register_evidence(EvidenceRef(evidence_id, EvidenceKind.OBSERVATION, subject or claim, event, strength, source_id))
            self._emit(self.phase, event, payload | {"claim": claim})
            self._record_decision(decision_id=f"{self.session_id}:evidence:{self._sequence}", action=f"observe:{claim}", rationale=update.rationale, evidence=(evidence_id,), state={"confidence": update.belief.confidence, "contradiction": update.contradiction}, policy={"polarity": polarity.value, "selected_policy": self._selected_policy or "unknown"})
            return self.events[-1]
        self._emit(self.phase, event, payload); return self.events[-1]

    def recover(self, *, reason: str) -> SessionTransition:
        if self.phase in {SessionPhase.COMPLETE, SessionPhase.INTAKE}: raise ValueError("recovery is not available in the current phase")
        source = self.phase; self.phase = SessionPhase.RECOVER; self._emit(self.phase, "recovery_required", {"reason": reason})
        self._record_decision(decision_id=f"{self.session_id}:recover:{self._sequence}", action=TransitionKind.REPAIR.value, rationale=(reason,), state={"source":source.value}, policy={"selected_policy": self._selected_policy or "unknown"})
        return SessionTransition(source, SessionPhase.RECOVER, TransitionKind.REPAIR, reason)

    def _gates(self, control: JeevesSessionPlan, pipeline_kind: PipelineKind, objective: str) -> tuple[EvidenceGate, ...]:
        return (EvidenceGate("objective", "learner objective is explicit", True, bool(control.primary_skill or objective)), EvidenceGate("attempt", "learner has produced observable work", True, False), EvidenceGate("reasoning", "learner can explain the result", True, False), EvidenceGate("verification", "result has verification evidence", pipeline_kind not in {PipelineKind.LESSON}, False), EvidenceGate("reflection", "learner reflection is recorded", True, False))

    @staticmethod
    def _transition_kind(source: SessionPhase, target: SessionPhase) -> TransitionKind:
        if target == SessionPhase.RECOVER: return TransitionKind.REPAIR
        if target == SessionPhase.CHALLENGE: return TransitionKind.ESCALATE
        if target == SessionPhase.TEACH and source == SessionPhase.RECOVER: return TransitionKind.DEESCALATE
        if target == SessionPhase.COMPLETE: return TransitionKind.COMPLETE
        return TransitionKind.ADVANCE

    @staticmethod
    def _transitions(gates: tuple[EvidenceGate, ...], pipeline_kind: PipelineKind) -> tuple[SessionTransition, ...]:
        return (SessionTransition(SessionPhase.DIAGNOSE, SessionPhase.ORIENT, TransitionKind.ADVANCE, "diagnostic evidence determines the starting point", gates[:1]), SessionTransition(SessionPhase.PRACTICE, SessionPhase.CHALLENGE, TransitionKind.ESCALATE, "sufficient evidence permits harder transfer", gates[1:3]), SessionTransition(SessionPhase.PRACTICE, SessionPhase.RECOVER, TransitionKind.REPAIR, "failure or overload requires scaffolding"), SessionTransition(SessionPhase.VERIFY, SessionPhase.REFLECT, TransitionKind.ADVANCE, "verification evidence is available", gates[1:4]), SessionTransition(SessionPhase.REFLECT, SessionPhase.COMMIT, TransitionKind.ADVANCE, "reflection converts experience into durable evidence", gates[-1:]), SessionTransition(SessionPhase.COMMIT, SessionPhase.COMPLETE, TransitionKind.COMPLETE, f"close {pipeline_kind.value} session"))

    def _record_decision(self, *, decision_id: str, action: str, rationale: Sequence[str], state: dict[str, object], policy: dict[str, object], evidence: Sequence[str] = (), disposition: DecisionDisposition = DecisionDisposition.PROPOSED) -> None:
        predecessors = (self._last_decision_id,) if self._last_decision_id else ()
        record = self.ledger.append(session_id=self.session_id, decision_id=decision_id, domain="session_runtime", action=action, rationale=rationale, evidence=evidence, predecessors=predecessors, state=state, policy=policy, disposition=disposition)
        self._last_decision_id = record.decision_id

    def _emit(self, phase: SessionPhase, event: str, payload: dict[str, str]) -> None:
        self._sequence += 1; self.events.append(SessionEvent(self._sequence, phase, event, tuple(sorted(payload.items()))))
