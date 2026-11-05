"""Canonical source -> actual game -> contracts -> save/replay/CLI acceptance."""
from __future__ import annotations
from copy import deepcopy
from pathlib import Path
import subprocess
import sys
import pytest

from skeleton.game.gameplay.harbor_crafting import (
    HarborError, canonical, decode, demo_actions, digest, export_bundle, load_source,
)
from skeleton.game.gameplay.harbor_crafting_contracts import (
    append_save, build_save, edit_board, next_order, play_save, validate_board,
    verify_edit, verify_save,
)

ROOT = Path(__file__).resolve().parents[1] / "game" / "gameplay" / "fixtures"
CLI = [sys.executable, "-m", "skeleton.game.gameplay.harbor_crafting_cli"]


def inputs():
    world = load_source(ROOT / "harbor_lantern_quay.json")
    board = decode((ROOT / "harbor_lantern_quay_contracts.json").read_bytes())
    return world, board


def games(world):
    a = export_bundle(world, demo_actions(), require_win=True)
    shelter = [{"op": "wait"}] + demo_actions()
    shelter[-1] = {"op": "choose", "choice": "shelter"}
    return a, export_bundle(world, shelter, require_win=True)


def test_real_play_checkpoint_and_portable_replay():
    world, board = inputs()
    first, second = games(world)
    root = build_save(world, board, [])
    assert next_order(root)["order"]["id"] == "beacon_supply"
    partial = append_save(root, first, expected_digest=root["save_digest"])
    assert next_order(partial)["order"]["id"] == "shelter_relief"
    final = append_save(partial, second, expected_digest=partial["save_digest"])
    assert final["complete"] and next_order(final)["status"] == "complete"
    assert verify_save(decode(canonical(final)))["complete"]
    assert canonical(final) == canonical(build_save(world, board, [first, second]))
    with pytest.raises(HarborError, match="stale"):
        append_save(partial, second, expected_digest=root["save_digest"])
    with pytest.raises(HarborError, match="already complete"):
        append_save(final, first, expected_digest=final["save_digest"])


def test_play_is_actual_canonical_gameplay_not_claimed_score():
    world, board = inputs()
    root = build_save(world, board, [])
    partial = play_save(root, demo_actions(), expected_digest=root["save_digest"])
    with pytest.raises(HarborError, match="consequence"):
        play_save(partial, demo_actions(), expected_digest=partial["save_digest"])
    shelter = [{"op": "wait"}] + demo_actions()
    shelter[-1] = {"op": "choose", "choice": "shelter"}
    assert play_save(partial, shelter, expected_digest=partial["save_digest"])["complete"]


@pytest.mark.parametrize("field,value", [
    ("deadline", 17), ("ending", "shelter"), ("min_gathers", 4),
    ("min_crafts", 3), ("max_waits", -1), ("min_coins", 65),
])
def test_contract_constraints_fail_closed(field, value):
    world, board = inputs()
    mutated = deepcopy(board)
    if field in ("deadline", "ending"):
        mutated["orders"][0][field] = value
    else:
        mutated["orders"][0]["rules"][field] = value
    if field in ("max_waits", "min_coins"):
        with pytest.raises(HarborError):
            validate_board(mutated, world)
    else:
        with pytest.raises(HarborError):
            build_save(world, mutated, [games(world)[0]])


def test_duplicate_foreign_and_resealed_replay_rejected():
    world, board = inputs()
    first, second = games(world)
    bad = deepcopy(board)
    bad["orders"][1]["id"] = bad["orders"][0]["id"]
    with pytest.raises(HarborError, match="duplicate"):
        validate_board(bad, world)
    with pytest.raises(HarborError, match="duplicate contract replay"):
        build_save(world, board, [first, first])
    foreign = deepcopy(world)
    foreign["initial_coins"] += 1
    with pytest.raises(HarborError, match="source mismatch"):
        build_save(world, board, [export_bundle(foreign, demo_actions(), require_win=True)])
    final = build_save(world, board, [first, second])
    final["results"][0]["coins"] = 999
    final["save_digest"] = digest({k: v for k, v in final.items() if k != "save_digest"})
    with pytest.raises(HarborError, match="replay verification"):
        verify_save(final)


def test_transactional_contract_authoring_and_resealed_forgery():
    world, board = inputs()
    edits = [{"id": "beacon_supply", "field": "deadline", "value": 25}]
    rev = edit_board(world, board, edits, expected_source_digest=digest(world),
                     expected_board_digest=digest(board))
    assert verify_edit(decode(canonical(rev)))["orders"] == 2
    with pytest.raises(HarborError, match="stale"):
        edit_board(world, board, edits, expected_source_digest="0"*64,
                   expected_board_digest=digest(board))
    rev["after"]["orders"][0]["deadline"] = 24
    rev["revision_digest"] = digest({k: v for k, v in rev.items() if k != "revision_digest"})
    with pytest.raises(HarborError, match="replay"):
        verify_edit(rev)


def test_cli_play_and_verify_and_editor(tmp_path):
    world, board = inputs()
    board_file = tmp_path / "board.json"
    board_file.write_bytes(canonical(board))
    def call(*args):
        proc = subprocess.run(CLI + list(args), capture_output=True, check=False)
        assert proc.returncode == 0, proc.stderr.decode()
        return decode(proc.stdout)
    root = call("contract-init", "--contracts", str(board_file))
    save_file = tmp_path / "save.json"
    save_file.write_bytes(canonical(root))
    actions_file = tmp_path / "actions.json"
    actions_file.write_bytes(canonical(demo_actions()))
    first = call("contract-play", "--contract-save", str(save_file),
                 "--actions", str(actions_file), "--expected-contract-digest", root["save_digest"])
    save_file.write_bytes(canonical(first))
    assert call("contract-next", "--contract-save", str(save_file))["order"]["id"] == "shelter_relief"
    shelter = [{"op": "wait"}] + demo_actions()
    shelter[-1] = {"op": "choose", "choice": "shelter"}
    actions_file.write_bytes(canonical(shelter))
    final = call("contract-play", "--contract-save", str(save_file),
                 "--actions", str(actions_file), "--expected-contract-digest", first["save_digest"])
    save_file.write_bytes(canonical(final))
    assert call("contract-verify", "--contract-save", str(save_file))["complete"]
    edits_file = tmp_path / "edits.json"
    edits_file.write_bytes(canonical([{"id": "beacon_supply", "field": "deadline", "value": 25}]))
    revision = call("contract-author", "--contracts", str(board_file), "--contract-edits", str(edits_file),
                    "--expected-source-digest", digest(world), "--expected-contract-digest", digest(board))
    revision_file = tmp_path / "revision.json"
    revision_file.write_bytes(canonical(revision))
    assert call("contract-verify-author", "--contract-revision", str(revision_file))["verified"]

def test_terminal_contract_play_reaches_real_earned_save():
    from io import StringIO
    from skeleton.game.gameplay.harbor_crafting_ui import play_live, scripted_demo_commands
    world, board = inputs()
    root = build_save(world, board, [])
    output = StringIO()
    assert play_live(world, StringIO(scripted_demo_commands()), output, contract_save=root) == 0
    text = output.getvalue()
    assert "CONTRACT_EARNED beacon_supply" in text
    line = next(line for line in text.splitlines() if line.startswith("CONTRACT_SAVE "))
    advanced = decode(line[len("CONTRACT_SAVE "):].encode())
    assert verify_save(advanced)["next_order"] == 1
    assert advanced["results"][0]["ending"] == "beacon"


def test_terminal_contract_rejects_wrong_earned_consequence():
    from io import StringIO
    from skeleton.game.gameplay.harbor_crafting_ui import play_live, scripted_demo_commands
    world, board = inputs()
    first = build_save(world, board, [games(world)[0]])
    output = StringIO()
    assert play_live(world, StringIO(scripted_demo_commands()), output, contract_save=first) == 2
    assert "CONTRACT_REJECTED" in output.getvalue()
    assert "CONTRACT_SAVE " not in output.getvalue()


def test_terminal_contract_cli_and_stale_lease(tmp_path):
    from skeleton.game.gameplay.harbor_crafting_ui import scripted_demo_commands
    world, board = inputs()
    root = build_save(world, board, [])
    path = tmp_path / "contract-save.json"
    path.write_bytes(canonical(root))
    ok = subprocess.run(
        CLI + ["contract-live", "--contract-save", str(path),
               "--expected-contract-digest", root["save_digest"]],
        input=scripted_demo_commands().encode(), capture_output=True, check=False,
    )
    assert ok.returncode == 0, ok.stderr.decode()
    assert b"CONTRACT_EARNED beacon_supply" in ok.stdout
    stale = subprocess.run(
        CLI + ["contract-live", "--contract-save", str(path),
               "--expected-contract-digest", "0" * 64],
        input=scripted_demo_commands().encode(), capture_output=True, check=False,
    )
    assert stale.returncode == 2 and stale.stdout == b""
