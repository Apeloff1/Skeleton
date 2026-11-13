"""Portable offline expedition export/import integrity and size bounds."""
from __future__ import annotations

import copy
import json
import pytest

from skeleton.game.gameplay.turn_combat import CombatSessionError
from skeleton.game.gameplay.arena_bundle import (
    MAX_BUNDLE_BYTES, export_bundle, import_bundle,
)
from skeleton.game.gameplay.arena_expedition import (
    cli, original_expedition, simulate_expedition,
)


def saved():
    return simulate_expedition(original_expedition(), [{"kind": "fight"}])


def test_export_import_round_trip_is_deterministic():
    checkpoint = saved()
    bundle = export_bundle(checkpoint)
    assert bundle == export_bundle(copy.deepcopy(checkpoint))
    assert import_bundle(json.loads(json.dumps(bundle))) == checkpoint
    assert bundle["source_digest"] == checkpoint["source_digest"]
    assert bundle["state_digest"] == checkpoint["state_digest"]


@pytest.mark.parametrize("mutate", [
    lambda x: x.update(checksum="0" * 64),
    lambda x: x.update(schema_version="future"),
    lambda x: x.update(kind="untrusted"),
    lambda x: x.update(source_digest="f" * 64),
    lambda x: x["session"]["state"].update(currency=999),
    lambda x: x.update(extra="forged"),
])
def test_tampered_bundle_rejected(mutate):
    bundle = export_bundle(saved())
    mutate(bundle)
    with pytest.raises(CombatSessionError):
        import_bundle(bundle)


def test_checksum_recalculation_cannot_bypass_nested_replay():
    from skeleton.game.gameplay.flgb_gameplay_runtime import dig
    bundle = export_bundle(saved())
    bundle["session"]["state"]["currency"] = 500
    bundle["checksum"] = dig({k: v for k, v in bundle.items() if k != "checksum"})
    with pytest.raises(CombatSessionError, match="replay|mismatch"):
        import_bundle(bundle)


def test_oversized_portable_bundle_fails_closed():
    bundle = export_bundle(saved())
    bundle["padding"] = "x" * MAX_BUNDLE_BYTES
    with pytest.raises(CombatSessionError, match="size budget"):
        import_bundle(bundle)


def test_cli_export_and_import_reaches_same_checkpoint(capsys):
    checkpoint = saved()
    assert cli(["export", "--session-json", json.dumps(checkpoint)]) == 0
    bundle = json.loads(capsys.readouterr().out)
    assert cli(["import", "--bundle-json", json.dumps(bundle)]) == 0
    assert json.loads(capsys.readouterr().out) == checkpoint
