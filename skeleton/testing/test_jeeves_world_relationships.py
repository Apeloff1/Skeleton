"""Source-leased NPC trust: proposal, replay, custody, proof and hostile inputs."""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
import pytest

from skeleton.jeeves.worlds.cast import CastStore, approve_cast, propose_cast
from skeleton.jeeves.worlds.relationships import (
    RelationshipStore, edit_relationships, evaluate_relationships,
    prove_relationships, render_relationships_html,
)
from skeleton.jeeves.worlds.relationships_cli import run
from skeleton.jeeves.worlds.tools import invoke_world_tool, manifest
from skeleton.jeeves.worlds.world_canon import CanonError, WorldStore, digest, propose


def fixture(tmp_path):
    world = propose(world_id="harbor", premise="An original harbor treaty",
                    protagonist="Mara", region="Glass Bay", goal="Restore trust")
    WorldStore(tmp_path).publish(world, create=True)
    cast = propose_cast(world, npc_id="tala", npc_name="Tala",
                        npc_line="The harbor remembers every promise.")
    cast["characters"][0]["scenes"] = ["opening", "resolution"]
    cast = approve_cast(cast, world, "Original cast reviewed")
    CastStore(tmp_path).publish("harbor", cast, create=True)
    store = RelationshipStore(tmp_path)
    source = store.propose(
        "harbor", prompt="Tala trusts Mara after the treaty",
        bond_id="tala_trust", actor="tala", name="Tala",
        choice="pursue_goal", delta=12, reason="Mara honored the pact",
        reaction_id="treaty_respected", scene="resolution",
        min_score=10, max_score=100, text="Tala welcomes Mara to the council.")
    return world, cast, store, source


def reject(code, fn):
    with pytest.raises(CanonError) as exc:
        fn()
    assert exc.value.code == code


def test_replay_proof_and_actual_choice(tmp_path):
    world, cast, _, source = fixture(tmp_path)
    proof = prove_relationships(source, world, cast)
    assert proof["reaction_witnesses"]["tala_trust:treaty_respected"] == ["pursue_goal"]
    player = evaluate_relationships(source, world, cast, ["pursue_goal"])
    assert player["scores"] == {"tala_trust": 12}
    assert player["reactions"][0]["reaction"] == "treaty_respected"
    reject("session_invalid_transition", lambda: evaluate_relationships(
        source, world, cast, ["forged_choice"]))


def test_review_compile_receipt_and_tamper(tmp_path):
    _, _, store, source = fixture(tmp_path)
    source["approved"] = True
    source["review_note"] = "Forged"
    first = store.publish("harbor", source, create=True)
    assert store.inspect("harbor")["relationships"]["approved"] is False
    reject("relationships_review_required", lambda: store.compile("harbor", first))
    approved = store.approve("harbor", expected_digest=first, review_note="Reviewed")
    receipt = store.compile("harbor", approved)
    assert store.verify("harbor") == receipt
    playable = tmp_path / receipt["html_file"]
    assert sha256(playable.read_bytes()).hexdigest() == receipt["html_sha256"]
    assert b"connect-src 'none'" in playable.read_bytes()
    assert b"harbor remembers every promise" in playable.read_bytes()
    playable.write_bytes(playable.read_bytes() + b"<!-- tampered -->")
    reject("relationships_playable_mismatch", lambda: store.verify("harbor"))


def test_edit_stale_lease_and_unreachable_reaction(tmp_path):
    world, cast, store, source = fixture(tmp_path)
    first = store.publish("harbor", source, create=True)
    edited = edit_relationships(store.inspect("harbor")["relationships"],
                                world, cast,
                                {"action": "replace_bond", "value": source["bonds"][0]})
    assert edited["approved"] is False
    reject("relationships_stale_edit", lambda: store.publish(
        "harbor", edited, expected_digest="0" * 64))
    invalid = deepcopy(source)
    invalid["bonds"][0]["reactions"][0]["min_score"] = 90
    reject("relationships_unreachable_reaction",
           lambda: prove_relationships(invalid, world, cast))
    invalid = deepcopy(source)
    second = deepcopy(invalid["bonds"][0]["reactions"][0])
    second["id"] = "z_second"
    invalid["bonds"][0]["reactions"].append(second)
    reject("relationships_ambiguous_reaction",
           lambda: prove_relationships(invalid, world, cast))
    invalid = deepcopy(source)
    invalid["cast_digest"] = "0" * 64
    reject("relationships_source_lease_mismatch",
           lambda: prove_relationships(invalid, world, cast))
    reject("relationships_review_required",
           lambda: render_relationships_html(edited, world, cast))


def test_offline_editor_cli_and_readonly_tools(tmp_path, capsys):
    _, _, store, source = fixture(tmp_path)
    first = store.publish("harbor", source, create=True)
    editor = store.editor("harbor", first)
    page = (tmp_path / editor["html_file"]).read_bytes()
    assert b"Export unapproved relationships" in page
    assert b"connect-src 'none'" in page
    reject("relationships_stale_edit", lambda: store.editor("harbor", "0" * 64))
    assert run(["--store", str(tmp_path), "inspect", "--world-id", "harbor"]) == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True
    names = {item["name"] for item in manifest()["tools"]}
    assert {"world.relationships_preview", "world.relationships_propose_preview"} <= names
    response = invoke_world_tool(str(tmp_path), {
        "schema": "jeeves.world.tool_request.v1",
        "tool": "world.relationships_preview", "world_id": "harbor", "args": {},
    })
    assert response["persisted"] is False
    assert response["result_digest"] == digest(response["result"])


def test_symlink_and_numeric_overflow_fail_closed(tmp_path, capsys):
    _, _, store, source = fixture(tmp_path)
    store.publish("harbor", source, create=True)
    path = tmp_path / "harbor.relationships.json"
    other = tmp_path / "other.json"
    other.write_bytes(path.read_bytes())
    path.unlink()
    path.symlink_to(other)
    with pytest.raises((CanonError, OSError)):
        store.inspect("harbor")
    assert run(["--store", str(tmp_path), "save", "--world-id", "harbor",
                "--relationships-json", '{"n":1e999}']) == 2
    assert json.loads(capsys.readouterr().out)["error"] == "nonfinite_number"


def test_cli_player_requires_review_then_replays_approved_source(tmp_path, capsys):
    _, _, store, source = fixture(tmp_path)
    first = store.publish("harbor", source, create=True)
    command = ["--store", str(tmp_path), "player", "--world-id", "harbor",
               "--choices-json", '["pursue_goal"]']
    assert run(command) == 2
    assert json.loads(capsys.readouterr().out)["error"] == "relationships_review_required"
    store.approve("harbor", expected_digest=first, review_note="Reviewed")
    assert run(command) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["player"]["scores"]["tala_trust"] == 12
    assert result["player"]["reactions"][0]["reaction"] == "treaty_respected"
    command[-1] = '["forged"]'
    assert run(command) == 2
    assert json.loads(capsys.readouterr().out)["error"] == "session_invalid_transition"


def test_script_breakout_is_escaped_in_playable_and_editor(tmp_path):
    _, _, store, source = fixture(tmp_path)
    source["bonds"][0]["reactions"][0]["text"] = "</script><script>alert(1)</script>"
    first = store.publish("harbor", source, create=True)
    editor = store.editor("harbor", first)
    editor_bytes = (tmp_path / editor["html_file"]).read_bytes()
    assert b"</script><script>alert(1)" not in editor_bytes
    approved = store.approve("harbor", expected_digest=first, review_note="Reviewed")
    receipt = store.compile("harbor", approved)
    playable = (tmp_path / receipt["html_file"]).read_bytes()
    assert b"</script><script>alert(1)" not in playable
    assert b"\\u003c/script>" in playable
    assert store.verify("harbor") == receipt


def test_persisted_player_slot_replay_and_jeeves_parity(tmp_path, capsys):
    from skeleton.jeeves.worlds.session import SessionStore
    _, _, store, source = fixture(tmp_path)
    first = store.publish("harbor", source, create=True)
    sessions = SessionStore(tmp_path)
    sessions.create("harbor", "chapter_one")
    reject("relationships_review_required",
           lambda: store.player("harbor", "chapter_one"))
    store.approve("harbor", expected_digest=first, review_note="Reviewed")
    initial = sessions.read("harbor", "chapter_one")
    sessions.choose("harbor", "chapter_one", "pursue_goal", digest(initial))
    result = store.player("harbor", "chapter_one")
    assert result["player"]["scores"]["tala_trust"] == 12
    assert result["session_digest"] == digest(sessions.read("harbor", "chapter_one"))
    args = ["--store", str(tmp_path), "player-slot", "--world-id", "harbor",
            "--slot", "chapter_one"]
    assert run(args) == 0
    assert json.loads(capsys.readouterr().out)["player"] == result["player"]
    tool = invoke_world_tool(str(tmp_path), {
        "schema": "jeeves.world.tool_request.v1",
        "tool": "world.relationships_player", "world_id": "harbor",
        "args": {"slot": "chapter_one"},
    })
    assert tool["result"] == result
    assert tool["persisted"] is False
    session_path = tmp_path / "harbor.chapter_one.session.json"
    payload = json.loads(session_path.read_text())
    payload["flags"] = ["forged"]
    session_path.write_text(json.dumps(payload))
    reject("session_replay_mismatch",
           lambda: store.player("harbor", "chapter_one"))
