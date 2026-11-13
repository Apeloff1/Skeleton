"""Operator dialogue transcript CLI and read-only Jeeves progress tool."""
from __future__ import annotations

import json
import os
import pytest

from skeleton.jeeves.worlds.cast import CastStore, approve_cast, propose_cast
from skeleton.jeeves.worlds.dialogue_graph import DialogueStore, propose_dialogue
from skeleton.jeeves.worlds.dialogue_transcript_cli import run
from skeleton.jeeves.worlds.session import SessionStore
from skeleton.jeeves.worlds.tools import invoke_world_tool, manifest
from skeleton.jeeves.worlds.world_canon import WorldStore, propose


@pytest.mark.skipif(os.name != "posix", reason="descriptor-anchored custody")
def test_cli_and_read_only_preview(tmp_path, capsys):
    world = propose(world_id="harbor", premise="Original harbor.",
                    protagonist="Ari", region="Harbor", goal="Reach shore.")
    WorldStore(tmp_path).publish(world, create=True)
    cast = approve_cast(propose_cast(
        world, npc_id="guide", npc_name="Mira",
        npc_line="The pier is safe."), world, "Reviewed cast.")
    CastStore(tmp_path).publish("harbor", cast, create=True)
    d = DialogueStore(tmp_path)
    lease = d.publish("harbor", propose_dialogue(
        world, cast, prompt="Original directions", conversation_id="directions",
        actor="guide", scene="opening", text="Follow the pier?",
        response_id="yes", label="I will.", world_choice="pursue_goal"), create=True)
    approved = d.approve("harbor", lease, "Reviewed dialogue.")
    session = SessionStore(tmp_path).create("harbor", "saveone")
    common = ["--store", str(tmp_path)]
    assert run(common + ["begin", "--world-id", "harbor", "--slot", "saveone",
                         "--conversation", "directions",
                         "--expected-session-digest", session["session_digest"],
                         "--expected-dialogue-digest", approved]) == 0
    begun = json.loads(capsys.readouterr().out)
    assert "world.dialogue_transcript_preview" in {
        item["name"] for item in manifest()["tools"]}
    result = invoke_world_tool(str(tmp_path), {
        "schema": "jeeves.world.tool_request.v1",
        "tool": "world.dialogue_transcript_preview",
        "world_id": "harbor", "args": {"slot": "saveone"},
    })
    assert result["persisted"] is False
    assert result["result"]["transcript_digest"] == begun["transcript_digest"]
    assert run(common + ["append", "--world-id", "harbor", "--slot", "saveone",
                         "--response-id", "yes", "--expected-digest",
                         begun["transcript_digest"]]) == 0
    advanced = json.loads(capsys.readouterr().out)
    assert run(common + ["commit", "--world-id", "harbor", "--slot", "saveone",
                         "--expected-digest", advanced["transcript_digest"]]) == 0
    capsys.readouterr()
    assert run(common + ["verify", "--world-id", "harbor",
                         "--slot", "saveone"]) == 0
    assert json.loads(capsys.readouterr().out)["receipt"][
        "world_choice"] == "pursue_goal"
