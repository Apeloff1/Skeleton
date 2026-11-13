"""CLI-level original asset review and real engine manifest handoff."""
import json
import os
from pathlib import Path

import pytest

from skeleton.jeeves.worlds.assets_cli import run as assets_cli
from skeleton.jeeves.worlds.world_canon import WorldStore, propose


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor-anchored custody")
def test_cli_full_asset_authoring_review_compile(tmp_path, capsys):
    root = tmp_path / "private"
    worlds = WorldStore(root)
    source = propose(world_id="harbor", premise="A navigator discovers a beacon.",
                     protagonist="Sora", region="North Harbor",
                     goal="Restore the beacon.")
    worlds.publish(source, create=True)
    assert assets_cli(["--store", str(root), "propose", "--world-id", "harbor",
                       "--id", "hero", "--scene", "opening", "--kind", "sprite",
                       "--description", "An original sailor silhouette",
                       "--alt-text", "Sailor in a blue coat"]) == 0
    proposed = json.loads(capsys.readouterr().out)
    assert proposed["review_required"] is True
    assert assets_cli(["--store", str(root), "compile", "--world-id", "harbor",
                       "--expected-digest", proposed["asset_briefs_digest"],
                       "--era", "eight_bit_tile_1983"]) == 2
    assert json.loads(capsys.readouterr().out)["error"] == "asset_review_required"
    operation = tmp_path / "review.json"
    operation.write_text(json.dumps({"action": "review", "value": {
        "id": "hero", "originality_attested": True,
    }}))
    assert assets_cli(["--store", str(root), "edit", "--world-id", "harbor",
                       "--expected-digest", proposed["asset_briefs_digest"],
                       "--operation-file", str(operation)]) == 0
    reviewed = json.loads(capsys.readouterr().out)
    assert reviewed["asset_briefs_digest"] != proposed["asset_briefs_digest"]
    assert assets_cli(["--store", str(root), "compile", "--world-id", "harbor",
                       "--expected-digest", reviewed["asset_briefs_digest"],
                       "--era", "eight_bit_tile_1983"]) == 0
    compiled = json.loads(capsys.readouterr().out)
    path = root / compiled["compiled_file"]
    assert path.is_file()
    manifest = json.loads(path.read_text())
    assert manifest["engine_manifest"]["asset_count"] == 1
    assert compiled["manifest_sha256"]
    assert len(compiled["manifest_sha256"]) == 64


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor-anchored custody")
def test_cli_rejects_stale_asset_digest(tmp_path, capsys):
    root = tmp_path / "private"
    worlds = WorldStore(root)
    source = propose(world_id="harbor", premise="A navigator discovers a beacon.",
                     protagonist="Sora", region="North Harbor",
                     goal="Restore the beacon.")
    worlds.publish(source, create=True)
    assert assets_cli(["--store", str(root), "propose", "--world-id", "harbor",
                       "--id", "hero", "--scene", "opening", "--kind", "sprite",
                       "--description", "Original sailor silhouette",
                       "--alt-text", "Sailor"]) == 0
    capsys.readouterr()
    assert assets_cli(["--store", str(root), "compile", "--world-id", "harbor",
                       "--expected-digest", "0" * 64,
                       "--era", "eight_bit_tile_1983"]) == 2
    assert json.loads(capsys.readouterr().out)["error"] == "stale_asset_source"


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor-anchored custody")
def test_cli_rejects_invalid_operation_file(tmp_path, capsys):
    root = tmp_path / "private"
    worlds = WorldStore(root)
    source = propose(world_id="harbor", premise="A navigator discovers a beacon.",
                     protagonist="Sora", region="North Harbor",
                     goal="Restore the beacon.")
    worlds.publish(source, create=True)
    assert assets_cli(["--store", str(root), "propose", "--world-id", "harbor",
                       "--id", "hero", "--scene", "opening", "--kind", "sprite",
                       "--description", "Original sailor silhouette",
                       "--alt-text", "Sailor"]) == 0
    proposed = json.loads(capsys.readouterr().out)
    operation = tmp_path / "bad.json"
    operation.write_text('{"action":"review","action":"remove","value":{"id":"hero"}}')
    assert assets_cli(["--store", str(root), "edit", "--world-id", "harbor",
                       "--expected-digest", proposed["asset_briefs_digest"],
                       "--operation-file", str(operation)]) == 2
    assert json.loads(capsys.readouterr().out)["error"] == "duplicate_json_key"
