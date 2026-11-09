from skeleton.school.curriculum import CurriculumGraph, CurriculumNode
from skeleton.school.energy import EnergyBudget
from skeleton.school.jeeves import JeevesControlPlane
from skeleton.school.learning_control import LearningState
from skeleton.school.memory import LearnerMemory, MemoryKind
from skeleton.school.student import StudentProfile


def test_jeeves_plan_composes_learning_policies():
    graph = CurriculumGraph()
    graph.add(CurriculumNode("python", "Python basics", tags=("python",), estimated_minutes=40))
    graph.add(CurriculumNode("algorithms", "Algorithms", prerequisites=("python",), estimated_minutes=50))

    student = StudentProfile(
        student_id="s1",
        goals=["python"],
        interests={"python"},
        energy=0.8,
    )
    memory = LearnerMemory(
        key="python-loop",
        content="Learner understands loops but confuses iteration and indexing.",
        kind=MemoryKind.MISCONCEPTION,
        skill_ids=("python",),
        importance=0.9,
        confidence=0.8,
    )
    plane = JeevesControlPlane(graph)
    plane.memory.remember(memory)

    plan = plane.plan(student, query_terms=("loops",), energy_budget=EnergyBudget(current=0.8))

    assert plan.primary_skill == "python"
    assert plan.memory_matches
    assert plan.learning_control.difficulty_adjustment in {"hold", "increase_challenge"}
    assert plan.energy.session_minutes == 40
    assert plan.decisions
    assert "response quality or solution score" in plan.next_evidence


def test_jeeves_reduces_complexity_when_cognitive_load_is_high():
    graph = CurriculumGraph()
    graph.add(CurriculumNode("python", "Python basics", estimated_minutes=45))
    student = StudentProfile(student_id="s1", energy=0.1)
    plane = JeevesControlPlane(graph)

    plan = plane.plan(
        student,
        learning_state=LearningState(
            mastery=0.8,
            acquisition_rate=0.8,
            retention_rate=0.8,
            transfer_rate=0.8,
            depth_score=0.8,
            cognitive_load=0.95,
        ),
        energy_budget=EnergyBudget(current=0.1),
    )

    assert plan.learning_control.difficulty_adjustment == "reduce_complexity"
    assert plan.suggested_minutes <= 20
