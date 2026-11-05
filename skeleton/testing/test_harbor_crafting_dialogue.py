"""NPC dialogue, actual patrol reachability, earned delivery and portable replay."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import subprocess
import sys

import pytest

from skeleton.game.gameplay.harbor_crafting import (
    HarborError, canonical, decode, demo_actions, digest, load_source,
)
from skeleton.game.gameplay.harbor_crafting_dialogue import (
    build_dialogue_game, resume_dialogue_game, validate_dialogue_board,
    verify_dialogue_game,
)
from skeleton.game.gameplay.harbor_crafting_dialogue_authoring import (
    edit_dialogue, verify_dialogue_edit,
)

FIXTURES = Path(__file__).resolve().parents[1] / "game" / "gameplay" / "fixtures"
CLI = [sys.executable, "-m", "skeleton.game.gameplay.harbor_crafting_cli"]


def source_board():
    source = load_source(FIXTURES / "harbor_lantern_quay.json")
    board = decode((FIXTURES / "harbor_lantern_quay_dialogue.json").read_bytes())
    return source, board


def earned_actions():
    base = demo_actions()
    return base[:16] + [
        {"op": "wait"},
        {"op": "talk", "node": "merchant_intro", "choice": "permit"},
    ] + base[16:]


def test_real_npc_talk_earns_delivery_permit_and_ending():
    source, board = source_board()
    report = build_dialogue_game(source, board, earned_actions(), require_win=True)
    assert report["bundle"]["state"]["ending"] == "beacon"
    assert report["flags"] == ["dock_pass"] and report["trust"] == 2
    assert report["spoken_nodes"] == ["merchant_intro"]
    talk = report["events"][17]
    assert talk["action"]["op"] == "talk"
    assert talk["canonical_action"] == {"op": "wait"}
    assert talk["npc_position"] == [4, 2]
    assert verify_dialogue_game(decode(canonical(report)), require_win=True)["trust"] == 2


def test_delivery_without_permit_and_talk_out_of_range_fail_closed():
    source, board = source_board()
    with pytest.raises(HarborError, match="permit"):
        build_dialogue_game(source, board, demo_actions())
    with pytest.raises(HarborError, match="out of reach"):
        build_dialogue_game(source, board, [
            {"op": "talk", "node": "merchant_intro", "choice": "permit"},
        ])
    declined = demo_actions()[:16] + [
        {"op": "wait"}, {"op": "talk", "node": "merchant_intro", "choice": "decline"},
    ] + demo_actions()[16:]
    with pytest.raises(HarborError, match="permit"):
        build_dialogue_game(source, board, declined)


def test_cas_checkpoint_continuation_preserves_real_world_ticks():
    source, board = source_board()
    actions = earned_actions()
    partial = build_dialogue_game(source, board, actions[:17])
    advanced = resume_dialogue_game(partial, actions[17:],
                                    expected_digest=partial["report_digest"], require_win=True)
    assert advanced == build_dialogue_game(source, board, actions, require_win=True)
    with pytest.raises(HarborError, match="stale"):
        resume_dialogue_game(partial, actions[17:], expected_digest="0"*64)
    with pytest.raises(HarborError, match="already complete"):
        resume_dialogue_game(advanced, [], expected_digest=advanced["report_digest"])


def test_resealed_choice_and_trust_forgery_rejected():
    source, board = source_board()
    original = build_dialogue_game(source, board, earned_actions())
    for key, replacement in (
        ("trust", 20), ("flags", ["dock_pass", "rescue_volunteer"]),
        ("spoken_nodes", []), ("events", original["events"][:-1]),
    ):
        forged = deepcopy(original)
        forged[key] = replacement
        forged["report_digest"] = digest({k: v for k, v in forged.items() if k != "report_digest"})
        with pytest.raises(HarborError, match="replay"):
            verify_dialogue_game(forged)
    bad = deepcopy(original)
    bad["input_actions"][17]["choice"] = "decline"
    bad["report_digest"] = digest({k: v for k, v in bad.items() if k != "report_digest"})
    with pytest.raises(HarborError):
        verify_dialogue_game(bad)


def test_invalid_dialogue_graph_and_repeated_conversation():
    source, board = source_board()
    for invalid in (
        {**board, "speaker": "foreign_npc"},
        {**board, "required_flag_for_delivery": "unobtainable"},
        {**board, "nodes": board["nodes"] + [board["nodes"][0]]},
        {**board, "nodes": [{**board["nodes"][0], "requires": ["unknown"]}]},
        {**board, "nodes": [{**board["nodes"][0], "min_trust": True}]},
    ):
        with pytest.raises(HarborError):
            validate_dialogue_board(invalid, source)
    duplicate = earned_actions()[:18] + [
        {"op": "wait"}, {"op": "talk", "node": "merchant_intro", "choice": "permit"},
    ]
    with pytest.raises(HarborError, match="already spoken"):
        build_dialogue_game(source, board, duplicate)


def test_editor_preview_replays_earned_choices_and_refuses_resealed_change():
    source, board = source_board()
    report = build_dialogue_game(source, board, earned_actions(), require_win=True)
    edits = [{"node": "merchant_intro", "choice": "permit",
              "field": "trust_delta", "value": 1}]
    revision = edit_dialogue(
        source, board, edits, expected_source_digest=digest(source),
        expected_board_digest=digest(board), preview_report=report,
    )
    assert revision["preview"]["before_trust"] == 2
    assert revision["preview"]["after_trust"] == 1
    assert verify_dialogue_edit(decode(canonical(revision)))["nodes"] == 2
    with pytest.raises(HarborError, match="stale"):
        edit_dialogue(source, board, edits, expected_source_digest="0"*64,
                      expected_board_digest=digest(board))
    forged = deepcopy(revision)
    forged["after"]["nodes"][0]["choices"][0]["trust_delta"] = 5
    forged["after_digest"] = digest(forged["after"])
    forged["revision_digest"] = digest({k: v for k, v in forged.items() if k != "revision_digest"})
    with pytest.raises(HarborError, match="replay"):
        verify_dialogue_edit(forged)


def test_cli_actual_dialogue_gameplay_replay_and_editor(tmp_path):
    source, board = source_board()
    board_file = tmp_path / "dialogue-board.json"
    board_file.write_bytes(canonical(board))
    actions_file = tmp_path / "actions.json"
    actions_file.write_bytes(canonical(earned_actions()[:17]))

    def call(*args):
        process = subprocess.run(CLI + list(args), capture_output=True, check=False)
        assert process.returncode == 0, process.stderr.decode()
        return decode(process.stdout)

    partial = call("dialogue-run", "--dialogue-board", str(board_file),
                   "--actions", str(actions_file))
    report_file = tmp_path / "report.json"
    report_file.write_bytes(canonical(partial))
    assert call("dialogue-verify", "--dialogue-report", str(report_file))["verified"]
    actions_file.write_bytes(canonical(earned_actions()[17:]))
    final = call("dialogue-resume", "--dialogue-report", str(report_file),
                 "--actions", str(actions_file), "--expected-dialogue-digest",
                 partial["report_digest"], "--require-win")
    assert final["bundle"]["state"]["ending"] == "beacon"
    edits_file = tmp_path / "edits.json"
    edits_file.write_bytes(canonical([{"node": "merchant_intro", "choice": "permit",
                                     "field": "trust_delta", "value": 1}]))
    report_file.write_bytes(canonical(final))
    revision = call("dialogue-author", "--dialogue-board", str(board_file),
                    "--dialogue-edits", str(edits_file), "--dialogue-report", str(report_file),
                    "--expected-source-digest", digest(source),
                    "--expected-dialogue-board-digest", digest(board))
    revision_file = tmp_path / "revision.json"
    revision_file.write_bytes(canonical(revision))
    assert call("dialogue-verify-author", "--dialogue-revision", str(revision_file))["verified"]
    denied = subprocess.run(
        CLI + ["dialogue-resume", "--dialogue-report", str(report_file),
               "--actions", str(actions_file), "--expected-dialogue-digest", "0"*64],
        capture_output=True, check=False,
    )
    assert denied.returncode == 2 and not denied.stdout


def test_circular_prerequisites_and_unreachable_trust_are_denied():
    source, board = source_board()
    circular = deepcopy(board)
    circular["nodes"][0]["requires"] = ["dock_pass"]
    with pytest.raises(HarborError, match="unreachable"):
        validate_dialogue_board(circular, source)
    impossible = deepcopy(board)
    impossible["nodes"][0]["min_trust"] = 10
    with pytest.raises(HarborError, match="unreachable"):
        validate_dialogue_board(impossible, source)
    malformed = deepcopy(board)
    malformed["nodes"][0]["requires"] = [["dock_pass"]]
    with pytest.raises(HarborError, match="invalid dialogue prerequisites"):
        validate_dialogue_board(malformed, source)
