"""Dialogue CLI and read-only Jeeves previews, atomic saved world handoff."""
from __future__ import annotations

import json
import os
import pytest

from skeleton.jeeves.worlds.cast import CastStore, approve_cast, propose_cast
from skeleton.jeeves.worlds.dialogue_graph_cli import run
from skeleton.jeeves.worlds.session import SessionStore
from skeleton.jeeves.worlds.tools import invoke_world_tool, manifest
from skeleton.jeeves.worlds.world_canon import WorldStore, propose


@pytest.mark.skipif(os.name != "posix", reason="descriptor-anchored custody")
def test_operator_cli_and_atomic_dialogue_choice(tmp_path, capsys):
    world = propose(world_id="harbor", premise="Original harbor.",
                    protagonist="Ari", region="Harbor", goal="Reach shore.")
    WorldStore(tmp_path).publish(world, create=True)
    cast = approve_cast(propose_cast(
        world, npc_id="guide", npc_name="Mira",
        npc_line="The harbor is safe."), world, "Reviewed cast.")
    CastStore(tmp_path).publish("harbor", cast, create=True)
    common = ["--store", str(tmp_path)]
    assert run(common + ["propose", "--world-id", "harbor",
        "--prompt", "Ask Mira for directions.", "--conversation-id", "directions",
        "--actor", "guide", "--scene", "opening",
        "--text", "Follow the pier?", "--response-id", "yes",
        "--label", "I will.", "--world-choice", "pursue_goal"]) == 0
    source = json.loads(capsys.readouterr().out)["proposal"]
    assert source["approved"] is False
    assert run(common + ["save", "--world-id", "harbor", "--create",
                         "--source-json", json.dumps(source)]) == 0
    lease = json.loads(capsys.readouterr().out)["dialogue_digest"]
    assert run(common + ["approve", "--world-id", "harbor",
                         "--expected-digest", lease,
                         "--review-note", "Reviewed."]) == 0
    approved = json.loads(capsys.readouterr().out)["dialogue_digest"]
    assert run(common + ["compile", "--world-id", "harbor",
                         "--expected-digest", approved]) == 0
    capsys.readouterr()
    assert run(common + ["verify", "--world-id", "harbor"]) == 0
    capsys.readouterr()
    session = SessionStore(tmp_path)
    start = session.create("harbor", "saveone")
    args = ["--world-id", "harbor", "--slot", "saveone",
            "--conversation", "directions", "--responses-json", '["yes"]']
    assert run(common + ["player"] + args) == 0
    preview = json.loads(capsys.readouterr().out)
    assert preview["dialogue"]["world_choice"] == "pursue_goal"
    assert run(common + ["choose"] + args +
               ["--expected-session-digest", "0" * 64,
                "--expected-dialogue-digest", approved]) == 2
    assert json.loads(capsys.readouterr().out)["error"] == "dialogue_stale_session"
    assert session.read("harbor", "saveone")["choices"] == []
    assert run(common + ["choose"] + args +
               ["--expected-session-digest", start["session_digest"],
                "--expected-dialogue-digest", approved]) == 0
    after = json.loads(capsys.readouterr().out)
    assert after["scene"] == "resolution"
    assert session.read("harbor", "saveone")["choices"] == ["pursue_goal"]
    assert "world.dialogue_preview" in {
        tool["name"] for tool in manifest()["tools"]}
    for name, tool_args in [
        ("world.dialogue_preview", {}),
        ("world.dialogue_propose_preview", {
            "prompt": "Original directions", "conversation_id": "directions",
            "actor": "guide", "scene": "opening", "text": "Follow the pier?",
            "response_id": "yes", "label": "I will.",
            "world_choice": "pursue_goal",
        }),
    ]:
        result = invoke_world_tool(str(tmp_path), {
            "schema": "jeeves.world.tool_request.v1",
            "tool": name, "world_id": "harbor", "args": tool_args,
        })
        assert result["persisted"] is False
