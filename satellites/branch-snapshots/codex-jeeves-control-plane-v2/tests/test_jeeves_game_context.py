from skeleton.intelligence.game_context import (
    FactionContext,
    NoveltyDecision,
    novelty_gate,
    reputation_level,
)
from skeleton.intelligence.jeeves_policy import (
    InteractionMode,
    LearningStage,
    choose_difficulty,
    interaction_mode,
    stage_for_hours,
)


def test_jeeves_learning_stages_and_zpd_bounds():
    assert stage_for_hours(0) is LearningStage.ONBOARDING
    assert stage_for_hours(10) is LearningStage.FOUNDATION
    assert stage_for_hours(100) is LearningStage.GROWTH
    assert stage_for_hours(500) is LearningStage.MASTERY
    assert choose_difficulty(LearningStage.ONBOARDING, [1.0]) <= 0.30
    assert choose_difficulty(LearningStage.GROWTH, [0.95], "frustrated") < 0.80


def test_learner_choice_wins_and_emotional_state_changes_mode():
    assert interaction_mode(performance=0.2, emotional_state="neutral") is InteractionMode.TEACH
    assert interaction_mode(performance=0.95, emotional_state="neutral") is InteractionMode.CHALLENGE
    assert interaction_mode(performance=0.95, emotional_state="frustrated") is InteractionMode.REVIEW
    assert interaction_mode(performance=0.2, emotional_state="neutral", learner_requested="explore") is InteractionMode.EXPLORE


def test_reputation_context_and_relationships():
    assert reputation_level(-600).value == "hated"
    assert reputation_level(10000).value == "revered"
    ctx = FactionContext("merchants", reputation=3500, allies=("craftsmen",), enemies=("pirates",))
    assert ctx.level.value == "honored"
    assert ctx.relationship_signal("craftsmen") == "ally"
    assert ctx.relationship_signal("pirates") == "enemy"


def test_novelty_gate_requires_quorum():
    assert novelty_gate(quorum=3, confirmations=1) is NoveltyDecision.QUARANTINE
    assert novelty_gate(quorum=3, confirmations=3) is NoveltyDecision.ACCEPT
    assert novelty_gate(quorum=3, confirmations=1, trusted=True) is NoveltyDecision.ACCEPT
