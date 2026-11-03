"""CLI and read-only Jeeves world economy tool contract."""
from __future__ import annotations

import json
import os
import pytest

from skeleton.jeeves.worlds.economy_cli import run
from skeleton.jeeves.worlds.tools import invoke_world_tool, manifest
from skeleton.jeeves.worlds.world_canon import WorldStore, propose


@pytest.mark.skipif(os.name != "posix", reason="descriptor-anchored custody")
def test_full_cli_and_typed_tools(tmp_path, capsys):
    world = propose(world_id="harbor", premise="Original expedition.",
                    protagonist="Ari", region="Harbor", goal="Reach shore.")
    WorldStore(tmp_path).publish(world, create=True)
    common = ["--store", str(tmp_path)]
    assert run(common + [
        "propose", "--world-id", "harbor", "--prompt", "Original rations",
        "--resource-id", "rations", "--name", "Rations",
        "--initial", "1", "--capacity", "5", "--choice-id", "pursue_goal",
        "--cost", "1", "--gain", "0",
    ]) == 0
    source = json.loads(capsys.readouterr().out)["proposal"]
    assert source["approved"] is False
    assert run(common + ["save", "--world-id", "harbor", "--create",
                         "--source-json", json.dumps(source)]) == 0
    lease = json.loads(capsys.readouterr().out)["economy_digest"]
    assert run(common + ["approve", "--world-id", "harbor",
                         "--expected-digest", lease, "--review-note",
                         "Reviewed original source."]) == 0
    approved = json.loads(capsys.readouterr().out)["economy_digest"]
    assert run(common + ["compile", "--world-id", "harbor",
                         "--expected-digest", approved]) == 0
    capsys.readouterr()
    assert run(common + ["verify", "--world-id", "harbor"]) == 0
    capsys.readouterr()
    assert run(common + ["inspect", "--world-id", "harbor"]) == 0
    assert json.loads(capsys.readouterr().out)["economy"]["approved"] is True
    assert run(common + ["edit", "--world-id", "harbor",
                         "--expected-digest", "0" * 64, "--operation-json",
                         json.dumps({"action": "remove_effect",
                                     "value": {"choice": "pursue_goal"}})]) == 2
    assert json.loads(capsys.readouterr().out)["error"] == "economy_stale_edit"
    names = {tool["name"] for tool in manifest()["tools"]}
    assert "world.economy_preview" in names
    assert "world.economy_propose_preview" in names
    for name, args in [
        ("world.economy_preview", {}),
        ("world.economy_propose_preview", {
            "prompt": "Original supplies", "resource_id": "rations",
            "name": "Rations", "initial": 1, "capacity": 5,
            "choice_id": "pursue_goal", "cost": 1, "gain": 0,
        }),
    ]:
        response = invoke_world_tool(str(tmp_path), {
            "schema": "jeeves.world.tool_request.v1",
            "tool": name, "world_id": "harbor", "args": args,
        })
        assert response["persisted"] is False
        assert response["world_digest"]
        assert response["result_digest"]
