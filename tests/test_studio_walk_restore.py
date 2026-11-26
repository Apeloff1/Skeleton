"""Untrusted saved walk sessions are source-verified before resume."""
import json
from dataclasses import replace
import pytest
from skeleton.ai.game_builder import studio_ecosystem_walk_replay as replay
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError

WORLD = {
    "project_id": "original-world", "source_digest": "f" * 64,
    "width": 4, "height": 4, "spawn": [1, 1], "target": [2, 1],
    "maps": [["####", "#..#", "#..#", "####"]],
    "stages": [{"id": "scene-one", "alternatives": ["inspect"],
                "prerequisites": []}],
}

@pytest.fixture
def documents(monkeypatch):
    monkeypatch.setattr(replay, "playable_world_source", lambda _: WORLD)
    return {}


def _bytes(receipt):
    return json.dumps(receipt, separators=(",", ":")).encode("utf-8")


def test_authorized_restore_resumes_real_play_and_preserves_digest(documents):
    before = replay.walk_action(replay.start_walk(documents, authorized=True),
                                documents, action="move", value="right", authorized=True)
    saved = replay.export_walk_receipt(before, documents, authorized=True)
    restored = replay.restore_walk_receipt(documents, saved, authorized=True)
    assert restored == before
    after = replay.walk_action(restored, documents, action="choose",
                               value="inspect", authorized=True)
    assert after.scene_index == 1
    assert after.chosen == (("scene-one", "inspect"),)
    assert replay.restore_walk_receipt(documents, _bytes(after.receipt()),
                                       authorized=True) == after


def test_rejects_tampering_without_accepting_client_claims(documents):
    before = replay.start_walk(documents, authorized=True)
    for key, value in [
        ("scene_index", True), ("accepted_moves", True),
        ("position", [2, 1]), ("source_digest", "e" * 64),
        ("session_digest", "0" * 64), ("release_certified", True),
        ("choices", [["scene-one", "inspect"]]),
    ]:
        payload = before.receipt()
        payload[key] = value
        with pytest.raises(StudioQuestError):
            replay.restore_walk_receipt(documents, _bytes(payload), authorized=True)


def test_duplicate_fields_extra_fields_and_nonfinite_rejected(documents):
    payload = replay.start_walk(documents, authorized=True).receipt()
    for raw in [
        _bytes(payload)[:-1] + b',"scene_index":0}',
        _bytes(dict(payload, unauthorized=True)),
        _bytes(payload)[:-1] + b',"other":NaN}',
        b'{"schema":',
        b'\xff',
    ]:
        with pytest.raises(StudioQuestError):
            replay.restore_walk_receipt(documents, raw, authorized=True)


def test_bounds_before_world_construction(monkeypatch):
    monkeypatch.setattr(replay, "playable_world_source", lambda _:
                        pytest.fail("untrusted oversized restore reached world generation"))
    with pytest.raises(StudioQuestError, match="oversized"):
        replay.restore_walk_receipt({}, b"x" * (replay.MAX_WALK_RECEIPT_BYTES + 1),
                                    authorized=True)
    receipt = {"schema": "skeleton.game_builder.studio_walk_replay.v1",
               "project_id": "p", "source_digest": "f" * 64,
               "events": [["move", "right"]] * (replay.MAX_WALK_EVENTS + 1),
               "scene_index": 0, "position": [1, 1], "choices": [],
               "accepted_moves": 0, "session_digest": "0" * 64,
               "external_evidence_verified": False,
               "native_genre_runtime_verified": False,
               "release_certified": False}
    with pytest.raises(StudioQuestError, match="event budget"):
        replay.restore_walk_receipt({}, _bytes(receipt), authorized=True)


def test_denied_authorization_precedes_deserialization(documents):
    with pytest.raises(PermissionError):
        replay.restore_walk_receipt(documents, b"not JSON", authorized=False)


def test_receipt_from_different_canonical_source_rejected(monkeypatch, documents):
    original = replay.start_walk(documents, authorized=True).receipt()
    changed = dict(WORLD, source_digest="e" * 64)
    monkeypatch.setattr(replay, "playable_world_source", lambda _: changed)
    with pytest.raises(StudioQuestError, match="authoritative source"):
        replay.restore_walk_receipt(documents, _bytes(original), authorized=True)


def test_export_denies_forged_state_and_requires_authorization(documents):
    session = replay.start_walk(documents, authorized=True)
    with pytest.raises(PermissionError):
        replay.export_walk_receipt(session, documents, authorized=False)
    with pytest.raises(StudioQuestError, match="does not match"):
        replay.export_walk_receipt(replace(session, accepted_moves=3),
                                   documents, authorized=True)
