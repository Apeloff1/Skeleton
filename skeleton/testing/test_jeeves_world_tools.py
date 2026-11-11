"""Typed Jeeves read-only world tools cannot self-authorize mutations."""
from __future__ import annotations

import json
import os

import pytest

from skeleton.jeeves.worlds.evidence import (
    EvidenceStore, approve_evidence, propose_evidence,
)
from skeleton.jeeves.worlds.factions import (
    FactionStore, approve_factions, propose_factions,
)
from skeleton.jeeves.worlds.session import SessionStore
from skeleton.jeeves.worlds.tools import (
    SCHEMA, invoke_world_tool, manifest,
)
from skeleton.jeeves.worlds.tools_cli import run
from skeleton.jeeves.worlds.world_canon import (
    CanonError, WorldStore, digest, propose,
)


def world():
    return propose(
        world_id="marsh", premise="An original marsh journey.",
        protagonist="Iris", region="Marsh", goal="Reach home.",
    )


def request(tool, args=None):
    return {"schema": SCHEMA, "tool": tool, "world_id": "marsh",
            "args": args if args is not None else {}}


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor-anchored custody")
def test_read_only_typed_proposal_does_not_persist(tmp_path):
    root = tmp_path / "private"
    WorldStore(root).publish(world(), create=True)
    payload = invoke_world_tool(str(root), request("factions.propose_preview", {
        "prompt": "Trust should be earned.", "faction_id": "couriers",
        "name": "Couriers", "description": "Courier guild.",
        "choice_id": "pursue_goal", "delta": 4, "reason": "Reached home.",
    }))
    assert payload["review_required"] is True
    assert payload["persisted"] is False
    assert payload["result"]["approved"] is False
    assert not (root / "marsh.factions.json").exists()
    assert payload["result_digest"] == digest(payload["result"])


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor-anchored custody")
def test_evidence_preview_and_manifest_are_read_only(tmp_path):
    root = tmp_path / "private"
    WorldStore(root).publish(world(), create=True)
    preview = invoke_world_tool(str(root), request("evidence.propose_preview", {
        "prompt": "Find the letter.", "clue_id": "letter",
        "title": "A letter", "detail": "Hidden under a stone.",
        "unlock_choice": "pursue_goal",
    }))
    assert preview["result"]["clues"][0]["id"] == "letter"
    assert not (root / "marsh.evidence.json").exists()
    assert all(item["read_only"] for item in manifest()["tools"])


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor-anchored custody")
def test_real_player_tools_use_saved_session(tmp_path):
    root = tmp_path / "private"
    source = world()
    WorldStore(root).publish(source, create=True)
    faction = approve_factions(propose_factions(
        source, prompt="Trust.", faction_id="couriers",
        name="Couriers", description="Guild.", choice_id="pursue_goal",
        delta=6, reason="Earned."), source, "Reviewed.")
    evidence = approve_evidence(propose_evidence(
        source, prompt="Clue.", clue_id="letter", title="Letter",
        detail="Secret.", unlock_choice="pursue_goal"), source, "Reviewed.")
    FactionStore(root).publish("marsh", faction, create=True)
    EvidenceStore(root).publish("marsh", evidence, create=True)
    sessions = SessionStore(root)
    sessions.create("marsh", "one")
    before = invoke_world_tool(str(root), request("evidence.player", {"slot": "one"}))
    assert before["result"]["visible_clues"] == []
    saved = sessions.read("marsh", "one")
    sessions.choose("marsh", "one", "pursue_goal", digest(saved))
    faction_result = invoke_world_tool(str(root), request(
        "factions.player", {"slot": "one"}))
    evidence_result = invoke_world_tool(str(root), request(
        "evidence.player", {"slot": "one"}))
    assert faction_result["result"]["reputation"]["couriers"] == 6
    assert evidence_result["result"]["collected"] == ["letter"]


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor-anchored custody")
@pytest.mark.parametrize("tool,args,code", [
    ("factions.approve", {}, "unknown_world_tool"),
    ("world.proof", {"write": True}, "invalid_fields"),
    ("factions.propose_preview", {}, "invalid_fields"),
    ("evidence.player", {"slot": "../outside"}, "invalid_identifier"),
])
def test_model_cannot_invoke_unauthorized_or_malformed_tools(tmp_path, tool, args, code):
    root = tmp_path / "private"
    WorldStore(root).publish(world(), create=True)
    with pytest.raises(CanonError, match=code):
        invoke_world_tool(str(root), request(tool, args))


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor-anchored custody")
def test_cli_manifest_proof_and_rejected_write(tmp_path, capsys):
    root = tmp_path / "private"
    WorldStore(root).publish(world(), create=True)
    args = ["--store", str(root)]
    assert run(args + ["manifest"]) == 0
    assert json.loads(capsys.readouterr().out)["manifest"]["tools"]
    assert run(args + ["invoke", "--request-json",
                       json.dumps(request("world.proof"))]) == 0
    assert json.loads(capsys.readouterr().out)["response"]["result"]["source_digest"]
    assert run(args + ["invoke", "--request-json",
                       json.dumps(request("factions.approve"))]) == 2
    assert json.loads(capsys.readouterr().out)["error"] == "unknown_world_tool"
