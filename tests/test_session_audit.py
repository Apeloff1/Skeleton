from skeleton.school.ai_pipeline import PipelineKind
from skeleton.school.curriculum import CurriculumGraph
from skeleton.school.jeeves import JeevesControlPlane
from skeleton.school.knowledge import KnowledgeGraph
from skeleton.school.session_audit import audit_session, policy_chain
from skeleton.school.session_runtime import JeevesSessionRuntime
from skeleton.school.student import StudentProfile


def test_session_audit_covers_runtime_chain() -> None:
    curriculum = CurriculumGraph()
    runtime = JeevesSessionRuntime(JeevesControlPlane(curriculum), curriculum, KnowledgeGraph())
    runtime.begin(
        StudentProfile(student_id="audit"),
        session_id="audit",
        query_terms=("algorithms",),
        pipeline_kind=PipelineKind.LESSON,
    )

    audit = audit_session(runtime.ledger, "audit")

    assert audit.valid
    assert "hash-chain" in audit.checks
    assert "causal-root" in audit.checks
    assert "counterfactual-audit" in audit.checks
    assert audit.digest
    assert policy_chain(runtime.ledger.records)
