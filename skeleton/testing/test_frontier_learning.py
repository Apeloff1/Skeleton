from skeleton.frontier.learning import LearningState, Mastery, assess


def test_learning_state_records_progress_deterministically():
    state = LearningState("learner-1", "python")
    state = state.record(True).record(True).record(True)
    assert state.attempts == 3
    assert state.successes == 3
    assert state.success_rate == 1.0
    assert state.mastery is Mastery.DEVELOPING


def test_learning_state_does_not_exceed_mastery_cap():
    state = LearningState("learner-1", "python", mastery=Mastery.MASTERED)
    for _ in range(10):
        state = state.record(True)
    assert state.mastery is Mastery.MASTERED


def test_assess_rejects_invalid_counts():
    try:
        assess(LearningState("learner-1", "python"), successes=4, attempts=3)
    except ValueError:
        pass
    else:
        raise AssertionError("invalid assessment should fail")
