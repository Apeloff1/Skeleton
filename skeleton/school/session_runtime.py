"""Grand Jeeves session state machine.

This is the execution membrane between planning and observable learner work.
It turns the many deterministic policies in :mod:`skeleton.school` into a
single auditable lifecycle with explicit phase transitions, evidence gates,
recovery paths and commit semantics.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Sequence

from skeleton.school.ai_pipeline import PipelineKind, PipelineRequest, plan_pipeline
from skeleton.school.cocoding import CoCodingContext, choose_action, next_handoff
from skeleton.school.curriculum import CurriculumGraph
from skeleton.school.debugging import DebuggingPolicy
from skeleton.school.jeeves import JeevesControlPlane, JeevesSessionPlan
from skeleton.school.knowledge import KnowledgeGraph, KnowledgeState, rank_knowledge
from skeleton.school.student import StudentProfile


class SessionPhase(str, Enum):
    INTAKE = "intake"
    DIAGNOSE = "diagnose"
    ORIENT = "orient"
    TEACH = "teach"
    PRACTICE = "practice"
    CHALLENGE = "challenge"
    VERIFY = "verify"
    REFLECT = "reflect"
    COMMIT = "commit"
    SCHEDULE = "schedule"
    RECOVER = "recover"
    COMPLETE = "complete"


class TransitionKind(str, Enum):
    ADVANCE = "advance"
    REPAIR = "repair"
    ESCALATE = "escalate"
    DEESCALATE = "deescalate"
    PAUSE = "pause"
    COMPLETE = "complete"


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
    gates: tuple[EvidenceGate, ...]
    transitions: tuple[SessionTransition, ...]


@dataclass
class JeevesSessionRuntime:
    control: JeevesControlPlane
    curriculum: CurriculumGraph
    knowledge: KnowledgeGraph = field(default_factory=KnowledgeGraph)
    knowledge_state: KnowledgeState = field(default_factory=KnowledgeState)
    events: list[SessionEvent] = field(default_factory=list)
    phase: SessionPhase = SessionPhase.INTAKE
    _sequence: int = 0

    def begin(
        self,
        student: StudentProfile,
        *,
        session_id: str,
        query_terms: Sequence[str] = (),
        pipeline_kind: PipelineKind = PipelineKind.LESSON,
        cocoding: CoCodingContext | None = None,
    ) -> RuntimePlan:
        control = self.control.plan(student, query_terms=query_terms)
        primary = control.primary_skill
        candidates = rank_knowledge(self.knowledge, self.knowledge_state, query_terms=query_terms, goals=student.goals)
        request = PipelineRequest(
            kind=pipeline_kind,
            objective=primary or (query_terms[0] if query_terms else "advance the learner's current objective"),
            learner_skill=primary,
            require_tests=pipeline_kind not in {PipelineKind.LESSON, PipelineKind.ASSESS},
        )
        pipeline = plan_pipeline(request)
        context = cocoding or CoCodingContext()
        action = choose_action(context)
        handoff = next_handoff(context)
        gates = self._gates(control, pipeline_kind)
        transitions = self._transitions(gates, pipeline_kind)
        self._emit(SessionPhase.INTAKE, "session_opened", {"session_id": session_id})
        self.phase = SessionPhase.DIAGNOSE
        self._emit(self.phase, "control_plan_ready", {"primary_skill": primary or "none"})
        return RuntimePlan(
            session_id=session_id,
            control=control,
            phase=self.phase,
            pipeline_kind=pipeline_kind,
            pipeline_stages=tuple(step.stage.value for step in pipeline.steps),
            knowledge_candidates=tuple(candidate.node_id for candidate in candidates),
            co_coding_action=action.pattern.value,
            handoff_stage=handoff.value,
            gates=gates,
            transitions=transitions,
        )

    def transition(self, target: SessionPhase, *, rationale: str, evidence: Sequence[EvidenceGate] = ()) -> SessionTransition:
        if target == self.phase:
            raise ValueError("session is already in requested phase")
        allowed = {
            SessionPhase.INTAKE: {SessionPhase.DIAGNOSE},
            SessionPhase.DIAGNOSE: {SessionPhase.ORIENT, SessionPhase.RECOVER},
            SessionPhase.ORIENT: {SessionPhase.TEACH, SessionPhase.PRACTICE},
            SessionPhase.TEACH: {SessionPhase.PRACTICE, SessionPhase.VERIFY, SessionPhase.RECOVER},
            SessionPhase.PRACTICE: {SessionPhase.CHALLENGE, SessionPhase.VERIFY, SessionPhase.RECOVER},
            SessionPhase.CHALLENGE: {SessionPhase.VERIFY, SessionPhase.RECOVER},
            SessionPhase.VERIFY: {SessionPhase.REFLECT, SessionPhase.RECOVER, SessionPhase.CHALLENGE},
            SessionPhase.REFLECT: {SessionPhase.COMMIT, SessionPhase.RECOVER},
            SessionPhase.COMMIT: {SessionPhase.SCHEDULE, SessionPhase.COMPLETE},
            SessionPhase.SCHEDULE: {SessionPhase.COMPLETE},
            SessionPhase.RECOVER: {SessionPhase.TEACH, SessionPhase.PRACTICE, SessionPhase.ORIENT},
            SessionPhase.COMPLETE: set(),
        }
        if target not in allowed[self.phase]:
            raise ValueError(f"invalid session transition: {self.phase.value} -> {target.value}")
        gate_set = tuple(evidence)
        if target in {SessionPhase.VERIFY, SessionPhase.COMMIT} and any(g.required and not g.satisfied for g in gate_set):
            raise ValueError("required evidence gate is unsatisfied")
        source = self.phase
        kind = self._transition_kind(source, target)
        self.phase = target
        self._emit(target, f"transition:{kind.value}", {"from": source.value, "rationale": rationale})
        return SessionTransition(source, target, kind, rationale, gate_set)

    def record_evidence(self, *, event: str, **payload: str) -> SessionEvent:
        self._emit(self.phase, event, payload)
        return self.events[-1]

    def recover(self, *, reason: str) -> SessionTransition:
        if self.phase in {SessionPhase.COMPLETE, SessionPhase.INTAKE}:
            raise ValueError("recovery is not available in the current phase")
        source = self.phase
        self.phase = SessionPhase.RECOVER
        self._emit(self.phase, "recovery_required", {"reason": reason})
        return SessionTransition(source, SessionPhase.RECOVER, TransitionKind.REPAIR, reason)

    def _gates(self, control: JeevesSessionPlan, pipeline_kind: PipelineKind) -> tuple[EvidenceGate, ...]:
        gates = [
            EvidenceGate("objective", "learner objective is explicit", True, bool(control.primary_skill)),
            EvidenceGate("attempt", "learner has produced observable work", True, False),
            EvidenceGate("reasoning", "learner can explain the result", True, False),
            EvidenceGate("verification", "result has verification evidence", pipeline_kind not in {PipelineKind.LESSON}, False),
            EvidenceGate("reflection", "learner reflection is recorded", True, False),
        ]
        return tuple(gates)

    @staticmethod
    def _transition_kind(source: SessionPhase, target: SessionPhase) -> TransitionKind:
        if target == SessionPhase.RECOVER:
            return TransitionKind.REPAIR
        if target == SessionPhase.CHALLENGE:
            return TransitionKind.ESCALATE
        if target == SessionPhase.TEACH and source == SessionPhase.RECOVER:
            return TransitionKind.DEESCALATE
        if target == SessionPhase.COMPLETE:
            return TransitionKind.COMPLETE
        return TransitionKind.ADVANCE

    @staticmethod
    def _transitions(gates: tuple[EvidenceGate, ...], pipeline_kind: PipelineKind) -> tuple[SessionTransition, ...]:
        return (
            SessionTransition(SessionPhase.DIAGNOSE, SessionPhase.ORIENT, TransitionKind.ADVANCE, "diagnostic evidence determines the starting point", gates[:1]),
            SessionTransition(SessionPhase.PRACTICE, SessionPhase.CHALLENGE, TransitionKind.ESCALATE, "sufficient evidence permits harder transfer", gates[1:3]),
            SessionTransition(SessionPhase.PRACTICE, SessionPhase.RECOVER, TransitionKind.REPAIR, "failure or overload requires scaffolding", ()),
            SessionTransition(SessionPhase.VERIFY, SessionPhase.REFLECT, TransitionKind.ADVANCE, "verification evidence is available", gates[1:4]),
            SessionTransition(SessionPhase.REFLECT, SessionPhase.COMMIT, TransitionKind.ADVANCE, "reflection converts experience into durable evidence", gates[-1:]),
            SessionTransition(SessionPhase.COMMIT, SessionPhase.COMPLETE, TransitionKind.COMPLETE, f"close {pipeline_kind.value} session"),
        )

    def _emit(self, phase: SessionPhase, event: str, payload: dict[str, str]) -> None:
        self._sequence += 1
        self.events.append(SessionEvent(self._sequence, phase, event, tuple(sorted(payload.items()))))
