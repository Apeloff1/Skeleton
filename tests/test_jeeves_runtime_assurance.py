from skeleton.jeeves.runtime.state import RuntimeState, RuntimePhase, RuntimeTransition, validate_runtime, transition_runtime

def test_runtime_transition_is_bounded():
    s=RuntimeState("job")
    t=RuntimeTransition(RuntimePhase.IDLE,RuntimePhase.PREPARE,"validated")
    assert transition_runtime(s,t).phase is RuntimePhase.PREPARE

def test_runtime_duplicate_states_rejected():
    s=RuntimeState("job")
    try: validate_runtime((s,s))
    except ValueError as e: assert "duplicate" in str(e)
    else: raise AssertionError("duplicate accepted")
