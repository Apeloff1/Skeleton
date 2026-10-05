from skeleton.school.curriculum import CurriculumGraph, CurriculumNode
from skeleton.school.engine import SchoolEngine
from skeleton.school.learning_control import LearningState
from skeleton.school.memory import LearnerMemory, MemoryKind, MemoryStore
from skeleton.school.session import JeevesSessionEngine
from skeleton.school.student import StudentProfile


def test_jeeves_session_composes_curriculum_control_and_memory():
    graph = CurriculumGraph()
    graph.add(CurriculumNode("python", "Python", tags=("coding",)))
    graph.add(CurriculumNode("testing", "Testing", prerequisites=("python",), tags=("coding",)))
    student = StudentProfile(student_id="s1", goals=["python"], interests={"coding"})
    memory = MemoryStore()
    memory.remember(LearnerMemory(
        key="m1", content="Learner confused assertions with print debugging", kind=MemoryKind.MISCONCEPTION,
        skill_ids=("python",), importance=0.9, confidence=0.9,
    ))

    plan = JeevesSessionEngine(SchoolEngine(graph), memory).plan(student, query_terms=("assertions",))

    assert plan.focus_skill == "python"
    assert plan.session_mode == "application"
    assert plan.memories[0].memory.key == "m1"
    assert any(decision.action == "retrieve_memory" for decision in plan.decisions)


def test_jeeves_session_surfaces_retention_and_low_energy_controls():
    graph = CurriculumGraph()
    graph.add(CurriculumNode("python", "Python"))
    student = StudentProfile(student_id="s1", energy=0.15)
    plan = JeevesSessionEngine(SchoolEngine(graph)).plan(
        student,
        learning_state=LearningState(retention_rate=0.4, time_since_review_hours=48, cognitive_load=0.9),
    )

    assert plan.session_mode == "recovery"
    assert plan.learning_control.practice_schedule == "increase_spaced_repetition"
    assert plan.learning_control.retention_strategy == "scheduled_review_needed"
    assert any(decision.action == "review" for decision in plan.decisions)
