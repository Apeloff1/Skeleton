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
    for bad in (" alice", "alice ", ""alice" + chr(10) + "other"", ""alice" + chr(0) + "shadow""):
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


def test_game_labels_reject_embedded_control_characters():
    from dataclasses import replace
    store = setup()
    for name in (""Example" + chr(0) + "Game"", ""Example" + chr(10) + "Game""):
        with pytest.raises(ValueError, match="game label"):
            store.record(replace(session(store), game_label=name), authorized=True)


def test_duration_bool_cannot_cross_recording_boundary():
    from dataclasses import replace
    store = setup()
    with pytest.raises(ValueError, match="duration"):
        store.record(replace(session(store), duration_ms=True), authorized=True)


def test_observation_collection_requires_typed_bounded_tuple():
    from dataclasses import replace
    store = setup()
    base = session(store)
    for bad in ([observation()], ("not-an-observation",), ()):
        with pytest.raises(ValueError, match="observation collection"):
            store.record(replace(base, observations=bad), authorized=True)


def test_recorded_observations_require_real_monotone_timestamps():
    from dataclasses import replace
    store = setup()
    base = session(store)
    for items, reason in (
        ((observation(timestamp=1000), observation(timestamp=999)), "recording order"),
        ((observation(timestamp=True),), "outside recording"),
    ):
        with pytest.raises(ValueError, match=reason):
            store.record(replace(base, observations=items), authorized=True)


def test_observation_confidence_rejects_boolean_nonfinite_and_string():
    store = setup()
    for bad in (True, float("nan"), float("inf"), "0.9", -0.1, 1.1):
        with pytest.raises(ValueError, match="confidence"):
            store.record(session(store, observations=(observation(confidence=bad),)), authorized=True)


def test_observation_confirmation_rejects_numeric_truthiness():
    from dataclasses import replace
    store = setup()
    item = observation(preference=PreferenceSignal.ENJOYED, confirmed=True)
    with pytest.raises(ValueError, match="confirmation must be boolean"):
        store.record(session(store, observations=(replace(item, user_confirmed=1),)), authorized=True)


def test_observation_note_refuses_control_and_surrogate_text():
    from dataclasses import replace
    store = setup()
    base = observation()
    for bad in ("embedded" + chr(0) + "nul", "two" + chr(10) + "lines", "bad" + chr(0xd800)):
        with pytest.raises(ValueError, match="observation note"):
            store.record(session(store, observations=(replace(base, description=bad),)), authorized=True)


def test_session_identity_rejects_invalid_digest_and_replay():
    from dataclasses import replace
    store = setup()
    base = session(store)
    for bad in ("A" * 64, "0" * 64, "not-a-digest"):
        with pytest.raises(ValueError, match="session identifier"):
            store.record(replace(base, session_id=bad), authorized=True)


def test_read_limit_requires_integer_not_boolean():
    store = setup()
    for value in (True, 1.5, -1, 1001):
        with pytest.raises(ValueError, match="history limit"):
            store.sessions("alice", authorized=True, limit=value)


def test_session_id_must_have_canonical_lowercase_content_digest():
    from dataclasses import replace
    store = setup()
    good = session(store)
    for forged in (good.session_id.upper(), good.session_id[:-1] + "Z", "0" * 64):
        if forged == good.session_id:
            continue
        with pytest.raises(ValueError, match="session identifier"):
            store.record(replace(good, session_id=forged), authorized=True)


def test_session_reads_require_explicit_boolean_true():
    store = setup()
    for authorization in (1, "yes", None):
        with pytest.raises(PermissionError, match="authorization"):
            store.sessions("alice", authorized=authorization)


def test_session_erasure_requires_explicit_boolean_true():
    store = setup()
    store.record(session(store), authorized=True)
    with pytest.raises(PermissionError, match="authorization"):
        store.erase("alice", authorized=1)
    assert len(store.sessions("alice", authorized=True)) == 1


def test_session_record_refuses_unbounded_serialized_payload(monkeypatch):
    import skeleton.ai.webcrawler.dragon_game_mechanics as module
    store = setup()
    monkeypatch.setattr(module, "MAX_STORED_SESSION_BYTES", 48)
    with pytest.raises(ValueError, match="byte budget"):
        store.record(session(store), authorized=True)
    assert store.sessions("alice", authorized=True) == ()


def test_session_byte_budget_accepts_regular_observations():
    store = setup()
    value = session(store)
    store.record(value, authorized=True)
    assert store.sessions("alice", authorized=True)[0].session_id == value.session_id


def test_corrupted_stored_payload_over_budget_fails_before_decode(monkeypatch):
    import skeleton.ai.webcrawler.dragon_game_mechanics as module
    store = setup()
    store.record(session(store), authorized=True)
    monkeypatch.setattr(module, "MAX_STORED_SESSION_BYTES", 4)
    with pytest.raises(ValueError, match="byte budget"):
        store.sessions("alice", authorized=True)


def test_history_reads_are_bounded_and_ordered_across_sessions():
    store = setup()
    for text in ("First", "Second", "Third"):
        record = store.build_session("alice", text, 20000, (observation(),),
                                     capture_consent=True, analysis_consent=True)
        store.record(record, authorized=True)
    result = store.sessions("alice", authorized=True, limit=2)
    assert len(result) == 2
    assert [s.session_id for s in result] == sorted(s.session_id for s in result)


def test_corrupt_stored_observation_json_fails_closed():
    store = setup()
    store.record(session(store), authorized=True)
    store.db.execute("UPDATE dragon_game_sessions SET observations_json=? WHERE owner=?",
                     ("{corrupted", "alice"))
    with pytest.raises(ValueError, match="JSON corrupt"):
        store.sessions("alice", authorized=True)


def test_stored_observation_shape_refuses_partial_records():
    store = setup()
    store.record(session(store), authorized=True)
    for body in ("{}", "[[1,2]]", "[]"):
        store.db.execute("UPDATE dragon_game_sessions SET observations_json=? WHERE owner=?",
                         (body, "alice"))
        with pytest.raises(ValueError, match="invalid shape"):
            store.sessions("alice", authorized=True)

