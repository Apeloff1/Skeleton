"""End-to-end director: approved chapters + cinema -> one HTML5 world."""
from __future__ import annotations

import json

import pytest

from skeleton.jeeves.worlds.chapters import ChapterStore
from skeleton.jeeves.worlds.cinematics import CinematicsStore
from skeleton.jeeves.worlds.director import DirectorStore, compile_director
from skeleton.jeeves.worlds.director_cli import run
from skeleton.jeeves.worlds.session import SessionStore
from skeleton.jeeves.worlds.tools import invoke_world_tool, manifest
from skeleton.jeeves.worlds.world_canon import CanonError, WorldStore, propose


def fixture(tmp_path):
    world = propose(world_id="director", premise="A courier meets a strange light",
                    protagonist="Ira", region="Hollow Coast", goal="Return home")
    WorldStore(tmp_path).publish(world, create=True)
    chapters = ChapterStore(tmp_path)
    chapter_source = chapters.propose("director", prompt="Original chapter headings",
        chapters=[{"id": "story", "title": "A Journey", "summary": "The road home",
                   "acts": [{"id": "first", "title": "The Light", "summary": "The choice",
                             "scenes": ["opening"]},
                            {"id": "last", "title": "Home", "summary": "The return",
                             "scenes": ["resolution"]}]}])
    cd = chapters.publish("director", chapter_source, create=True)
    chapters.approve("director", cd, "Reviewed original structure")
    cinema = CinematicsStore(tmp_path)
    cinema_source = cinema.propose("director", prompt="Original opening cinematic",
        sequences=[{"scene": "opening", "beats": [
            {"id": "first", "cue": "arrival",
             "caption": "A pale light rises.", "duration_ms": 1100}]}])
    bd = cinema.publish("director", cinema_source, create=True)
    cinema.approve("director", bd, "Reviewed original caption")
    return DirectorStore(tmp_path), world


def reject(code, callback):
    with pytest.raises(CanonError) as exc:
        callback()
    assert exc.value.code == code


def test_director_compile_replay_receipt_and_tamper(tmp_path):
    store, world = fixture(tmp_path)
    info = store.inspect("director")
    assert info["scene_count"] == 2
    receipt = store.compile("director", info["source_digests"])
    assert receipt == store.verify("director")
    page = (tmp_path / "director.director.playable.html").read_text()
    assert "A Journey" in page and "A pale light rises" in page
    assert "script-src 'sha256-" in page
    assert "connect-src 'none'" in page
    SessionStore(tmp_path).create("director", "reader")
    view = store.player("director", "reader")
    assert view["player"]["chapters"]["current"]["act"] == "first"
    assert view["player"]["cinematics"]["visits"][0]["scene"] == "opening"
    forged = dict(info["source_digests"], chapters="0" * 64)
    reject("director_stale_source", lambda: store.compile("director", forged))
    (tmp_path / "director.director.manifest.json").write_text("{}")
    reject("director_artifact_mismatch", lambda: store.verify("director"))


def test_readonly_jeeves_and_cli_director(tmp_path, capsys):
    store, _ = fixture(tmp_path)
    names = {item["name"] for item in manifest()["tools"]}
    assert "world.director_preview" in names
    result = invoke_world_tool(str(tmp_path), {
        "schema": "jeeves.world.tool_request.v1",
        "tool": "world.director_preview", "world_id": "director", "args": {},
    })
    assert result["persisted"] is False
    assert result["result"]["scene_count"] == 2
    assert run(["--store", str(tmp_path), "inspect", "--id", "director"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["ok"] is True
    assert run(["--store", str(tmp_path), "compile", "--id", "director",
                "--expected-digests-json", json.dumps(
                    output["source_digests"])]) == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True


def test_director_session_transition_and_exact_world_revision(tmp_path):
    store, world = fixture(tmp_path)
    SessionStore(tmp_path).create("director", "reader")
    before = SessionStore(tmp_path).read("director", "reader")
    result = SessionStore(tmp_path).choose(
        "director", "reader", "pursue_goal",
        __import__("skeleton.jeeves.worlds.world_canon",
                   fromlist=["digest"]).digest(before))
    assert result["ending"] == "Return home"
    view = store.player("director", "reader")
    assert view["player"]["scene"] == "resolution"
    assert view["player"]["chapters"]["current"]["act"] == "last"
    assert len(view["player"]["chapters"]["visits"]) == 2
    assert len(view["player"]["cinematics"]["visits"]) == 1
    # A source revision is not permission to replay old approved storyboards.
    from skeleton.jeeves.worlds.world_canon import WorldStore, edit, digest
    changed = edit(world, {"action": "replace_scene", "value": {
        "id": "opening", "title": "A revised original coast",
        "narrative": "A new authored opening."}})
    WorldStore(tmp_path).publish(changed, expected_digest=digest(world))
    reject("chapters_source_lease_mismatch", lambda: store.inspect("director"))
    reject("chapters_source_lease_mismatch", lambda: store.player("director", "reader"))


def test_director_tool_player_never_mutates(tmp_path):
    store, _ = fixture(tmp_path)
    SessionStore(tmp_path).create("director", "reader")
    before = (tmp_path / "director.reader.session.json").read_bytes()
    result = invoke_world_tool(str(tmp_path), {
        "schema": "jeeves.world.tool_request.v1",
        "tool": "world.director_player", "world_id": "director",
        "args": {"slot": "reader"},
    })
    assert result["persisted"] is False
    assert result["result"]["revision"] == 0
    assert (tmp_path / "director.reader.session.json").read_bytes() == before
