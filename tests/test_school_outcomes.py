from skeleton.school.memory import MemoryStore, MemoryKind
from skeleton.school.outcomes import OutcomeKind, SessionOutcome, apply_outcome
from skeleton.school.reflection import ReflectionJournal
from skeleton.school.student import StudentProfile


def test_outcome_updates_learner_memory_reflection_and_signals():
    student = StudentProfile(student_id="s1")
    memory = MemoryStore()
    reflections = ReflectionJournal()

    result = apply_outcome(
        student,
        SessionOutcome(
            skill_id="python",
            score=0.95,
            confidence=0.9,
            minutes=30,
            step=1,
            kind=OutcomeKind.INDEPENDENT,
            summary="Learner implemented the parser independently.",
            learner_explanation="I split the input into tokens before parsing.",
            lesson_learned="Decomposition made the implementation manageable.",
        ),
        memory=memory,
        reflections=reflections,
    )

    assert student.skill("python").attempts == 1
    assert student.skill("python").mastery > 0
    assert memory.retrieve(skill_ids=("python",), kinds=(MemoryKind.PROCEDURAL,))
    assert reflections.recent(1)[0].skills == ("python",)
    assert "evidence_recorded" in result.signals
    assert "memory_updated" in result.signals
    assert "reflection_recorded" in result.signals
    assert "consider_challenge_or_transfer" in result.signals


def test_misconception_creates_explicit_follow_up_memory():
    student = StudentProfile(student_id="s1")
    memory = MemoryStore()
    reflections = ReflectionJournal()

    result = apply_outcome(
        student,
        SessionOutcome(
            skill_id="loops",
            score=0.35,
            kind=OutcomeKind.MISCONCEPTION,
            summary="Learner treated range stop as inclusive.",
            misconception="Learner believes range(5) includes 5.",
        ),
        memory=memory,
        reflections=reflections,
    )

    matches = memory.retrieve(skill_ids=("loops",), kinds=(MemoryKind.MISCONCEPTION,))
    assert matches
    assert "misconception_requires_follow_up" in result.signals
    assert "consider_scaffolding_or_reteach" in result.signals
