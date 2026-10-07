from skeleton.school.assessment import AssessmentEngine, AssessmentEvidence, AssessmentKind
from skeleton.school.code_lab import CodeLabEngine, CodeTask, FindingSeverity
from skeleton.school.curriculum import CurriculumGraph, CurriculumNode, rank_recommendations
from skeleton.school.engine import SchoolEngine
from skeleton.school.student import StudentProfile


def test_curriculum_recommendations_respect_prerequisites_and_goals():
    graph = CurriculumGraph()
    graph.add(CurriculumNode("python", "Python", tags=("coding",)))
    graph.add(CurriculumNode("algorithms", "Algorithms", prerequisites=("python",), tags=("coding",)))
    graph.add(CurriculumNode("systems", "Systems", prerequisites=("algorithms",), tags=("systems",)))
    graph.validate()

    recs = rank_recommendations(graph, {"python": 0.9}, goals=("algorithms",), interests=("coding",))
    assert [item.skill_id for item in recs] == ["algorithms"]
    assert recs[0].priority > 0.5


def test_mastery_uses_recent_evidence_without_instant_mastery():
    student = StudentProfile("s1")
    state = student.record_evidence("python", 1.0, confidence=0.9, minutes=30, evidence="quiz-1")
    assert 0.5 <= state.mastery < 1.0
    state = student.record_evidence("python", 1.0, confidence=0.9, minutes=30, evidence="quiz-2")
    assert state.mastery > 0.7
    assert student.total_hours == 1.0


def test_assessment_recommends_targeted_remediation_for_misconception():
    engine = AssessmentEngine()
    engine.record(AssessmentEvidence("loops", AssessmentKind.FORMATIVE, 0.4, misconception="off-by-one"))
    intervention = engine.intervention_for("loops")
    assert intervention is not None
    assert intervention.kind == "targeted_remediation"
    assert intervention.intensity == 3


def test_code_lab_surfaces_security_and_test_signals():
    task = CodeTask("t1", "python", "Write a safe helper", expected_concepts=("function",))
    review = CodeLabEngine().review(task, "def run(x):\n    return eval(x)\n")
    assert any(item.severity == FindingSeverity.HIGH for item in review.findings)
    assert review.tests_suggested


def test_school_engine_shortens_low_energy_sessions():
    graph = CurriculumGraph()
    graph.add(CurriculumNode("python", "Python"))
    engine = SchoolEngine(graph)
    student = StudentProfile("s1", energy=0.2, goals=["python"])
    plan = engine.plan(student)
    assert plan.suggested_minutes == 20
    assert plan.recommendations[0].skill_id == "python"
