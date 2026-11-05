"""Operator interaction CLI and read-only Jeeves tool surface."""
from __future__ import annotations

import json
import os
import pytest

from skeleton.jeeves.worlds.cast import CastStore
from skeleton.jeeves.worlds.character_arcs import ArcStore
from skeleton.jeeves.worlds.dialogue_graph import DialogueStore
from skeleton.jeeves.worlds.economy import EconomyStore
from skeleton.jeeves.worlds.interaction_assembly_cli import run
from skeleton.jeeves.worlds.tools import invoke_world_tool, manifest
from skeleton.jeeves.worlds.world_canon import WorldStore
from skeleton.testing.test_jeeves_world_interaction_core import fixture


@pytest.mark.skipif(os.name != "posix", reason="descriptor-anchored custody")
def test_cli_and_read_only_preview(tmp_path, capsys):
    world, cast, economy, arcs, dialogue = fixture()
    WorldStore(tmp_path).publish(world, create=True)
    CastStore(tmp_path).publish("harbor", cast, create=True)
    for store, source in [
        (EconomyStore(tmp_path), economy),
        (ArcStore(tmp_path), arcs),
        (DialogueStore(tmp_path), dialogue),
    ]:
        draft = {**source, "approved": False, "review_note": ""}
        lease = store.publish("harbor", draft, create=True)
        store.approve("harbor", lease, "Reviewed original source.")
    common = ["--store", str(tmp_path), "inspect", "--world-id", "harbor"]
    assert run(common) == 0
    proof = json.loads(capsys.readouterr().out)["proof"]
    assert run(["--store", str(tmp_path), "compile", "--world-id", "harbor",
                "--expected-digests-json",
                json.dumps(proof["source_digests"])]) == 0
    capsys.readouterr()
    assert run(["--store", str(tmp_path), "verify",
                "--world-id", "harbor"]) == 0
    capsys.readouterr()
    assert "world.interaction_preview" in {
        item["name"] for item in manifest()["tools"]}
    result = invoke_world_tool(str(tmp_path), {
        "schema": "jeeves.world.tool_request.v1",
        "tool": "world.interaction_preview", "world_id": "harbor",
        "args": {},
    })
    assert result["persisted"] is False
    assert result["result"]["proof"]["dialogue_handoff_witnesses"] == {
        "directions:pursue_goal": []}
