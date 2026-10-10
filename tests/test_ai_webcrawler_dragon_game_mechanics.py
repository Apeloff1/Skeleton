"""Game observation distillation and privacy regression tests."""
import sqlite3
import pytest

from skeleton.ai.webcrawler.dragon_game_mechanics import (
    GameMechanicsMemory, GameObservation, Mechanic, PreferenceSignal,
)


def setup():
    return GameMechanicsMemory(sqlite3.connect(":memory:"))


def observation(mechanic=Mechanic.COMBAT, preference=PreferenceSignal.UNKNOWN,
                confirmed=False, confidence=0.9, timestamp=1000):
    return GameObservation(
        timestamp, mechanic, "Timing-based interaction",
        confidence, preference, confirmed,
    )


def session(store, owner="alice", observations=None, **kwargs):
    return store.build_session(
        owner, "Example Game", 20000,
        observations or (observation(),),
        capture_consent=kwargs.get("capture_consent", True),
        analysis_consent=kwargs.get("analysis_consent", True),
    )


def test_unknown_preference_does_not_become_user_taste():
    store = setup()
    store.record(session(store), authorized=True)
    profile = store.distill("alice", authorized=True)
    assert len(profile.insights) == 1
    assert profile.insights[0].preference_score == 0
    assert profile.review_required
    assert profile.design_directives == ()


def test_confirmed_enjoyment_guides_game_creation():
    store = setup()
    item = observation(preference=PreferenceSignal.ENJOYED, confirmed=True)
    store.record(session(store, observations=(item,)), authorized=True)
    profile = store.distill("alice", authorized=True)
    assert profile.insights[0].preference_score == 1
    assert "combat" in profile.design_directives[0]


def test_confirmed_dislike_guides_alternative_design():
    store = setup()
    item = observation(
        mechanic=Mechanic.PUZZLE,
        preference=PreferenceSignal.DISLIKED,
        confirmed=True,
    )
    store.record(session(store, observations=(item,)), authorized=True)
    profile = store.distill("alice", authorized=True)
    assert profile.insights[0].preference_score == -1
    assert "alternatives" in profile.design_directives[0]


def test_unconfirmed_preference_is_rejected():
    store = setup()
    item = observation(preference=PreferenceSignal.ENJOYED)
    with pytest.raises(PermissionError, match="confirmation"):
        store.record(session(store, observations=(item,)), authorized=True)


def test_capture_and_analysis_require_separate_consent():
    store = setup()
    with pytest.raises(PermissionError):
        store.record(session(store, capture_consent=False), authorized=True)
    with pytest.raises(PermissionError):
        store.record(session(store, analysis_consent=False), authorized=True)
    with pytest.raises(PermissionError):
        store.record(session(store), authorized=False)


def test_timestamp_outside_capture_rejected():
    store = setup()
    item = observation(timestamp=20001)
    with pytest.raises(ValueError, match="outside"):
        store.record(session(store, observations=(item,)), authorized=True)


def test_owner_isolation_and_erasure():
    store = setup()
    store.record(session(store, owner="alice"), authorized=True)
    store.record(session(store, owner="bob"), authorized=True)
    assert store.erase("alice", authorized=True) == 1
    assert store.sessions("alice", authorized=True) == ()
    assert len(store.sessions("bob", authorized=True)) == 1


def test_duplicate_session_is_idempotent():
    store = setup()
    data = session(store)
    assert store.record(data, authorized=True) == data.session_id
    assert store.record(data, authorized=True) == data.session_id
    assert len(store.sessions("alice", authorized=True)) == 1


def test_raw_video_cannot_be_retained_in_observation_store():
    from dataclasses import replace
    store = setup()
    with pytest.raises(ValueError, match="raw"):
        store.record(
            replace(session(store), raw_video_retained=True),
            authorized=True,
        )


def test_low_confidence_mechanic_excluded():
    store = setup()
    item = observation(confidence=0.1)
    store.record(session(store, observations=(item,)), authorized=True)
    assert store.distill("alice", authorized=True).insights == ()


def test_distillation_is_deterministic():
    store = setup()
    store.record(session(store), authorized=True)
    assert store.distill("alice", authorized=True) == store.distill(
        "alice", authorized=True,
    )

def test_policy_rejects_type_confusion():
    from skeleton.ai.webcrawler.dragon_game_mechanics import CapturePolicy
    with pytest.raises(ValueError, match="duration"):
        GameMechanicsMemory(sqlite3.connect(":memory:"), policy=CapturePolicy(max_session_seconds=True))
    with pytest.raises(ValueError, match="CapturePolicy"):
        GameMechanicsMemory(sqlite3.connect(":memory:"), policy=None)


def test_policy_strict_observation_resource_budget():
    from skeleton.ai.webcrawler.dragon_game_mechanics import CapturePolicy
    for attr in ("max_observations", "max_note_chars", "max_sessions_per_owner"):
        options = {attr: True}
        with pytest.raises(ValueError):
            GameMechanicsMemory(sqlite3.connect(":memory:"), policy=CapturePolicy(**options))


def test_policy_note_budget_zero_is_rejected():
    from skeleton.ai.webcrawler.dragon_game_mechanics import CapturePolicy
    with pytest.raises(ValueError, match="note budget"):
        GameMechanicsMemory(sqlite3.connect(":memory:"), policy=CapturePolicy(max_note_chars=0))


def test_policy_session_capacity_bool_not_admitted():
    from skeleton.ai.webcrawler.dragon_game_mechanics import CapturePolicy
    with pytest.raises(ValueError, match="session capacity"):
        GameMechanicsMemory(sqlite3.connect(":memory:"), policy=CapturePolicy(max_sessions_per_owner=False))


def test_policy_confidence_rejects_boolean_and_nonfinite():
    from skeleton.ai.webcrawler.dragon_game_mechanics import CapturePolicy
    for bad in (True, float("nan"), float("inf"), -1):
        with pytest.raises(ValueError, match="confidence"):
            GameMechanicsMemory(sqlite3.connect(":memory:"), policy=CapturePolicy(min_confidence=bad))


def test_owner_identity_rejects_control_and_whitespace():
    store = setup()
    for bad in (" alice", "alice ", "alice\\nother", "alice\\x00shadow"):
        with pytest.raises(ValueError, match="owner"):
            store.sessions(bad, authorized=True)


def test_strict_explicit_capture_and_analysis_consent():
    from dataclasses import replace
    store = setup()
    base = session(store)
    for field in ("capture_consent", "analysis_consent"):
        with pytest.raises(PermissionError, match="consent"):
            store.record(replace(base, **{field: 1}), authorized=True)
    with pytest.raises(PermissionError, match="consent"):
        store.record(base, authorized=1)


def test_raw_video_retention_flag_requires_explicit_false():
    from dataclasses import replace
    store = setup()
    with pytest.raises(ValueError, match="raw"):
        store.record(replace(session(store), raw_video_retained=0), authorized=True)

