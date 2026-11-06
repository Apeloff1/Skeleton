"""Reviewed original epilogues: coverage, replay, custody and CLI."""
from __future__ import annotations

import copy
import json

import pytest

from skeleton.jeeves.worlds.epilogues import (
    EpilogueStore, ending_view, propose_epilogues, render_epilogue_html,
    validate_epilogues,
)
from skeleton.jeeves.worlds.epilogues_cli import run
from skeleton.jeeves.worlds.epilogues_editor import render_epilogues_editor
from skeleton.jeeves.worlds.session import SessionStore, new_session
from skeleton.jeeves.worlds.tools import SCHEMA, invoke_world_tool
from skeleton.jeeves.worlds.world_canon import (
    CanonError, WorldStore, canonical, digest, propose,
)


def setup(tmp_path):
    world = propose(world_id="delta", premise="The lighthouse goes dark.",
                    protagonist="Ari", region="Delta", goal="Restore the light.")
    WorldStore(tmp_path).publish(world, create=True)
    sessions = SessionStore(tmp_path)
    sessions.create("delta", "player")
    entries = [{
        "scene": ending["scene"], "title": "After the beacon",
        "text": "Ari kept the light burning for the next voyage.",
    } for ending in sorted(world["endings"], key=lambda e: e["scene"])]
    store = EpilogueStore(tmp_path)
    source = store.propose("delta", prompt="Original beacon epilogue", entries=entries)
    return world, sessions, store, source


def test_reviewed_ending_earned_player_and_verified_html(tmp_path):
    world, sessions, store, source = setup(tmp_path)
    assert source["approved"] is False
    lease = store.publish("delta", source, create=True)
    with pytest.raises(CanonError, match="epilogues_review_required"):
        ending_view(source, world, new_session(world))
    approved = store.approve("delta", lease, "Reviewed original text and ending closure")
    with pytest.raises(CanonError, match="epilogues_ending_not_earned"):
        store.player("delta", "player")
    session = sessions.read("delta", "player")
    # Follow the canonical source route, never invent an earned ending.
    for choice in world["choices"]:
        if choice["from"] == session["scene"]:
            sessions.choose("delta", "player", choice["id"], digest(session))
            session = sessions.read("delta", "player")
            if session["ending"] is not None:
                break
    assert session["ending"] is not None
    view = store.player("delta", "player")
    assert view["epilogues_digest"] == approved
    assert view["session_digest"] == digest(session)
    result = store.compile("delta", "player", approved, digest(session))
    assert result["html_sha256"]
    assert store.verify("delta", "player")["html_sha256"] == result["html_sha256"]
    page = (tmp_path / result["html_file"]).read_bytes()
    assert b"Content-Security-Policy" in page
    assert b"script-src 'none'" in page


def test_coverage_and_duplicate_endings_rejected(tmp_path):
    world, _, _, source = setup(tmp_path)
    bad = copy.deepcopy(source)
    bad["entries"] = []
    with pytest.raises(CanonError, match="epilogues_ending_coverage"):
        validate_epilogues(bad, world)
    bad = copy.deepcopy(source)
    bad["entries"].append(copy.deepcopy(bad["entries"][0]))
    with pytest.raises(CanonError, match="epilogues_ending_coverage"):
        validate_epilogues(bad, world)


def test_unapproved_persistence_cannot_bypass_operator_review(tmp_path):
    _, _, store, source = setup(tmp_path)
    forged = {**source, "approved": True, "review_note": "not approved"}
    with pytest.raises(CanonError, match="epilogues_approval_bypass"):
        store.publish("delta", forged, create=True)
    first = store.publish("delta", source, create=True)
    with pytest.raises(CanonError, match="epilogues_stale_source"):
        store.publish("delta", source, create=True)
    with pytest.raises(CanonError, match="epilogues_stale_source"):
        store.approve("delta", "0" * 64, "reviewed")
    approved = store.approve("delta", first, "reviewed")
    assert store.inspect("delta")["source_digest"] == approved


def test_forged_player_and_changed_world_fail_closed(tmp_path):
    world, sessions, store, source = setup(tmp_path)
    store.publish("delta", source, create=True)
    store.approve("delta", digest(source), "reviewed")
    session = sessions.read("delta", "player")
    forged = {**session, "ending": "fake"}
    with pytest.raises(CanonError, match="session_replay_mismatch"):
        ending_view({**source, "approved": True, "review_note": "reviewed"}, world, forged)
    changed = copy.deepcopy(world)
    changed["prompt"] = "New canon"
    with pytest.raises(CanonError, match="epilogues_world_lease_mismatch"):
        validate_epilogues(source, changed)


def test_escaped_original_prose_not_executable_html(tmp_path):
    world, _, _, source = setup(tmp_path)
    source["entries"][0]["text"] = "</script><img src=x onerror=alert(1)>"
    source["approved"] = True
    source["review_note"] = "reviewed"
    from skeleton.jeeves.worlds.session import apply_choice
    session = new_session(world)
    for choice in world["choices"]:
        if choice["from"] == session["scene"]:
            session = apply_choice(session, world, choice["id"])
            if session["ending"]:
                break
    view = ending_view(source, world, session)
    page = render_epilogue_html(view)
    assert b"<img src=x" not in page
    assert b"&lt;img" in page


def test_cli_proposal_and_read_only_jeeves_preview(tmp_path, capsys):
    world, _, store, source = setup(tmp_path)
    request = {"prompt": source["prompt"], "entries": source["entries"]}
    path = tmp_path / "request.json"
    path.write_bytes(canonical(request))
    assert run(["--store", str(tmp_path), "propose", "--world-id", "delta",
                "--file", str(path)]) == 0
    assert json.loads(capsys.readouterr().out)["result"]["review_required"]
    response = invoke_world_tool(str(tmp_path), {
        "schema": SCHEMA, "tool": "world.epilogues_propose_preview",
        "world_id": "delta", "args": request,
    })
    assert response["persisted"] is False
    assert response["result"] == source


def test_offline_editor_source_lease_and_csp(tmp_path):
    world, _, store, source = setup(tmp_path)
    lease = store.publish("delta", source, create=True)
    page = render_epilogues_editor(source, world)
    assert b"Content-Security-Policy" in page
    assert b"connect-src 'none'" in page
    assert b"sha256-" in page
    result = store.editor("delta", lease)
    assert (tmp_path / result["html_file"]).read_bytes() == page
    with pytest.raises(CanonError, match="epilogues_stale_source"):
        store.editor("delta", "0" * 64)
    store.approve("delta", lease, "Reviewed")
    with pytest.raises(CanonError, match="epilogues_editor_requires_draft"):
        store.editor("delta", store.inspect("delta")["source_digest"])


def test_offline_editor_escapes_embedded_original_prose(tmp_path):
    world, _, _, source = setup(tmp_path)
    source["entries"][0]["text"] = "</script><img src=x onerror=alert(1)>"
    page = render_epilogues_editor(source, world)
    assert b"<img src=x" not in page
    assert b"\\u003c/script>" in page
