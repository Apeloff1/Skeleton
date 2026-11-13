"""Operator original NPC locale CLI and read-only Jeeves preview."""
from __future__ import annotations

import json
import os
import pytest

from skeleton.jeeves.worlds.cast import CastStore
from skeleton.jeeves.worlds.dialogue_graph import DialogueStore
from skeleton.jeeves.worlds.dialogue_localization_cli import run
from skeleton.jeeves.worlds.tools import invoke_world_tool, manifest
from skeleton.jeeves.worlds.world_canon import WorldStore
from skeleton.testing.test_jeeves_world_dialogue_localization_core import fixture


@pytest.mark.skipif(os.name != "posix", reason="descriptor-anchored custody")
def test_full_cli_and_jeeves_read_only(tmp_path, capsys):
    world, cast, dialogue, source = fixture()
    WorldStore(tmp_path).publish(world, create=True)
    CastStore(tmp_path).publish("harbor", cast, create=True)
    d = DialogueStore(tmp_path)
    lease = d.publish("harbor", {
        **dialogue, "approved": False, "review_note": ""}, create=True)
    d.approve("harbor", lease, "Reviewed original dialogue.")
    common = ["--store", str(tmp_path)]
    assert run(common + ["propose", "--world-id", "harbor",
        "--prompt", "Original Norwegian edition", "--tag", "nb-NO",
        "--conversation-id", "directions", "--node-id", "opening",
        "--text", "Følg bryggen?", "--response-id", "yes",
        "--label", "Ja."]) == 0
    proposal = json.loads(capsys.readouterr().out)["proposal"]
    assert proposal["approved"] is False
    assert run(common + ["save", "--world-id", "harbor", "--create",
                         "--source-json", json.dumps(proposal)]) == 0
    lease = json.loads(capsys.readouterr().out)["localization_digest"]
    assert run(common + ["approve", "--world-id", "harbor",
                         "--expected-digest", lease, "--review-note",
                         "Reviewed original language edition."]) == 0
    approved = json.loads(capsys.readouterr().out)["localization_digest"]
    assert run(common + ["compile", "--world-id", "harbor",
                         "--expected-digest", approved]) == 0
    capsys.readouterr()
    assert run(common + ["verify", "--world-id", "harbor"]) == 0
    capsys.readouterr()
    names = {entry["name"] for entry in manifest()["tools"]}
    assert "world.dialogue_locales_preview" in names
    for name, args in [
        ("world.dialogue_locales_preview", {}),
        ("world.dialogue_locales_propose_preview", {
            "prompt": "Original Norwegian", "tag": "nb-NO",
            "conversation_id": "directions", "node_id": "opening",
            "text": "Følg bryggen?", "response_id": "yes", "label": "Ja.",
        }),
    ]:
        result = invoke_world_tool(str(tmp_path), {
            "schema": "jeeves.world.tool_request.v1",
            "tool": name, "world_id": "harbor", "args": args,
        })
        assert result["persisted"] is False
