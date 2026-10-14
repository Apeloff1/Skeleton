"""Baby dragon companion runtime tests."""
import pytest
from skeleton.ai.webcrawler.dragon_companion_runtime import (
    DragonCompanionPolicy, DragonEvent, DragonPhase,
    animation_frame, new_companion, transition,
)


def advance_to_distilling():
    state = new_companion("alice")
    state = transition(state, DragonEvent.WAKE)
    state = transition(
        state, DragonEvent.START_RESEARCH,
        topic="neural graphics", consent=True,
    )
    state = transition(state, DragonEvent.DISCOVER)
    state = transition(state, DragonEvent.CAPTURE)
    return transition(state, DragonEvent.START_DISTILL)


def test_dragon_starts_snuggled_in_egg():
    state = new_companion("alice")
    frame = animation_frame(state)
    assert state.phase is DragonPhase.NESTING
    assert frame["egg"]["half_hatched"]
    assert frame["egg"]["hat"]


def test_distillation_activates_geek_glasses():
    state = advance_to_distilling()
    frame = animation_frame(state)
    assert frame["glasses"]["visible"]
    assert frame["glasses"]["white_tape"]
    assert not frame["fire"]["visible"]


def test_burning_is_distinct_from_distillation():
    state = new_companion("alice")
    state = transition(state, DragonEvent.WAKE)
    state = transition(
        state, DragonEvent.START_RESEARCH, topic="research", consent=True,
    )
    state = transition(state, DragonEvent.DISCOVER)
    state = transition(state, DragonEvent.CAPTURE)
    assert animation_frame(state)["fire"]["visible"]
    assert not animation_frame(state)["glasses"]["visible"]


def test_research_requires_consent():
    state = transition(new_companion("alice"), DragonEvent.WAKE)
    with pytest.raises(PermissionError):
        transition(
            state, DragonEvent.START_RESEARCH,
            topic="science", consent=False,
        )


def test_approval_is_not_automatic():
    state = advance_to_distilling()
    state = transition(state, DragonEvent.DISTILLED)
    state = transition(state, DragonEvent.VERIFIED)
    with pytest.raises(PermissionError):
        transition(state, DragonEvent.APPROVED)
    state = transition(
        state, DragonEvent.APPROVED, human_approved=True,
    )
    assert state.phase is DragonPhase.REMEMBERING
    state = transition(state, DragonEvent.STORED)
    assert state.phase is DragonPhase.LISTENING


def test_invalid_transition_fails_closed():
    with pytest.raises(ValueError):
        transition(new_companion("alice"), DragonEvent.STORED)


def test_progress_is_monotonic():
    state = transition(new_companion("alice"), DragonEvent.WAKE)
    state = transition(
        state, DragonEvent.START_RESEARCH,
        topic="physics", consent=True,
    )
    state = transition(state, DragonEvent.DISCOVER, progress=0.5)
    with pytest.raises(ValueError):
        transition(state, DragonEvent.CAPTURE, progress=0.2)


def test_error_state_can_reset():
    state = transition(new_companion("alice"), DragonEvent.FAIL,
                       error="temporary transport failure")
    assert state.phase is DragonPhase.ERROR
    assert state.last_error
    state = transition(state, DragonEvent.RESET)
    assert state.phase is DragonPhase.LISTENING
    assert not state.last_error


def test_state_fingerprints_are_deterministic():
    a = transition(new_companion("alice"), DragonEvent.WAKE)
    b = transition(new_companion("alice"), DragonEvent.WAKE)
    assert a == b


def test_event_budget():
    state = new_companion("alice")
    state = transition(
        state, DragonEvent.WAKE,
        policy=DragonCompanionPolicy(max_progress_events=1),
    )
    with pytest.raises(ValueError, match="budget"):
        transition(
            state, DragonEvent.TALK,
            policy=DragonCompanionPolicy(max_progress_events=1),
        )
