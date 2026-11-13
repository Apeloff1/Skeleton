"""Field journal replay, source leases, offline editor and CLI."""
from __future__ import annotations

import json

import pytest

from skeleton.jeeves.worlds.field_journal import (
    FieldJournalStore, new_journal, validate_journal,
)
from skeleton.jeeves.worlds.field_journal_cli import run
from skeleton.jeeves.worlds.field_journal_editor import render_field_journal_editor
from skeleton.jeeves.worlds.session import SessionStore
from skeleton.jeeves.worlds.tools import SCHEMA, invoke_world_tool
from skeleton.jeeves.worlds.world_canon import (
    CanonError, WorldStore, canonical, digest, propose,
)


def setup(tmp_path):
    world = propose(world_id="delta", premise="Explore the harbor.",
                    protagonist="Ari", region="Delta", goal="Find the beacon")
    WorldStore(tmp_path).publish(world, create=True)
    sessions = SessionStore(tmp_path)
    sessions.create("delta", "player")
    store = FieldJournalStore(tmp_path)
    store.create("delta", "player")
    return world, sessions, store


def test_append_edit_and_replay_across_session_progress(tmp_path):
    world, sessions, store = setup(tmp_path)
    session = sessions.read("delta", "player")
    initial = store.inspect("delta", "player")
    proposal = store.preview("delta", "player", note_id="first", text="The harbor is quiet.")
    assert proposal["persisted"] is False
    assert proposal["scene"] == world["start"]
    added = store.append(
        "delta", "player", note_id="first", text="The harbor is quiet.",
        expected_journal_digest=initial["journal_digest"],
        expected_session_digest=digest(session))
    assert added["notes"][0]["at_revision"] == 0
    sessions.choose("delta", "player", "pursue_goal", digest(session))
    progressed = store.inspect("delta", "player")
    assert progressed["notes"][0]["scene"] == "opening"
    assert progressed["scene"] == "resolution"
    updated = store.edit(
        "delta", "player", note_id="first", text="The beacon is ahead.",
        expected_journal_digest=progressed["journal_digest"])
    assert updated["notes"][0]["text"] == "The beacon is ahead."
    with pytest.raises(CanonError, match="field_journal_stale_lease"):
        store.edit("delta", "player", note_id="first", text="stale",
                   expected_journal_digest=progressed["journal_digest"])


def test_replay_rejects_forged_note_scene_and_prefix(tmp_path):
    world, sessions, store = setup(tmp_path)
    session = sessions.read("delta", "player")
    data = new_journal(world, "player")
    data["entries"] = [{
        "id": "fake", "scene": "resolution", "at_revision": 0,
        "choices_digest": digest([]), "text": "I was never here",
    }]
    data["revision"] = 1
    with pytest.raises(CanonError, match="field_journal_replay_mismatch"):
        validate_journal(data, world, session, "player")
    data["entries"][0]["scene"] = "opening"
    data["entries"][0]["choices_digest"] = "0" * 64
    with pytest.raises(CanonError, match="field_journal_replay_mismatch"):
        validate_journal(data, world, session, "player")


def test_compiled_artifact_and_receipt_revalidated(tmp_path):
    _, sessions, store = setup(tmp_path)
    session = sessions.read("delta", "player")
    initial = store.inspect("delta", "player")
    added = store.append(
        "delta", "player", note_id="first", text="</script><img src=x>",
        expected_journal_digest=initial["journal_digest"],
        expected_session_digest=digest(session))
    with pytest.raises(CanonError, match="field_journal_stale_lease"):
        store.compile("delta", "player",
                      expected_journal_digest="0" * 64,
                      expected_session_digest=digest(session))
    result = store.compile(
        "delta", "player", expected_journal_digest=added["journal_digest"],
        expected_session_digest=digest(session))
    page = (tmp_path / result["html_file"]).read_bytes()
    assert b"connect-src 'none'" in page
    assert b"<img src=x>" not in page
    assert b"&lt;img" in page
    assert store.verify("delta", "player")["html_sha256"] == result["html_sha256"]
    (tmp_path / result["html_file"]).write_text("tampered")
    with pytest.raises(CanonError, match="field_journal_artifact_mismatch"):
        store.verify("delta", "player")


def test_cli_and_read_only_jeeves_proposal(tmp_path, capsys):
    _, _, store = setup(tmp_path)
    assert run(["--store", str(tmp_path), "inspect", "--world-id", "delta",
                "--slot", "player"]) == 0
    assert json.loads(capsys.readouterr().out)["ok"]
    request = {
        "schema": SCHEMA, "tool": "world.field_journal_propose_preview",
        "world_id": "delta",
        "args": {"slot": "player", "note_id": "first", "text": "A field note"},
    }
    result = invoke_world_tool(str(tmp_path), request)
    assert result["persisted"] is False
    assert result["result"]["expected_journal_digest"]


def test_editor_escapes_player_text_and_is_network_disabled(tmp_path):
    _, sessions, store = setup(tmp_path)
    session = sessions.read("delta", "player")
    initial = store.inspect("delta", "player")
    view = store.append(
        "delta", "player", note_id="first", text="</script><img src=x>",
        expected_journal_digest=initial["journal_digest"],
        expected_session_digest=digest(session))
    page = render_field_journal_editor(view)
    assert b"\\u003c/script>" in page
    assert b"<img src=x>" not in page
    assert b"sha256-" in page
    result = store.editor("delta", "player", view["journal_digest"])
    assert (tmp_path / result["html_file"]).read_bytes() == page
    with pytest.raises(CanonError, match="field_journal_stale_lease"):
        store.editor("delta", "player", "0" * 64)
