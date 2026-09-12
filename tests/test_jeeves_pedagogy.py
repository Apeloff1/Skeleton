from skeleton.intelligence.jeeves_pedagogy import (
    AssessmentKind,
    ScaffoldLevel,
    assessment_strategy,
    build_session,
    interleave_topics,
    next_scaffold,
    retrieval_schedule,
    choose_session_structure,
)


def test_retrieval_schedule_is_spaced_and_bounded():
    reviews = retrieval_schedule(7)
    assert [review.interval_days for review in reviews] == [0, 1, 3, 7]


def test_assessment_strategies_cover_three_modes():
    assert "quick_concept_check" in assessment_strategy(AssessmentKind.FORMATIVE)
    assert "error_analysis" in assessment_strategy(AssessmentKind.DIAGNOSTIC)
    assert "teach_back" in assessment_strategy(AssessmentKind.SUMMATIVE)


def test_scaffolding_fades_only_after_mastery():
    assert next_scaffold(ScaffoldLevel.HEAVY, demonstrated_mastery=True) == ScaffoldLevel.MODERATE
    assert next_scaffold(ScaffoldLevel.MODERATE, demonstrated_mastery=False) == ScaffoldLevel.HEAVY
    assert next_scaffold(ScaffoldLevel.MINIMAL, demonstrated_mastery=True) == ScaffoldLevel.MINIMAL


def test_session_adapts_to_time_and_energy():
    session = build_session(
        stage="growth",
        topic="recursion",
        minutes=60,
        energy_level="low",
        difficulty=0.7,
    )
    assert session.structure == "review_guided_practice_break"
    assert session.scaffold == ScaffoldLevel.LIGHT
    assert session.difficulty_delta == -0.15
    assert session.include_break is True


def test_short_session_uses_quick_review():
    assert choose_session_structure(15) == "quick_review"


def test_interleaving_deduplicates_without_reordering():
    assert interleave_topics(["loops", "arrays", "loops", " ", "arrays"]) == ("loops", "arrays")
