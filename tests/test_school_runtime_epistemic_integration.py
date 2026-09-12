from skeleton.school.ai_pipeline import PipelineKind
from skeleton.school.curriculum import CurriculumGraph
from skeleton.school.epistemics import EvidencePolarity
from skeleton.school.jeeves import JeevesControlPlane
from skeleton.school.knowledge import KnowledgeGraph
from skeleton.school.session_runtime import JeevesSessionRuntime
from skeleton.school.student import StudentProfile


def learner() -> StudentProfile:
    return StudentProfile(student_id="test")


def runtime() -> JeevesSessionRuntime:
    curriculum = CurriculumGraph()
    return JeevesSessionRuntime(JeevesControlPlane(curriculum), curriculum, KnowledgeGraph())


def test_runtime_records_epistemic_evidence_and_ledger() -> None:
    engine = runtime()
    engine.begin(learner(), session_id="s1", query_terms=("algorithms",), pipeline_kind=PipelineKind.LESSON)
    engine.record_evidence(event="answer", subject="algorithms", claim="a loop always terminates", score=0.9, polarity=EvidencePolarity.SUPPORTS)
    assert engine.epistemics.evidence
    assert engine.ledger.records
    engine.ledger.verify()


def test_objective_gate_accepts_query_only_session() -> None:
    engine = runtime()
    plan = engine.begin(learner(), session_id="s2", query_terms=("graphs",))
    objective = next(g for g in plan.gates if g.gate_id == "objective")
    assert objective.satisfied
