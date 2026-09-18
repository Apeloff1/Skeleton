import pytest

from skeleton.learning import (
    AssessmentEngine,
    BloomLevel,
    Curriculum,
    CurriculumError,
    LearningService,
    Lesson,
)


def _engine() -> AssessmentEngine:
    return AssessmentEngine(
        learning_rate=1.0,
        decay_rate=0.0,
        clock=lambda: 0.0,
    )


def test_curriculum_maps_prerequisite_lesson_to_its_skill():
    engine = _engine()
    curriculum = Curriculum()
    curriculum.add(Lesson("lesson-basics", "Basics", "skill-python"))
    curriculum.add(
        Lesson(
            "lesson-functions",
            "Functions",
            "skill-functions",
            prerequisites=("lesson-basics",),
            mastery_gate=0.6,
        )
    )

    assert [lesson.lesson_id for lesson in curriculum.ready(engine)] == [
        "lesson-basics"
    ]

    service = LearningService(assessment=engine, curriculum=curriculum)
    service.record(
        "skill-python",
        correct=True,
        bloom_level=BloomLevel.APPLY,
    )

    assert engine.mastery("lesson-basics") is None
    assert engine.mastery("skill-python") == 1.0
    assert [lesson.lesson_id for lesson in curriculum.ready(engine)] == [
        "lesson-basics",
        "lesson-functions",
    ]


def test_prerequisite_stays_blocked_below_dependent_lesson_gate():
    engine = AssessmentEngine(
        learning_rate=0.5,
        decay_rate=0.0,
        clock=lambda: 0.0,
    )
    curriculum = Curriculum()
    curriculum.add(Lesson("foundation", "Foundation", "skill-foundation"))
    curriculum.add(
        Lesson(
            "advanced",
            "Advanced",
            "skill-advanced",
            prerequisites=("foundation",),
            mastery_gate=0.7,
        )
    )

    service = LearningService(assessment=engine, curriculum=curriculum)
    service.record(
        "skill-foundation",
        correct=True,
        bloom_level=BloomLevel.UNDERSTAND,
    )

    assert engine.mastery("skill-foundation") == 0.5
    assert [lesson.lesson_id for lesson in service.ready_lessons()] == [
        "foundation"
    ]


def test_learning_service_exposes_provider_neutral_state_snapshot():
    service = LearningService(assessment=_engine())
    service.add_lesson(Lesson("intro", "Intro", "skill-intro"))
    service.add_lesson(
        Lesson(
            "build",
            "Build",
            "skill-build",
            prerequisites=("intro",),
        )
    )

    before = service.snapshot()
    assert before.ready_lesson_ids == ("intro",)
    assert before.weakest_skill_ids == ()
    assert service.next_lesson().lesson_id == "intro"

    observed = service.record(
        "skill-intro",
        correct=True,
        bloom_level=BloomLevel.CREATE,
        latency_s=2.0,
        hints_used=0,
    )

    assert observed.skill_id == "skill-intro"
    assert service.mastery("skill-intro") == 1.0
    assert service.snapshot().ready_lesson_ids == ("intro", "build")
    assert service.snapshot().weakest_skill_ids == ("skill-intro",)


def test_mastery_lookup_is_read_only_for_unknown_skills():
    engine = _engine()

    assert engine.mastery("not-seen") is None
    assert engine.weakest() == ()


def test_curriculum_still_rejects_unknown_prerequisite_lessons():
    curriculum = Curriculum()

    with pytest.raises(CurriculumError):
        curriculum.add(
            Lesson(
                "advanced",
                "Advanced",
                "skill-advanced",
                prerequisites=("missing-lesson",),
            )
        )
