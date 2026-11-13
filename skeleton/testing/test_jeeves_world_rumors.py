"""Rumor transmission, causal witnesses, contradictory branches, custody and CLI."""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json

import pytest

from skeleton.jeeves.worlds.cast import CastStore, approve_cast, propose_cast
from skeleton.jeeves.worlds.rumors import (
    RumorStore, edit_rumors, prove_rumors, replay_rumors, render_rumors_html,
)
from skeleton.jeeves.worlds.rumors_cli import run
from skeleton.jeeves.worlds.tools import invoke_world_tool, manifest
from skeleton.jeeves.worlds.world_canon import CanonError, WorldStore, digest, propose


def fixture(tmp_path):
    world = propose(world_id="harbor", premise="An original harbor whisper",
                    protagonist="Mara", region="Glass Bay", goal="Reach the archive")
    WorldStore(tmp_path).publish(world, create=True)
    cast = propose_cast(world, npc_id="tala", npc_name="Tala",
                        npc_line="The archive is open tonight.")
    cast["characters"][0]["scenes"] = ["opening", "resolution"]
    cast = approve_cast(cast, world, "Original rumor reviewed")
    CastStore(tmp_path).publish("harbor", cast, create=True)
    store = RumorStore(tmp_path)
    source = store.propose(
        "harbor", prompt="Tala learns the archive is open",
        rumor_id="archive_open", claim="archive_status", stance="supports",
        origin="tala", seed_choice="pursue_goal",
        text="The archive is open after dusk.")
    return world, cast, store, source


def reject(code, fn):
    with pytest.raises(CanonError) as exc:
        fn()
    assert exc.value.code == code


def test_seed_proof_replay_and_invalid_choice(tmp_path):
    world, cast, _, source = fixture(tmp_path)
    proof = prove_rumors(source, world, cast)
    assert proof["delivery_witnesses"]["seed:archive_open"] == ["pursue_goal"]
    player = replay_rumors(source, world, cast, ["pursue_goal"])
    assert player["steps"][-1]["heard"][0]["actor"] == "tala"
    reject("session_invalid_transition",
           lambda: replay_rumors(source, world, cast, ["forged"]))


def test_review_compile_and_artifact_tamper(tmp_path):
    _, _, store, source = fixture(tmp_path)
    source["approved"] = True
    first = store.publish("harbor", source, create=True)
    assert store.inspect("harbor")["rumors"]["approved"] is False
    reject("rumors_review_required", lambda: store.compile("harbor", first))
    approved = store.approve("harbor", expected_digest=first, review_note="Reviewed")
    receipt = store.compile("harbor", approved)
    assert store.verify("harbor") == receipt
    page = tmp_path / receipt["html_file"]
    assert sha256(page.read_bytes()).hexdigest() == receipt["html_sha256"]
    assert b"connect-src 'none'" in page.read_bytes()
    page.write_bytes(page.read_bytes() + b"<!-- modified -->")
    reject("rumors_playable_mismatch", lambda: store.verify("harbor"))


def test_invalid_source_and_coexisting_contradiction(tmp_path):
    world, cast, _, source = fixture(tmp_path)
    bad = deepcopy(source)
    bad["world_digest"] = "0" * 64
    reject("rumors_source_lease_mismatch", lambda: prove_rumors(bad, world, cast))
    bad = deepcopy(source)
    bad["rumors"][0]["origin"] = "unknown"
    reject("rumors_unknown_origin", lambda: prove_rumors(bad, world, cast))
    bad = deepcopy(source)
    bad["rumors"].append({
        "id": "z_denial", "claim": "archive_status", "stance": "denies",
        "origin": "tala", "seed_choice": "pursue_goal",
        "text": "The archive is closed."})
    reject("rumors_coexisting_contradiction", lambda: prove_rumors(bad, world, cast))
    bad["rumors"][1]["claim"] = "another_claim"
    assert len(prove_rumors(bad, world, cast)["delivery_witnesses"]) == 2


def test_invalid_route_and_stale_edit(tmp_path):
    world, cast, store, source = fixture(tmp_path)
    first = store.publish("harbor", source, create=True)
    bad = deepcopy(source)
    bad["routes"] = [{"id": "handoff", "rumor": "archive_open",
                      "from_actor": "tala", "to_actor": "missing",
                      "choice": "pursue_goal", "scene": "resolution"}]
    reject("rumors_invalid_transfer", lambda: prove_rumors(bad, world, cast))
    edited = edit_rumors(source, world, cast, {
        "action": "replace_rumor", "value": source["rumors"][0]})
    assert not edited["approved"]
    reject("rumors_stale_edit", lambda: store.publish(
        "harbor", edited, expected_digest="0" * 64))
    assert store.publish("harbor", edited, expected_digest=first)


def test_editor_cli_tools_read_only(tmp_path, capsys):
    _, _, store, source = fixture(tmp_path)
    first = store.publish("harbor", source, create=True)
    editor = store.editor("harbor", first)
    page = (tmp_path / editor["html_file"]).read_bytes()
    assert b"Export unapproved rumors" in page
    assert b"connect-src 'none'" in page
    reject("rumors_stale_edit", lambda: store.editor("harbor", "0" * 64))
    assert run(["--store", str(tmp_path), "inspect", "--world-id", "harbor"]) == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True
    names = {item["name"] for item in manifest()["tools"]}
    assert {"world.rumors_preview", "world.rumors_propose_preview"} <= names
    response = invoke_world_tool(str(tmp_path), {
        "schema": "jeeves.world.tool_request.v1",
        "tool": "world.rumors_preview", "world_id": "harbor", "args": {},
    })
    assert response["persisted"] is False
    assert response["result_digest"] == digest(response["result"])
    preview = invoke_world_tool(str(tmp_path), {
        "schema": "jeeves.world.tool_request.v1",
        "tool": "world.rumors_propose_preview", "world_id": "harbor",
        "args": {"prompt": "Archive rumor", "rumor_id": "archive_open",
                 "claim": "archive_status", "stance": "supports", "origin": "tala",
                 "seed_choice": "pursue_goal", "text": "The archive is open."},
    })
    assert preview["review_required"] is True
    assert preview["result"]["approved"] is False


def test_unapproved_player_and_invalid_text(tmp_path):
    world, cast, _, source = fixture(tmp_path)
    reject("rumors_review_required", lambda: render_rumors_html(source, world, cast))
    bad = deepcopy(source)
    bad["rumors"][0]["text"] = "\u0000"
    reject("control_character", lambda: prove_rumors(bad, world, cast))
