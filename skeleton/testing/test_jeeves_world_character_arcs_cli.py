"""Arc CLI, typed Jeeves preview and saved player replay."""
from __future__ import annotations

import json
import os
import pytest

from skeleton.jeeves.worlds.cast import CastStore, approve_cast, propose_cast
from skeleton.jeeves.worlds.character_arcs_cli import run
from skeleton.jeeves.worlds.session import SessionStore
from skeleton.jeeves.worlds.tools import invoke_world_tool, manifest
from skeleton.jeeves.worlds.world_canon import WorldStore, propose


@pytest.mark.skipif(os.name != "posix", reason="descriptor-anchored custody")
def test_prompt_cli_review_compile_and_jeeves(tmp_path, capsys):
    world = propose(world_id="harbor", premise="Original voyage.",
                    protagonist="Ari", region="Harbor", goal="Reach shore.")
    WorldStore(tmp_path).publish(world, create=True)
    cast = approve_cast(propose_cast(
        world, npc_id="guide", npc_name="Mira",
        npc_line="The harbor is safe."), world, "Reviewed original cast.")
    CastStore(tmp_path).publish("harbor", cast, create=True)
    common = ["--store", str(tmp_path)]
    propose_args = [
        "--prompt", "Mira learns to trust.", "--actor", "guide",
        "--desire", "Guide travelers", "--starting-belief", "No one listens.",
        "--resolved-belief", "Ari listens.", "--choice", "pursue_goal",
        "--text", "Mira changes her mind.",
    ]
    assert run(common + ["propose", "--world-id", "harbor"] + propose_args) == 0
    source = json.loads(capsys.readouterr().out)["proposal"]
    assert source["approved"] is False
    assert run(common + ["save", "--world-id", "harbor", "--create",
                         "--source-json", json.dumps(source)]) == 0
    lease = json.loads(capsys.readouterr().out)["arcs_digest"]
    assert run(common + ["approve", "--world-id", "harbor",
                         "--expected-digest", lease,
                         "--review-note", "Reviewed."]) == 0
    approved = json.loads(capsys.readouterr().out)["arcs_digest"]
    assert run(common + ["compile", "--world-id", "harbor",
                         "--expected-digest", approved]) == 0
    capsys.readouterr()
    assert run(common + ["verify", "--world-id", "harbor"]) == 0
    capsys.readouterr()
    session = SessionStore(tmp_path)
    start = session.create("harbor", "saveone")
    session.choose("harbor", "saveone", "pursue_goal", start["session_digest"])
    assert run(common + ["player", "--world-id", "harbor",
                         "--slot", "saveone"]) == 0
    assert json.loads(capsys.readouterr().out)["replay"]["completed"] == ["guide"]
    names = {entry["name"] for entry in manifest()["tools"]}
    assert "world.character_arcs_preview" in names
    assert "world.character_arcs_propose_preview" in names
    for name, args in [
        ("world.character_arcs_preview", {}),
        ("world.character_arcs_propose_preview", {
            "prompt": "Original motivation", "actor": "guide",
            "desire": "Guide travelers", "starting_belief": "No one listens.",
            "resolved_belief": "Ari listens.", "choice": "pursue_goal",
            "text": "Mira changes her mind.",
        }),
        ("world.character_arcs_player", {"slot": "saveone"}),
    ]:
        result = invoke_world_tool(str(tmp_path), {
            "schema": "jeeves.world.tool_request.v1",
            "tool": name, "world_id": "harbor", "args": args,
        })
        assert result["persisted"] is False
        assert result["world_digest"]
