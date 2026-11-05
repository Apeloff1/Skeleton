"""End-to-end offline time-trial challenge acceptance on the canonical engine."""
from __future__ import annotations

import copy
import json
import socket

import pytest

from scripts.game.game_project import _demo, main
from skeleton.ai.runtime.game_play_challenge import (
    GameChallengeError, default_challenge_policy, pack_play_score,
    rank_play_scores, validate_challenge_policy, verify_play_board,
    verify_play_score,
)
from skeleton.ai.runtime.game_play_session import start_play_session
from skeleton.ai.runtime.game_playability import check_game_playability
from skeleton.app.cli import run_app_cli


def _capsule():
    return _demo(17, ["windows-11"], "NO", width=8, height=6)


def _control(left=False, right=False, jump=False):
    return {"left": left, "right": right, "jump": jump}


def _winning_session(capsule):
    proof = check_game_playability({"tiles": capsule["tilemap"], "max_frames": 64})
    assert proof["status"] == "playable"
    actions = proof["controller_actions"]
    assert 1 <= len(actions) <= 64
    saved = start_play_session(capsule, actions)
    assert saved["victory_frame"] is not None
    return saved


def test_score_is_deterministic_source_bound_and_replay_verified():
    capsule = _capsule()
    session = _winning_session(capsule)
    policy = default_challenge_policy()
    first = pack_play_score(capsule, session, policy)
    assert first == pack_play_score(capsule, session, policy)
    verified = verify_play_score(capsule, first)
    assert verified["eligible"]
    assert verified["victory_frame"] == session["victory_frame"]
    assert verified["rank_key"][0] == session["frame_count"]
    assert verified["source_bound_replay_verified"]
    assert not verified["score_signature_verified"]
    assert not verified["native_export_created"]


def test_losing_and_disqualified_runs_never_enter_winning_rank():
    capsule = _capsule()
    lost = start_play_session(capsule, [_control()])
    losing = pack_play_score(capsule, lost, default_challenge_policy())
    assert not verify_play_score(capsule, losing)["eligible"]
    assert losing["result"]["rank_key"] is None
    winner = _winning_session(capsule)
    strict = default_challenge_policy()
    strict["max_frames"] = max(1, winner["frame_count"] - 1)
    if winner["frame_count"] > 1:
        disqualified = pack_play_score(capsule, winner, strict)
        assert not disqualified["result"]["eligible"]
    no_jump = default_challenge_policy("fewest_jumps")
    no_jump["max_jump_frames"] = 0
    score = pack_play_score(capsule, winner, no_jump)
    assert score["result"]["eligible"] == all(
        not frame["jump"] for frame in winner["controls"]
    )


@pytest.mark.parametrize("bad", [
    {"schema_version": "wrong", "mode": "fastest", "max_frames": 2,
     "max_jump_frames": 1, "max_left_frames": 1},
    {"schema_version": "skeleton.game.play_challenge_policy.v1", "mode": "fastest",
     "max_frames": True, "max_jump_frames": 0, "max_left_frames": 0},
    {"schema_version": "skeleton.game.play_challenge_policy.v1", "mode": "fastest",
     "max_frames": 2, "max_jump_frames": 3, "max_left_frames": 0},
    {"schema_version": "skeleton.game.play_challenge_policy.v1", "mode": "remote",
     "max_frames": 2, "max_jump_frames": 1, "max_left_frames": 1},
    {"schema_version": "skeleton.game.play_challenge_policy.v1", "mode": "fastest",
     "max_frames": 2, "max_jump_frames": 1, "max_left_frames": 1,
     "admin": True},
])
def test_policy_is_strict_and_rejects_untrusted_fields(bad):
    with pytest.raises(GameChallengeError):
        validate_challenge_policy(bad)


@pytest.mark.parametrize("mutate", [
    lambda p: p["result"].update(eligible=True),
    lambda p: p["result"].update(victory_frame=1),
    lambda p: p["result"]["metrics"].update(jump_frames=0),
    lambda p: p["result"].update(frame_count=True),
    lambda p: p["session"].update(trace_sha256="0" * 64),
    lambda p: p["session"]["controls"][0].update(right=True),
    lambda p: p.update(body_sha256="0" * 64),
    lambda p: p.update(unexpected="injection"),
    lambda p: p["policy"].update(mode="fewest_inputs"),
])
def test_score_rejects_tampering_even_when_json_well_formed(mutate):
    capsule = _capsule()
    score = pack_play_score(
        capsule, start_play_session(capsule, [_control()]),
        default_challenge_policy(),
    )
    mutate(score)
    with pytest.raises((GameChallengeError, ValueError)):
        verify_play_score(capsule, score)


def test_board_ranks_real_winning_session_before_incomplete_session():
    capsule = _capsule()
    policy = default_challenge_policy()
    winner = pack_play_score(capsule, _winning_session(capsule), policy)
    loser = pack_play_score(capsule, start_play_session(capsule, [_control()]), policy)
    board = rank_play_scores(capsule, [loser, winner])
    receipt = verify_play_board(capsule, board)
    assert receipt["entry_count"] == 2
    assert receipt["eligible_count"] == 1
    assert receipt["ranked_session_sha256"][0] == winner["result"]["session_sha256"]
    assert board == rank_play_scores(capsule, [winner, loser])
    assert not receipt["score_signature_verified"]


def test_board_rejects_duplicate_cross_policy_reordered_or_forged_entries():
    capsule = _capsule()
    winner = _winning_session(capsule)
    first = pack_play_score(capsule, winner, default_challenge_policy())
    second = pack_play_score(
        capsule, start_play_session(capsule, [_control()]),
        default_challenge_policy(),
    )
    with pytest.raises(GameChallengeError):
        rank_play_scores(capsule, [first, copy.deepcopy(first)])
    mixed = pack_play_score(capsule, winner, default_challenge_policy("fewest_inputs"))
    with pytest.raises(GameChallengeError):
        rank_play_scores(capsule, [first, mixed])
    board = rank_play_scores(capsule, [first, second])
    forged = copy.deepcopy(board)
    forged["entries"].reverse()
    with pytest.raises(GameChallengeError):
        verify_play_board(capsule, forged)
    forged = copy.deepcopy(board)
    forged["challenge_sha256"] = "0" * 64
    with pytest.raises(GameChallengeError):
        verify_play_board(capsule, forged)


def test_source_edit_invalidates_score_and_board():
    capsule = _capsule()
    score = pack_play_score(capsule, _winning_session(capsule), default_challenge_policy())
    board = rank_play_scores(capsule, [score])
    edited = copy.deepcopy(capsule)
    edited["tilemap"][1] = edited["tilemap"][1].replace("S", ".")
    with pytest.raises(ValueError):
        verify_play_score(edited, score)
    with pytest.raises(ValueError):
        verify_play_board(edited, board)


def test_canonical_cli_score_verify_rank_and_reopen_without_network(tmp_path, capsys, monkeypatch):
    def forbidden(*_args, **_kwargs):
        raise AssertionError("offline game challenge must not use network")
    monkeypatch.setattr(socket, "create_connection", forbidden)
    source = tmp_path / "original.json"
    capsule = _capsule()
    source.write_text(json.dumps(capsule), encoding="utf-8")
    winning = tmp_path / "winning.json"
    losing = tmp_path / "losing.json"
    winning.write_text(json.dumps(_winning_session(capsule)), encoding="utf-8")
    losing.write_text(json.dumps(start_play_session(capsule, [_control()])), encoding="utf-8")
    policy = tmp_path / "policy.json"
    policy.write_text(json.dumps(default_challenge_policy()), encoding="utf-8")
    score_a = tmp_path / "score-a.json"
    score_b = tmp_path / "score-b.json"
    board = tmp_path / "board.json"
    assert run_app_cli([
        "game-project", "--score-play-session", str(winning),
        "--session-capsule", str(source), "--challenge-policy", str(policy),
        "--score-output", str(score_a),
    ]) == 0
    assert json.loads(capsys.readouterr().out)["eligible"]
    assert main([
        "--score-play-session", str(losing), "--session-capsule", str(source),
        "--challenge-policy", str(policy), "--score-output", str(score_b),
    ]) == 0
    capsys.readouterr()
    assert run_app_cli([
        "game-project", "--verify-play-score", str(score_a),
        "--session-capsule", str(source),
    ]) == 0
    assert json.loads(capsys.readouterr().out)["score_replay_verified"]
    assert run_app_cli([
        "game-project", "--rank-play-scores", "--session-capsule", str(source),
        "--score-input", str(score_b), "--score-input", str(score_a),
        "--board-output", str(board),
    ]) == 0
    assert json.loads(capsys.readouterr().out)["eligible_count"] == 1
    assert main([
        "--verify-play-board", str(board), "--session-capsule", str(source),
    ]) == 0
    assert json.loads(capsys.readouterr().out)["entry_count"] == 2
    assert board.exists()


def test_cli_rejects_output_overwrite_symlink_and_mismatched_flags(tmp_path, capsys):
    source = tmp_path / "source.json"
    capsule = _capsule()
    source.write_text(json.dumps(capsule), encoding="utf-8")
    session = tmp_path / "session.json"
    session.write_text(json.dumps(_winning_session(capsule)), encoding="utf-8")
    policy = tmp_path / "policy.json"
    policy.write_text(json.dumps(default_challenge_policy()), encoding="utf-8")
    output = tmp_path / "score.json"
    output.write_text("do not overwrite", encoding="utf-8")
    args = [
        "--score-play-session", str(session), "--session-capsule", str(source),
        "--challenge-policy", str(policy), "--score-output", str(output),
    ]
    assert main(args) == 1
    assert output.read_text() == "do not overwrite"
    capsys.readouterr()
    assert main(["--catalog", "--score-output", str(output)]) == 2
    assert main(["--rank-play-scores", "--session-capsule", str(source),
                 "--board-output", str(output)]) == 2
    link = tmp_path / "linked.json"
    try:
        link.symlink_to(session)
    except (OSError, NotImplementedError):
        pytest.skip("symlink unsupported")
    assert main([
        "--score-play-session", str(link), "--session-capsule", str(source),
        "--challenge-policy", str(policy),
        "--score-output", str(tmp_path / "fresh.json"),
    ]) == 1
    assert not (tmp_path / "fresh.json").exists()
