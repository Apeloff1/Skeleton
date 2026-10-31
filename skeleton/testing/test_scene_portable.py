"""Portable source-bound scene export, recovery and tamper rejection."""
from __future__ import annotations

import copy
import json

import pytest

from skeleton.game.gameplay.offline_portable import MAX_PORTABLE_BYTES
from skeleton.game.gameplay.scene_portable import (
    export_scene_bundle, import_scene_bundle,
)
from skeleton.game.gameplay.scene_travel import (
    SceneTravelError, cli, original_demo, resume_session, simulate,
)


def _saved():
    world, actions = original_demo()
    return simulate(world, actions[:2])


def test_scene_bundle_roundtrip_then_resume_equals_original_victory():
    saved = _saved()
    bundle = export_scene_bundle(saved)
    assert bundle == export_scene_bundle(copy.deepcopy(saved))
    restored = import_scene_bundle(json.loads(json.dumps(bundle)))
    assert restored == saved
    result = resume_session(restored, [{"kind": "travel", "exit_id": "inside"}])
    world, actions = original_demo()
    assert result == simulate(world, actions)
    assert result["state"]["phase"] == "won"


@pytest.mark.parametrize("mutate", [
    lambda b: b.update(checksum="0" * 64),
    lambda b: b.update(schema_version="future"),
    lambda b: b.update(kind="different_game"),
    lambda b: b.update(source_digest="0" * 64),
    lambda b: b.update(state_digest="0" * 64),
    lambda b: b.update(extra="untrusted"),
    lambda b: b["session"]["state"].update(inventory=["unearned_key"]),
    lambda b: b["session"]["journal"][0].update(receipt="0" * 64),
])
def test_scene_bundle_tampering_rejected(mutate):
    bundle = export_scene_bundle(_saved())
    mutate(bundle)
    with pytest.raises(SceneTravelError):
        import_scene_bundle(bundle)


def test_recomputed_checksum_cannot_bypass_canonical_scene_replay():
    from skeleton.game.gameplay.flgb_gameplay_runtime import dig
    bundle = export_scene_bundle(_saved())
    bundle["session"]["state"]["inventory"] = ["unearned_key"]
    bundle["checksum"] = dig({k: v for k, v in bundle.items() if k != "checksum"})
    with pytest.raises(SceneTravelError, match="replay"):
        import_scene_bundle(bundle)


def test_portable_size_and_malformed_data_fail_closed():
    bundle = export_scene_bundle(_saved())
    bundle["padding"] = "x" * MAX_PORTABLE_BYTES
    with pytest.raises(SceneTravelError, match="size budget"):
        import_scene_bundle(bundle)
    with pytest.raises(SceneTravelError):
        import_scene_bundle(["untrusted"])
    with pytest.raises(SceneTravelError):
        export_scene_bundle({"not": "a real save"})


def test_cli_export_import_source_bound_checkpoint(capsys):
    saved = _saved()
    assert cli(["export", "--session-json", json.dumps(saved)]) == 0
    bundle = json.loads(capsys.readouterr().out)
    assert cli(["import", "--bundle-json", json.dumps(bundle)]) == 0
    assert json.loads(capsys.readouterr().out) == saved
    bundle["checksum"] = "0" * 64
    assert cli(["import", "--bundle-json", json.dumps(bundle)]) == 2
    assert json.loads(capsys.readouterr().err)["ok"] is False


def test_installed_cli_portable_roundtrip(capsys):
    from skeleton.__main__ import main
    saved = _saved()
    assert main(["scene-travel", "export", "--session-json", json.dumps(saved)]) == 0
    bundle = json.loads(capsys.readouterr().out)
    assert main(["scene-travel", "import", "--bundle-json", json.dumps(bundle)]) == 0
    assert json.loads(capsys.readouterr().out) == saved
