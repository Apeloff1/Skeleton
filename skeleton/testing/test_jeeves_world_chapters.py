"""Chapter/act source completeness, branch witnesses and playable custody."""
from __future__ import annotations

import json

import pytest

from skeleton.jeeves.worlds.chapters import (
    ChapterStore, edit_chapters, engine_handoff, propose_chapters,
    prove_chapters, render_chapters_html, replay_chapters, validate_chapters,
)
from skeleton.jeeves.worlds.session import SessionStore
from skeleton.jeeves.worlds.world_canon import CanonError, WorldStore, digest, propose


def setup(tmp_path):
    world = propose(world_id="chapbook", premise="An archivist follows the light",
                    protagonist="Sora", region="Old Bridge", goal="Reach the library")
    WorldStore(tmp_path).publish(world, create=True)
    chapters = [
        {"id": "departure", "title": "The crossing", "summary": "The first decision",
         "acts": [{"id": "bridge", "title": "At the bridge",
                   "summary": "An opening scene", "scenes": ["opening"]}]},
        {"id": "homecoming", "title": "The return", "summary": "A conclusion",
         "acts": [{"id": "library", "title": "At the library",
                   "summary": "A final scene", "scenes": ["resolution"]}]},
    ]
    source = propose_chapters(world, prompt="Organize this original narrative", chapters=chapters)
    return world, ChapterStore(tmp_path), source


def assert_code(code, fn):
    with pytest.raises(CanonError) as exc:
        fn()
    assert exc.value.code == code


def test_complete_structure_and_branch_witnesses(tmp_path):
    world, _, source = setup(tmp_path)
    proof = prove_chapters(source, world)
    assert proof["chapter_entry_witnesses"] == {
        "departure": [], "homecoming": ["pursue_goal"]}
    assert proof["act_entry_witnesses"]["library"] == ["pursue_goal"]
    assert proof["cross_act_choices"] == [{
        "from": "bridge", "to": "library", "choice": "pursue_goal"}]
    replay = replay_chapters(source, world, ["pursue_goal"])
    assert replay["current"]["act"] == "library"
    assert replay["visited_acts"] == ["bridge", "library"]
    assert_code("chapters_review_required",
                lambda: render_chapters_html(source, world))


def test_schema_coverage_and_duplicates_fail_closed(tmp_path):
    world, _, source = setup(tmp_path)
    broken = json.loads(json.dumps(source))
    broken["chapters"][1]["acts"][0]["scenes"] = ["opening"]
    assert_code("chapters_duplicate_scene",
                lambda: validate_chapters(broken, world))
    broken = json.loads(json.dumps(source))
    broken["chapters"][1]["acts"][0]["scenes"] = ["absent"]
    assert_code("chapters_scene_coverage",
                lambda: validate_chapters(broken, world))
    broken = json.loads(json.dumps(source))
    broken["chapters"][1]["acts"][0]["id"] = "bridge"
    assert_code("chapters_duplicate_act",
                lambda: validate_chapters(broken, world))
    broken = json.loads(json.dumps(source))
    broken["world_digest"] = "0" * 64
    assert_code("chapters_source_lease_mismatch",
                lambda: validate_chapters(broken, world))


def test_review_compile_verify_player_and_editor(tmp_path):
    world, store, source = setup(tmp_path)
    first = store.publish(world["id"], source, create=True)
    published = store.inspect(world["id"])["chapters"]
    # Publication explicitly replaces the old draft review note and revokes
    # approval; the lease must bind the bytes actually persisted.
    assert published["approved"] is False
    assert first == digest(published)
    assert first != digest(source)
    assert_code("chapters_review_required",
                lambda: store.compile(world["id"], first))
    approved = store.approve(world["id"], first, "Author reviewed chapter structure")
    receipt = store.compile(world["id"], approved)
    assert store.verify(world["id"]) == receipt
    html = (tmp_path / "chapbook.chapters.playable.html").read_text()
    assert "The crossing" in html and "connect-src 'none'" in html
    assert engine_handoff(store.inspect(world["id"])["chapters"], world)[
        "navigation_policy"] == "actual_choice_graph_not_linearized"
    SessionStore(tmp_path).create(world["id"], "reader")
    view = store.player(world["id"], "reader")
    assert view["player"]["current"]["chapter"] == "departure"
    assert view["revision"] == 0
    editor = store.editor(world["id"], approved)
    assert editor["html_sha256"]
    assert "Export unapproved JSON" in (tmp_path / editor["html_file"]).read_text()


def test_review_reset_and_stale_edit(tmp_path):
    world, store, source = setup(tmp_path)
    first = store.publish(world["id"], source, create=True)
    approved = store.approve(world["id"], first, "Reviewed")
    changed = edit_chapters(store.inspect(world["id"])["chapters"], world, {
        "action": "replace_act",
        "value": {"chapter": "departure", "act": {
            "id": "bridge", "title": "The silent bridge",
            "summary": "A revised original scene", "scenes": ["opening"]}},
    })
    assert changed["approved"] is False
    assert_code("chapters_stale_edit",
                lambda: store.publish(world["id"], changed,
                                      expected_digest="f" * 64))
    next_digest = store.publish(world["id"], changed, expected_digest=approved)
    assert_code("chapters_review_required",
                lambda: store.compile(world["id"], next_digest))
    assert_code("chapters_stale_edit",
                lambda: store.compile(world["id"], approved))


def test_artifact_tamper_and_script_escape(tmp_path):
    world, store, source = setup(tmp_path)
    source["chapters"][0]["title"] = "</script><script>alert(1)</script>"
    first = store.publish(world["id"], source, create=True)
    approved = store.approve(world["id"], first, "Reviewed literal HTML-looking text")
    store.compile(world["id"], approved)
    html = (tmp_path / "chapbook.chapters.playable.html").read_text()
    assert "</script><script>alert(1)</script>" not in html
    assert "\\u003c/script>" in html
    path = tmp_path / "chapbook.chapters.engine.json"
    path.write_text("{}")
    assert_code("chapters_artifact_mismatch",
                lambda: store.verify(world["id"]))
