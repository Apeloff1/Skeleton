"""End-to-end original convoy: source -> player movement -> combat -> replay -> edit."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import subprocess
import sys

import pytest

from skeleton.game.gameplay.harbor_crafting import (
    HarborError, canonical, decode, demo_actions, digest, load_source,
)
from skeleton.game.gameplay.harbor_crafting_convoy import (
    build_convoy, convoy_status, resume_convoy, validate_convoy_board,
    verify_convoy,
)
from skeleton.game.gameplay.harbor_crafting_convoy_authoring import (
    edit_convoy_board, verify_convoy_revision,
)
from skeleton.game.gameplay.harbor_crafting_convoy_ui import play_convoy_live

FIXTURES = Path(__file__).resolve().parents[1] / "game" / "gameplay" / "fixtures"
CLI = [sys.executable, "-m", "skeleton.game.gameplay.harbor_crafting_cli"]


def source_board():
    source = load_source(FIXTURES / "harbor_lantern_quay.json")
    board = decode((FIXTURES / "harbor_lantern_quay_convoy.json").read_bytes())
    return source, board


def winning_actions():
    return demo_actions()[:12] + [
        {"op": "escort"},
        {"op": "move", "direction": "east"},
        {"op": "escort"},
        {"op": "strike"},
        {"op": "move", "direction": "east"},
        {"op": "escort"},
        {"op": "move", "direction": "east"},
        {"op": "escort"},
    ]


def test_real_crafting_escort_encounter_and_earned_dock_victory():
    source, board = source_board()
    report = build_convoy(source, board, winning_actions(), require_complete=True)
    status = verify_convoy(decode(canonical(report)), require_complete=True)
    assert status["complete"] and not status["failed"]
    assert status["hull"] == 3 and status["bounty"] == 7
    assert status["waypoint"] == 4 and status["tick"] == 20
    assert report["state"]["spent"] == 1
    assert report["bundle"]["state"]["inventory"]["lantern"] == 1
    assert convoy_status(report)["position"] == source["dock"]
    assert report["events"][-1]["previous"] == report["events"][-2]["digest"]


def test_weapon_charge_is_earned_not_invented_or_reusable():
    source, board = source_board()
    actions = [a for a in winning_actions() if a != {"op": "craft", "recipe": "lantern"}]
    with pytest.raises(HarborError, match="weapon charge"):
        build_convoy(source, board, actions)
    duplicate = deepcopy(board)
    duplicate["encounters"].append({
        "id": "dock_raider", "at_index": 3, "strength": 1, "reward": 1
    })
    actions = winning_actions()
    actions.insert(-2, {"op": "strike"})
    with pytest.raises(HarborError, match="weapon charge"):
        build_convoy(source, duplicate, actions)


def test_encounter_defeat_and_guard_are_real_deterministic_states():
    source, board = source_board()
    prefix = winning_actions()[:15]
    lost = build_convoy(source, board, prefix + [{"op": "wait"}] * 3)
    assert lost["state"]["failed"] and lost["state"]["hull"] == 0
    assert verify_convoy(lost)["failed"]
    with pytest.raises(HarborError, match="not earned"):
        verify_convoy(lost, require_complete=True)
    guarded = build_convoy(
        source, board, prefix + [{"op": "guard"}] + winning_actions()[15:],
        require_complete=True,
    )
    assert guarded["state"]["hull"] == 3
    assert verify_convoy(guarded)["complete"]


def test_collision_out_of_range_and_illegal_combat_fail_closed():
    source, board = source_board()
    with pytest.raises(HarborError, match="collided"):
        build_convoy(source, board, demo_actions()[:12] + [{"op": "move", "direction": "east"}])
    with pytest.raises(HarborError, match="no convoy threat"):
        build_convoy(source, board, [{"op": "strike"}])
    with pytest.raises(HarborError, match="nearby"):
        build_convoy(source, board, [{"op": "escort"}])
    with pytest.raises(HarborError):
        build_convoy(source, board, [{"op": ["escort"]}])


def test_board_validation_rejects_unreachable_and_forged_rules():
    source, board = source_board()
    variants = []
    for field, value in (
        ("source_id", "foreign"), ("hull", True), ("weapon_item", "unobtainable"),
        ("max_turns", 99999), ("route", [[2, 3], [6, 3]]),
        ("encounters", [board["encounters"][0]] * 2),
    ):
        item = deepcopy(board)
        item[field] = value
        variants.append(item)
    for item in variants:
        with pytest.raises(HarborError):
            validate_convoy_board(item, source)


def test_resealed_forgery_and_checkpoint_cas_rejected():
    source, board = source_board()
    actions = winning_actions()
    partial = build_convoy(source, board, actions[:15])
    full = resume_convoy(partial, actions[15:],
                         expected_digest=partial["report_digest"], require_complete=True)
    assert full == build_convoy(source, board, actions, require_complete=True)
    with pytest.raises(HarborError, match="stale"):
        resume_convoy(partial, actions[15:], expected_digest="0" * 64)
    with pytest.raises(HarborError, match="terminal"):
        resume_convoy(full, [{"op": "wait"}], expected_digest=full["report_digest"])
    for key, value in (
        ("bounty", 999), ("hull", 20), ("complete", False),
    ):
        forged = deepcopy(full)
        forged["state"][key] = value
        forged["report_digest"] = digest({
            k: v for k, v in forged.items() if k != "report_digest"
        })
        with pytest.raises(HarborError, match="replay"):
            verify_convoy(forged)


def test_authoring_cas_and_preview_are_replayed_not_trusted():
    source, board = source_board()
    play = build_convoy(source, board, winning_actions(), require_complete=True)
    edits = [{"kind": "encounter-reward", "target": "canal_raider", "value": 11}]
    revision = edit_convoy_board(
        source, board, edits, expected_board_digest=digest(board),
        preview_report=play,
    )
    assert revision["result"]["state"]["bounty"] == 11
    assert verify_convoy_revision(decode(canonical(revision)))["preview_complete"]
    with pytest.raises(HarborError, match="stale"):
        edit_convoy_board(source, board, edits, expected_board_digest="0" * 64)
    forged = deepcopy(revision)
    forged["result"]["state"]["bounty"] = 999
    forged["result"]["report_digest"] = digest({
        k: v for k, v in forged["result"].items() if k != "report_digest"
    })
    forged["revision_digest"] = digest({
        k: v for k, v in forged.items() if k != "revision_digest"
    })
    with pytest.raises(HarborError):
        verify_convoy_revision(forged)


def test_cli_run_verify_resume_status_and_editor(tmp_path):
    source, board = source_board()
    def write(name, value):
        path = tmp_path / (name + ".json")
        path.write_bytes(canonical(value))
        return str(path)
    def call(*args):
        completed = subprocess.run(CLI + list(args), capture_output=True, check=False)
        assert completed.returncode == 0, completed.stderr.decode()
        return decode(completed.stdout)

    source_file = str(FIXTURES / "harbor_lantern_quay.json")
    board_file = str(FIXTURES / "harbor_lantern_quay_convoy.json")
    actions = winning_actions()
    report = call("convoy-run", "--source", source_file,
                  "--convoy-board", board_file, "--actions", write("actions", actions),
                  "--require-all")
    report_file = write("report", report)
    assert call("convoy-verify", "--convoy-report", report_file)["complete"]
    assert call("convoy-status", "--convoy-report", report_file)["position"] == source["dock"]
    partial = build_convoy(source, board, actions[:15])
    resumed = call("convoy-resume", "--convoy-report", write("partial", partial),
                   "--actions", write("continuation", actions[15:]),
                   "--expected-convoy-digest", partial["report_digest"], "--require-all")
    assert resumed == report
    edits = [{"kind": "encounter-reward", "target": "canal_raider", "value": 11}]
    revision = call(
        "convoy-author", "--source", source_file, "--convoy-board", board_file,
        "--convoy-edits", write("edits", edits),
        "--expected-convoy-board-digest", digest(board),
        "--convoy-report", report_file,
    )
    assert call("convoy-verify-author",
                "--convoy-revision", write("revision", revision))["preview_complete"]


def test_live_terminal_recovers_from_bad_command_without_corrupting_save():
    from io import StringIO
    source, board = source_board()
    stream = StringIO("invalid command\n" + "\n".join(
        a["op"] if a["op"] in {"escort", "strike", "guard", "gather", "wait"}
        else a["op"] + " " + a.get("direction", a.get("recipe", a.get("item", "")))
        for a in winning_actions()
    ) + "\n")
    output = StringIO()
    report = play_convoy_live(source, board, instream=stream, outstream=output)
    assert verify_convoy(report, require_complete=True)["complete"]
    assert "Rejected:" in output.getvalue()
