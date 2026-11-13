"""Actual source -> movement -> fog -> CAS save -> replay and editor acceptance."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import subprocess
import sys

import pytest

from skeleton.game.gameplay.harbor_crafting import (
    HarborError, canonical, decode, demo_actions, digest, load_source,
)
from skeleton.game.gameplay.harbor_crafting_survey import (
    build_survey, resume_survey, validate_board, verify_survey,
)
from skeleton.game.gameplay.harbor_crafting_survey_authoring import (
    edit_survey, verify_survey_edit,
)
from skeleton.game.gameplay.harbor_crafting_survey_guidance import (
    survey_hint, verify_survey_hint,
)

FIXTURES = Path(__file__).resolve().parents[1] / "game" / "gameplay" / "fixtures"
CLI = [sys.executable, "-m", "skeleton.game.gameplay.harbor_crafting_cli"]


def source_board():
    world = load_source(FIXTURES / "harbor_lantern_quay.json")
    board = decode((FIXTURES / "harbor_lantern_quay_survey.json").read_bytes())
    return world, board


def test_real_campaign_earns_exploration_without_claimed_scores():
    source, board = source_board()
    result = build_survey(source, board, demo_actions(), require_complete=True)
    assert result["complete"] and result["score"] == 13
    assert result["ending"] == "beacon"
    assert [v["id"] for v in result["visits"]] == [
        "timber_marker", "ore_marker", "south_rations", "dock_approach",
    ]
    assert [v["tick"] for v in result["visits"]] == [1, 4, 9, 16]
    assert verify_survey(decode(canonical(result)), require_complete=True)["score"] == 13
    assert [1, 1] in result["seen_tiles"] and [6, 3] in result["seen_tiles"]
    assert len(result["seen_tiles"]) == len({tuple(v) for v in result["seen_tiles"]})


def test_resume_from_real_checkpoint_and_reject_stale_and_terminal():
    source, board = source_board()
    actions = demo_actions()
    partial = build_survey(source, board, actions[:7])
    advanced = resume_survey(partial, actions[7:],
                             expected_digest=partial["report_digest"], require_complete=True)
    assert advanced == build_survey(source, board, actions, require_complete=True)
    with pytest.raises(HarborError, match="stale"):
        resume_survey(partial, actions[7:], expected_digest="0" * 64)
    with pytest.raises(HarborError, match="already complete"):
        resume_survey(advanced, [], expected_digest=advanced["report_digest"])


def test_forged_resealed_fog_and_awards_fail_closed():
    source, board = source_board()
    original = build_survey(source, board, demo_actions())
    for key, mutate in (
        ("score", lambda value: value + 999),
        ("visits", lambda value: value[:-1]),
        ("seen_tiles", lambda value: value[:-1]),
        ("complete", lambda value: False),
    ):
        bad = deepcopy(original)
        bad[key] = mutate(bad[key])
        bad["report_digest"] = digest({k: v for k, v in bad.items() if k != "report_digest"})
        with pytest.raises(HarborError, match="replay"):
            verify_survey(bad)
    tampered = deepcopy(original)
    tampered["bundle"]["state"]["coins"] += 1
    tampered["bundle"]["terminal_digest"] = digest(tampered["bundle"]["state"])
    tampered["bundle"]["bundle_digest"] = digest({
        k: v for k, v in tampered["bundle"].items() if k != "bundle_digest"
    })
    tampered["report_digest"] = digest({k: v for k, v in tampered.items() if k != "report_digest"})
    with pytest.raises(HarborError):
        verify_survey(tampered)


def test_invalid_authoring_and_npc_collision_fail_closed():
    source, board = source_board()
    for bad in (
        {**board, "minimum_points": True},
        {**board, "sites": board["sites"] + [board["sites"][0]]},
        {**board, "sites": [{**board["sites"][0], "at": [0, 0]}]},
        {**board, "sites": [{**board["sites"][0], "required": 1}]},
        {**board, "reveal_radius": 100},
    ):
        with pytest.raises(HarborError):
            validate_board(bad, source)
    with pytest.raises(HarborError, match="collision"):
        build_survey(source, board, [
            {"op": "move", "direction": "east"},
            {"op": "move", "direction": "south"},
        ])


def test_guidance_reaches_actual_unvisited_site_and_replays():
    source, board = source_board()
    partial = build_survey(source, board, [])
    hint = survey_hint(partial, max_steps=12)
    assert hint["site_id"] == "timber_marker"
    assert hint["route"]["actions"] == [{"op": "move", "direction": "east"}]
    assert verify_survey_hint(decode(canonical(hint)))["steps"] == 1
    bad = deepcopy(hint)
    bad["site_id"] = "ore_marker"
    bad["guidance_digest"] = digest({k: v for k, v in bad.items() if k != "guidance_digest"})
    with pytest.raises(HarborError, match="replay"):
        verify_survey_hint(bad)


def test_cas_editor_previews_real_campaign_and_rejects_resealed_revision():
    source, board = source_board()
    report = build_survey(source, board, demo_actions(), require_complete=True)
    edits = [{"id": "ore_marker", "field": "points", "value": 1}]
    revision = edit_survey(
        source, board, edits,
        expected_source_digest=digest(source), expected_board_digest=digest(board),
        preview_report=report,
    )
    assert revision["preview"]["summary"]["before_score"] == 13
    assert revision["preview"]["summary"]["after_score"] == 11
    assert verify_survey_edit(decode(canonical(revision)))["sites"] == 4
    with pytest.raises(HarborError, match="stale"):
        edit_survey(source, board, edits, expected_source_digest="0"*64,
                    expected_board_digest=digest(board))
    bad = deepcopy(revision)
    bad["after"]["sites"][1]["points"] = 9
    bad["after_digest"] = digest(bad["after"])
    bad["revision_digest"] = digest({k: v for k, v in bad.items() if k != "revision_digest"})
    with pytest.raises(HarborError, match="replay"):
        verify_survey_edit(bad)


def test_cli_real_play_export_verify_continue_hint_and_author(tmp_path):
    source, board = source_board()
    board_file = tmp_path / "survey-board.json"
    board_file.write_bytes(canonical(board))
    actions_file = tmp_path / "actions.json"
    actions_file.write_bytes(canonical(demo_actions()[:7]))

    def call(*args):
        process = subprocess.run(CLI + list(args), capture_output=True, check=False)
        assert process.returncode == 0, process.stderr.decode()
        return decode(process.stdout)

    partial = call("survey-run", "--survey-board", str(board_file),
                   "--actions", str(actions_file))
    report_file = tmp_path / "report.json"
    report_file.write_bytes(canonical(partial))
    assert call("survey-verify", "--survey-report", str(report_file))["score"] == partial["score"]
    hint = call("survey-hint", "--survey-report", str(report_file))
    hint_file = tmp_path / "hint.json"
    hint_file.write_bytes(canonical(hint))
    assert call("survey-verify-hint", "--survey-hint", str(hint_file))["verified"]
    actions_file.write_bytes(canonical(demo_actions()[7:]))
    final = call("survey-resume", "--survey-report", str(report_file),
                 "--actions", str(actions_file), "--expected-survey-digest",
                 partial["report_digest"], "--require-all")
    assert final["complete"]
    edits_file = tmp_path / "edits.json"
    edits_file.write_bytes(canonical([{"id": "ore_marker", "field": "points", "value": 1}]))
    report_file.write_bytes(canonical(final))
    revision = call("survey-author", "--survey-board", str(board_file),
                    "--survey-edits", str(edits_file), "--survey-report", str(report_file),
                    "--expected-source-digest", digest(source),
                    "--expected-survey-board-digest", digest(board))
    revision_file = tmp_path / "revision.json"
    revision_file.write_bytes(canonical(revision))
    assert call("survey-verify-author", "--survey-revision", str(revision_file))["verified"]
    denied = subprocess.run(CLI + ["survey-resume", "--survey-report", str(report_file),
                          "--actions", str(actions_file), "--expected-survey-digest",
                          "0" * 64], capture_output=True, check=False)
    assert denied.returncode == 2 and not denied.stdout
