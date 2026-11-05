"""Mission board must not grant rewards or trust forged replay hints."""
from __future__ import annotations

import copy
import json

import pytest

from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.scene_mission import (
    demo_actions, new_mission, original_mission, simulate_mission,
)
from skeleton.game.gameplay.scene_mission_board import (
    cli, export_board, import_board, inspect_board, verify_board,
)
from skeleton.game.gameplay.scene_travel import SceneTravelError


def test_start_board_shows_only_replay_derived_progress_and_legal_moves():
    session = new_mission(original_mission())
    board = inspect_board(session)
    assert board["missions_earned"] == []
    assert board["reputation"] == 0
    assert board["scene_id"] == "quay"
    assert board["receipt"] == dig({k: v for k, v in board.items() if k != "receipt"})
    assert any(action["kind"] == "choose" for action in board["available_actions"])
    assert not any(action["kind"] == "finish" for action in board["available_actions"])
    assert verify_board(copy.deepcopy(board), session=session) == board


def test_objectives_are_earned_only_by_real_mission_actions():
    source = original_mission()
    initial = inspect_board(new_mission(source))
    pledge = next(x for x in initial["objectives"] if x["id"] == "pledge")
    assert pledge["status"] == "available"
    played = simulate_mission(source, demo_actions()[:1])
    board = inspect_board(played)
    assert "pledge" in board["missions_earned"]
    assert next(x for x in board["objectives"] if x["id"] == "pledge")["status"] == "earned"
    assert board["reputation"] == 3


def test_terminal_board_has_no_actions_and_portable_roundtrip():
    session = simulate_mission(original_mission(), demo_actions())
    board = inspect_board(session)
    assert board["phase"] == "finished"
    assert board["ending"] == "lantern_restored"
    assert board["available_actions"] == []
    bundle = export_board(session)
    assert import_board(json.loads(json.dumps(bundle))) == board


@pytest.mark.parametrize("field", [
    "state_digest", "source_digest", "reputation", "available_actions", "receipt",
])
def test_forged_board_rejected_even_if_receipt_recomputed(field):
    session = new_mission(original_mission())
    bad = copy.deepcopy(inspect_board(session))
    if field in ("state_digest", "source_digest", "receipt"):
        bad[field] = "0" * 64
    elif field == "reputation":
        bad[field] = 900
    else:
        bad[field] = [{"kind": "finish", "ending_id": "lantern_restored"}]
    if field != "receipt":
        bad["receipt"] = dig({k: v for k, v in bad.items() if k != "receipt"})
    with pytest.raises(SceneTravelError):
        verify_board(bad, session=session)


def test_bundle_rejects_tampered_saved_reputation_with_new_checksum():
    bundle = export_board(new_mission(original_mission()))
    bundle["session"]["state"]["reputation"] = 900
    bundle["checksum"] = dig({k: v for k, v in bundle.items() if k != "checksum"})
    with pytest.raises(SceneTravelError):
        import_board(bundle)


def test_cli_is_reachable_from_main_and_roundtrips_bundle(capsys):
    from skeleton.__main__ import main
    assert main(["scene-mission-board", "--demo", "--export"]) == 0
    bundle = json.loads(capsys.readouterr().out)
    assert cli(["--bundle-json", json.dumps(bundle)]) == 0
    board = json.loads(capsys.readouterr().out)
    assert board["source_digest"] == bundle["source_digest"]


def test_invalid_json_and_bad_bundle_rejected(capsys):
    assert cli(["--source-json", '{"a":1,"a":2}']) == 2
    assert json.loads(capsys.readouterr().err)["ok"] is False
    assert cli(["--bundle-json", "{}"]) == 2
    assert json.loads(capsys.readouterr().err)["ok"] is False
