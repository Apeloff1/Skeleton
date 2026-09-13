from skeleton.frontier.gameforge_recovery import RecoveryState

def test_recovery_state_tracks_attempts_and_successes():
    state = RecoveryState()
    assert state.recovery_rate == 0.0
    state.record_attempt()
    state.record_recovery()
    state.record_attempt()
    assert state.attempts == 2
    assert state.recovered == 1
    assert state.recovery_rate == 0.5
