from skeleton.acquired.learning import (
    AdaptiveLearningEngine,
    DifficultyZone,
    LearningSignal,
    ProgressionTracker,
)
from skeleton.kernel.events import EventBus


def test_growth_zone_for_sustained_good_performance():
    engine = AdaptiveLearningEngine()
    result = engine.analyze(
        LearningSignal(
            current_mastery=0.72,
            recent_performance=(0.74, 0.78, 0.81, 0.76),
            time_on_task=600,
            errors_made=1,
            hints_used=0,
        )
    )

    assert result.zone is DifficultyZone.GROWTH
    assert result.recommendation == "maintain"
    assert 0.0 <= result.sweet_spot <= 1.0


def test_low_performance_with_struggle_reaches_panic_zone():
    engine = AdaptiveLearningEngine()
    result = engine.analyze(
        LearningSignal(
            current_mastery=0.65,
            recent_performance=(0.20, 0.25, 0.30),
            time_on_task=3600,
            errors_made=12,
            hints_used=8,
        )
    )

    assert result.zone is DifficultyZone.PANIC
    assert result.recommendation == "reduce_difficulty"
    assert result.sweet_spot < 0.65


def test_out_of_range_telemetry_is_bounded():
    engine = AdaptiveLearningEngine()
    result = engine.analyze(
        LearningSignal(
            current_mastery=5.0,
            recent_performance=(-10.0, 2.0),
            time_on_task=-100,
            errors_made=-4,
            hints_used=-2,
        )
    )

    assert 0.0 <= result.average_performance <= 1.0
    assert 0.0 <= result.struggle_score <= 1.0
    assert 0.0 <= result.optimal_min <= result.optimal_max <= 1.0


def test_scaffolding_follows_error_patterns_and_intensity():
    engine = AdaptiveLearningEngine()
    plan = engine.scaffolding(
        "recursion",
        performance=0.35,
        error_patterns=("conceptual", "procedural", "application"),
    )

    assert plan["scaffolding_intensity"] == "heavy"
    assert len(plan["scaffolds"]) == 4
    assert plan["scaffolds"][0]["type"] == "analogy"


def test_learning_engine_emits_events():
    bus = EventBus()
    observed = []
    bus.subscribe("acquired.learning.*", observed.append)
    engine = AdaptiveLearningEngine(bus=bus)

    engine.analyze(LearningSignal(recent_performance=(0.8, 0.82)))
    engine.scaffolding("testing", 0.7, ("procedural",))

    assert [event.topic for event in observed] == [
        "acquired.learning.zpd",
        "acquired.learning.scaffolding",
    ]


def test_progression_tracker_preserves_original_growth_curve_without_table_limit():
    assert ProgressionTracker.xp_threshold(0) == 0
    assert ProgressionTracker.xp_threshold(1) == 100
    assert ProgressionTracker.xp_threshold(2) == 150
    assert ProgressionTracker.xp_threshold(3) == 225
    assert ProgressionTracker.xp_threshold(120) > ProgressionTracker.xp_threshold(100)


def test_progression_summary_handles_empty_and_mastered_lessons():
    empty = ProgressionTracker.summarize(0)
    assert empty["current_level"] == 0
    assert empty["stats"]["mastery_rate"] == 0.0

    summary = ProgressionTracker.summarize(
        180,
        [
            {"mastery": 0.95, "time_spent": 600},
            {"mastery": 0.70, "time_spent": 300},
        ],
    )
    assert summary["current_level"] >= 1
    assert summary["stats"]["lessons_mastered"] == 1
    assert summary["stats"]["mastery_rate"] == 0.5
