import pytest

from skeleton.school.ai_pipeline import PipelineKind
from skeleton.school.curriculum import CurriculumGraph, CurriculumNode
from skeleton.school.jeeves import JeevesControlPlane
from skeleton.school.knowledge import KnowledgeGraph, KnowledgeNode
from skeleton.school.session_runtime import EvidenceGate, JeevesSessionRuntime, SessionPhase
from skeleton.school.student import StudentProfile


def _runtime() -> JeevesSessionRuntime:
    curriculum = CurriculumGraph()
    curriculum.add(CurriculumNode("python", "Python Foundations"))
    knowledge = KnowledgeGraph()
    knowledge.add_node(KnowledgeNode("python", "Python Foundations", tags=("python",)))
    return JeevesSessionRuntime(JeevesControlPlane(curriculum), curriculum, knowledge)


def test_runtime_constructs_auditable_plan_and_lifecycle():
    runtime = _runtime()
    student = StudentProfile("student-1", goals=["python"])
    plan = runtime.begin(student, session_id="s-1", query_terms=("python",), pipeline_kind=PipelineKind.LESSON)
    assert runtime.phase is SessionPhase.DIAGNOSE
    assert plan.session_id == "s-1"
    assert "reflect" in plan.pipeline_stages
    assert plan.knowledge_candidates == ("python",)
    runtime.transition(SessionPhase.ORIENT, rationale="ready")
    runtime.transition(SessionPhase.TEACH, rationale="introduce concept")
    runtime.record_evidence(event="learner_attempt", score="0.9")
    assert runtime.events[-1].sequence >= 3


def test_runtime_rejects_illegal_transition_and_unsatisfied_gate():
    runtime = _runtime()
    runtime.begin(StudentProfile("student-2"), session_id="s-2")
    with pytest.raises(ValueError):
        runtime.transition(SessionPhase.COMPLETE, rationale="skip")
    runtime.transition(SessionPhase.ORIENT, rationale="ready")
    runtime.transition(SessionPhase.TEACH, rationale="teach")
    runtime.transition(SessionPhase.PRACTICE, rationale="practice")
    with pytest.raises(ValueError):
        runtime.transition(SessionPhase.VERIFY, rationale="verify", evidence=(EvidenceGate("attempt", "work", True, False),))
