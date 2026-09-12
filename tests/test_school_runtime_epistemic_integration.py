from skeleton.school.ai_pipeline import PipelineKind
from skeleton.school.curriculum import CurriculumGraph
from skeleton.school.epistemics import EvidencePolarity
from skeleton.school.jeeves import JeevesControlPlane
from skeleton.school.knowledge import KnowledgeGraph
from skeleton.school.session_runtime import JeevesSessionRuntime, SessionPhase


def test_runtime_records_epistemic_evidence_and_ledger() -> None:
    runtime = JeevesSessionRuntime(JeevesControlPlane(), CurriculumGraph(), KnowledgeGraph())
    runtime.begin(object(), session_id="s1", query_terms=("algorithms",), pipeline_kind=PipelineKind.LESSON)  # type: ignore[arg-type]
    runtime.record_evidence(event="answer", subject="algorithms", claim="a loop always terminates", score=0.9, polarity=EvidencePolarity.SUPPORTS)
    assert runtime.epistemics.evidence
    assert runtime.ledger.records
    runtime.ledger.verify()


def test_objective_gate_accepts_query_only_session() -> None:
    runtime = JeevesSessionRuntime(JeevesControlPlane(), CurriculumGraph(), KnowledgeGraph())
    plan = runtime.begin(object(), session_id="s2", query_terms=("graphs",))  # type: ignore[arg-type]
    objective = next(g for g in plan.gates if g.gate_id == "objective")
    assert objective.satisfied
