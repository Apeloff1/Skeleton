from skeleton.school.learning_control import LearningControl, LearningState


def test_learning_control_reduces_complexity_when_load_is_high():
    decision = LearningControl().decide(LearningState(mastery=0.6, cognitive_load=0.9))
    assert decision.difficulty_adjustment == "reduce_complexity"
    assert "cognitive load is high" in decision.rationale


def test_learning_control_adds_contexts_when_transfer_is_weak():
    decision = LearningControl().decide(LearningState(transfer_rate=0.4))
    assert decision.content_strategy == "varied_contexts"


def test_learning_control_schedules_review_after_a_day():
    decision = LearningControl().decide(LearningState(time_since_review_hours=25, retention_rate=0.6))
    assert decision.practice_schedule == "increase_spaced_repetition"
    assert decision.retention_strategy == "scheduled_review_needed"


def test_learning_control_simplifies_when_response_time_doubles():
    decision = LearningControl().decide(LearningState(response_time_ratio=2.1))
    assert decision.content_strategy == "simplify_presentation"
