"""Nine-source reviewed Studio assembly to actual typed engine recipes."""
from __future__ import annotations

import json
import pytest

from skeleton.jeeves.worlds.asset_briefs import (
    ASSET_SCHEMA, AssetBriefStore, edit_briefs, propose_asset,
)
from skeleton.jeeves.worlds.studio_engine import StudioEngineStore
from skeleton.jeeves.worlds.studio_engine_cli import run
from skeleton.jeeves.worlds.timeline import TimelineStore, propose_timeline
from skeleton.jeeves.worlds.tools import invoke_world_tool, manifest
from skeleton.jeeves.worlds.world_canon import CanonError, digest
from skeleton.testing.test_jeeves_world_studio_assembly import fixture as studio_fixture

ERA = "eight_bit_tile_1983"


def fixture(tmp_path):
    studio = studio_fixture(tmp_path)
    world = studio.worlds.read("harbor")
    asset = propose_asset(
        world, asset_id="beacon", scene="opening", kind="sprite",
        description="Original harbor beacon sprite", alt_text="Beacon over water")
    data = {"schema": ASSET_SCHEMA, "world_id": "harbor",
            "world_digest": digest(world), "assets": [asset]}
    reviewed = edit_briefs(data, world, {"action": "review", "value": {
        "id": "beacon", "originality_attested": True}})
    AssetBriefStore(tmp_path).publish("harbor", reviewed, create=True)
    timeline = propose_timeline(
        world, actor="mara", opening_note="The beacon dims.",
        resolution_note="The beacon shines again.")
    TimelineStore(tmp_path).publish("harbor", timeline, create=True)
    return StudioEngineStore(tmp_path)


def reject(code, fn):
    with pytest.raises(CanonError) as exc:
        fn()
    assert exc.value.code == code


def test_actual_engine_handoff_receipt_and_tamper(tmp_path):
    store = fixture(tmp_path)
    info = store.inspect("harbor", ERA)
    receipt = store.compile("harbor", info["source_digests"], ERA)
    assert store.verify("harbor") == receipt
    path = tmp_path / receipt["manifest_file"]
    manifest = json.loads(path.read_text())
    assert manifest["engine_assets"]["engine_manifest"]["asset_count"] == 1
    assert manifest["temporal_events"]["events"][0]["kind"] == "setup"
    assert len(manifest["scene_nodes"]) == 3
    assert manifest["choice_edges"][0]["accessible_action"]
    assert manifest["studio_proof_digests"]["cross_plane"]
    assert manifest["source_digests"]["assets"] == info["source_digests"]["assets"]
    path.write_bytes(path.read_bytes() + b" ")
    reject("studio_engine_manifest_mismatch", lambda: store.verify("harbor"))


def test_invalid_era_and_stale_source_fail_closed(tmp_path):
    store = fixture(tmp_path)
    info = store.inspect("harbor", ERA)
    stale = dict(info["source_digests"])
    stale["assets"] = "0" * 64
    reject("studio_engine_stale_source", lambda: store.compile("harbor", stale, ERA))
    reject("engine_asset_compile_rejected",
           lambda: store.compile("harbor", info["source_digests"], "pong_discrete_1972"))
    assert not (tmp_path / "harbor.studio.engine.receipt.json").exists()


def test_operator_cli_and_readonly_jeeves_preview(tmp_path, capsys):
    store = fixture(tmp_path)
    assert run(["--store", str(tmp_path), "inspect",
                "--world-id", "harbor", "--era", ERA]) == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True
    names = {item["name"] for item in manifest()["tools"]}
    assert "world.studio_engine_preview" in names
    response = invoke_world_tool(str(tmp_path), {
        "schema": "jeeves.world.tool_request.v1",
        "tool": "world.studio_engine_preview", "world_id": "harbor",
        "args": {"era": ERA},
    })
    assert response["persisted"] is False
    assert response["result_digest"] == digest(response["result"])
