"""Original cinematic storyboards: typed proof, review, replay and custody."""
from __future__ import annotations

import json
import os

import pytest

from skeleton.jeeves.worlds.cinematics import (
    CinematicsStore, edit_cinematics, engine_handoff, propose_cinematics,
    prove_cinematics, render_cinematics_html, replay_cinematics,
    validate_cinematics,
)
from skeleton.jeeves.worlds.session import SessionStore
from skeleton.jeeves.worlds.world_canon import CanonError, WorldStore, digest, propose


def setup(tmp_path):
    worlds = WorldStore(tmp_path)
    world = propose(world_id="testworld", premise="A lantern keeper chooses a road",
                    protagonist="Mira", region="Mist Vale", goal="Return the lantern")
    worlds.publish(world, create=True)
    store = CinematicsStore(tmp_path)
    sequences = [
        {"scene": "opening", "beats": [
            {"id": "arrival", "cue": "arrival",
             "caption": "Mira steps into the blue dusk.", "duration_ms": 1500},
            {"id": "reaction", "cue": "reaction",
             "caption": "The lantern flickers.", "duration_ms": 900},
        ]},
        {"scene": "resolution", "beats": [
            {"id": "resolution", "cue": "departure",
             "caption": "The village glows once more.", "duration_ms": 1200},
        ]},
    ]
    source = propose_cinematics(world, prompt="Author an original lantern sequence",
                                sequences=sequences)
    return world, store, source


def assert_code(code, callback):
    with pytest.raises(CanonError) as exc:
        callback()
    assert exc.value.code == code


def test_propose_and_reachable_entry_witnesses(tmp_path):
    world, _, source = setup(tmp_path)
    proof = prove_cinematics(source, world)
    assert proof["entry_witnesses"] == {
        "opening": [], "resolution": ["pursue_goal"]}
    assert proof["duration_ms"] == {"opening": 2400, "resolution": 1200}
    assert replay_cinematics(source, world, ["pursue_goal"])["visits"][1]["scene"] == "resolution"
    assert_code("cinematics_review_required",
                lambda: render_cinematics_html(source, world))


def test_schema_and_budget_fail_closed(tmp_path):
    world, _, source = setup(tmp_path)
    for field, value, code in (
        ("duration_ms", True, "cinematics_invalid_duration"),
        ("duration_ms", 0, "cinematics_invalid_duration"),
        ("duration_ms", 15001, "cinematics_invalid_duration"),
        ("cue", "script", "cinematics_invalid_cue"),
        ("caption", "", "invalid_text"),
    ):
        broken = json.loads(json.dumps(source))
        broken["sequences"][0]["beats"][0][field] = value
        assert_code(code, lambda broken=broken: validate_cinematics(broken, world))
    duplicate = json.loads(json.dumps(source))
    duplicate["sequences"].append(duplicate["sequences"][0])
    assert_code("cinematics_duplicate_scene",
                lambda: validate_cinematics(duplicate, world))
    reversed_order = json.loads(json.dumps(source))
    reversed_order["sequences"].reverse()
    assert_code("cinematics_noncanonical_scene_order",
                lambda: validate_cinematics(reversed_order, world))


def test_review_persist_compile_verify_and_player(tmp_path):
    world, store, source = setup(tmp_path)
    first = store.publish(world["id"], source, create=True)
    assert first == digest(source)
    assert_code("cinematics_review_required",
                lambda: store.compile(world["id"], first))
    assert_code("cinematics_stale_edit",
                lambda: store.approve(world["id"], "0" * 64, "Author review"))
    approved = store.approve(world["id"], first, "I reviewed every original caption")
    receipt = store.compile(world["id"], approved)
    assert receipt == store.verify(world["id"])
    assert receipt["artifacts"]["testworld.cinematics.playable.html"]
    page = (tmp_path / "testworld.cinematics.playable.html").read_text()
    assert "script-src 'sha256-" in page
    assert "connect-src 'none'" in page
    assert "Mira steps into the blue dusk" in page
    assert "addEventListener" in page
    assert engine_handoff(store.inspect(world["id"])["cinematics"], world)["external_media"] is False
    SessionStore(tmp_path).create(world["id"], "player1")
    view = store.player(world["id"], "player1")
    assert view["player"]["visits"][0]["scene"] == "opening"
    assert view["revision"] == 0


def test_edit_requires_new_review_and_stale_custody(tmp_path):
    world, store, source = setup(tmp_path)
    first = store.publish(world["id"], source, create=True)
    approved = store.approve(world["id"], first, "Reviewed")
    original = store.inspect(world["id"])["cinematics"]
    changed = edit_cinematics(original, world, {
        "action": "replace_sequence", "value": {
            "scene": "resolution", "beats": [{
                "id": "ending", "cue": "departure",
                "caption": "A second original ending caption.", "duration_ms": 1100,
            }],
        },
    })
    assert changed["approved"] is False
    assert_code("cinematics_stale_edit",
                lambda: store.publish(world["id"], changed,
                                      expected_digest="f" * 64))
    new_digest = store.publish(world["id"], changed, expected_digest=approved)
    assert_code("cinematics_review_required",
                lambda: store.compile(world["id"], new_digest))
    assert_code("cinematics_stale_edit",
                lambda: store.compile(world["id"], approved))
    assert_code("cinematics_empty",
                lambda: edit_cinematics(changed, world, {"action": "batch", "value": [
                    {"action": "remove_sequence", "value": {"scene": "opening"}},
                    {"action": "remove_sequence", "value": {"scene": "resolution"}},
                ]}))


def test_tampered_outputs_and_symlink_rejected(tmp_path):
    world, store, source = setup(tmp_path)
    first = store.publish(world["id"], source, create=True)
    approved = store.approve(world["id"], first, "Reviewed")
    store.compile(world["id"], approved)
    page = tmp_path / "testworld.cinematics.playable.html"
    page.write_text("forged")
    assert_code("cinematics_artifact_mismatch",
                lambda: store.verify(world["id"]))
    store.compile(world["id"], approved)
    page.unlink()
    page.symlink_to(tmp_path / "testworld.cinematics.json")
    with pytest.raises((CanonError, OSError)):
        store.verify(world["id"])
    page.unlink()
    store.compile(world["id"], approved)
    (tmp_path / "testworld.cinematics.receipt.json").write_text("{}")
    assert_code("cinematics_receipt_mismatch",
                lambda: store.verify(world["id"]))


def test_untrusted_text_escaped_and_editor_source_lease(tmp_path):
    world, store, source = setup(tmp_path)
    source["sequences"][0]["beats"][0]["caption"] = "</script><script>alert(1)</script>"
    first = store.publish(world["id"], source, create=True)
    page = store.editor(world["id"], first)
    assert page["html_file"] == "testworld.cinematics.editor.html"
    html = (tmp_path / page["html_file"]).read_text()
    assert "</script><script>alert(1)</script>" not in html
    assert "\\u003c/script>" in html
    assert_code("cinematics_stale_edit",
                lambda: store.editor(world["id"], "f" * 64))
    approved = store.approve(world["id"], first, "Reviewed malicious-looking literal text")
    store.compile(world["id"], approved)
    playable = (tmp_path / "testworld.cinematics.playable.html").read_text()
    assert "</script><script>alert(1)</script>" not in playable
    assert "\\u003c/script>" in playable


def test_scene_local_beat_ids_remain_independent(tmp_path):
    world, store, source = setup(tmp_path)
    # Beat identity is local to its scene, not global across a story.
    source["sequences"][1]["beats"][0]["id"] = "arrival"
    assert validate_cinematics(source, world) == source
    from skeleton.jeeves.worlds.cinematics_editor import _EDITOR_JS
    assert "inputs[cursor++]" in _EDITOR_JS
    assert "byId.get(beat.id)" not in _EDITOR_JS
    first = store.publish(world["id"], source, create=True)
    assert store.editor(world["id"], first)["html_sha256"]
