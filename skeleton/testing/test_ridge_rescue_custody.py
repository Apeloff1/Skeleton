"""Source-bound replay custody and tampering adversarial tests."""
from copy import deepcopy
from pathlib import Path
import pytest
from skeleton.game.gameplay.ridge_rescue.schema import parse_world
from skeleton.game.gameplay.ridge_rescue.custody import export_run, verify_run, digest, CustodyError

WORLD = parse_world((Path(__file__).resolve().parents[1] / "game/gameplay/ridge_rescue/cinder_ridge.json").read_bytes())

def test_roundtrip_portable_run():
    actions = [{"verb": "move", "direction": "east"}, {"verb": "rescue", "target": "mira"}]
    bundle = export_run(WORLD, actions)
    result = verify_run(bundle)
    assert result["state"]["civilians"]["mira"] == "rescued"
    assert result["actions"] == actions

def test_digest_rejects_mutation():
    bundle = export_run(WORLD, [{"verb": "rest"}])
    bundle["payload"]["state"]["health"] = 999
    with pytest.raises(CustodyError, match="digest"):
        verify_run(bundle)

def test_rehashed_forgery_cannot_forge_unearned_gameplay():
    bundle = export_run(WORLD, [{"verb": "rest"}])
    bundle["payload"]["state"]["status"] = "won:protect"
    bundle["sha256"] = digest(bundle["payload"])
    with pytest.raises(CustodyError, match="replay"):
        verify_run(bundle)

def test_rehashed_action_forgery_rejected():
    bundle = export_run(WORLD, [{"verb": "rest"}])
    bundle["payload"]["actions"] = [{"verb": "evacuate", "choice": "protect"}]
    bundle["sha256"] = digest(bundle["payload"])
    with pytest.raises(CustodyError):
        verify_run(bundle)

def test_unsupported_schema_and_oversize_rejected():
    bundle = export_run(WORLD, [])
    bundle["payload"]["schema"] = "ridge.rescue.run.v0"
    bundle["sha256"] = digest(bundle["payload"])
    with pytest.raises(CustodyError):
        verify_run(bundle)
    with pytest.raises(CustodyError):
        verify_run(b"x" * 256001)

def test_replay_does_not_mutate_source():
    bundle = export_run(WORLD, [{"verb": "rest"}])
    before = deepcopy(bundle)
    verify_run(bundle)
    assert bundle == before
