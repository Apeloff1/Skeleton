"""Source-bound, offline time-trial challenges for actual playable capsule sessions.

A score is a reproducible local gameplay receipt, not an authenticated global
leaderboard, a legal clearance, a native build or proof of human play. Every
entry is re-simulated through the canonical game engine before admission.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping, Sequence

from .game_play_session import MAX_FRAMES, verify_play_session

POLICY_SCHEMA = "skeleton.game.play_challenge_policy.v1"
SCORE_SCHEMA = "skeleton.game.play_challenge_score.v1"
BOARD_SCHEMA = "skeleton.game.play_challenge_board.v1"
MAX_SCORE_BYTES = 120 * 1024
MAX_BOARD_BYTES = 160 * 1024
MAX_BOARD_ENTRIES = 8
_MODES = frozenset(("fastest", "fewest_inputs", "fewest_jumps"))
_POLICY_KEYS = frozenset((
    "schema_version", "mode", "max_frames", "max_jump_frames",
    "max_left_frames",
))
_SCORE_KEYS = frozenset(("schema_version", "policy", "session", "result", "body_sha256"))
_BOARD_KEYS = frozenset(("schema_version", "challenge_sha256", "entries", "body_sha256"))


class GameChallengeError(ValueError):
    """An untrusted challenge, score or board failed deterministic admission."""


def _canonical(value: Any) -> bytes:
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii")
    except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
        raise GameChallengeError("challenge JSON cannot be canonicalized") from exc


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _bounded_int(value: Any, lower: int, upper: int, field: str) -> int:
    if type(value) is not int or not lower <= value <= upper:
        raise GameChallengeError("invalid challenge " + field)
    return value


def validate_challenge_policy(value: Any) -> dict[str, Any]:
    """Strictly versioned limits; unknown keys and bool-as-int are rejected."""
    if type(value) is not dict or set(value) != _POLICY_KEYS:
        raise GameChallengeError("challenge policy fields mismatch")
    if value["schema_version"] != POLICY_SCHEMA or type(value["mode"]) is not str:
        raise GameChallengeError("unsupported challenge policy version or mode")
    if value["mode"] not in _MODES:
        raise GameChallengeError("unknown challenge scoring mode")
    maximum = _bounded_int(value["max_frames"], 1, MAX_FRAMES, "max_frames")
    jumps = _bounded_int(value["max_jump_frames"], 0, maximum, "max_jump_frames")
    left = _bounded_int(value["max_left_frames"], 0, maximum, "max_left_frames")
    return {
        "schema_version": POLICY_SCHEMA, "mode": value["mode"],
        "max_frames": maximum, "max_jump_frames": jumps,
        "max_left_frames": left,
    }


def default_challenge_policy(mode: str = "fastest") -> dict[str, Any]:
    """A deterministic local challenge without hidden game-state privileges."""
    return validate_challenge_policy({
        "schema_version": POLICY_SCHEMA, "mode": mode,
        "max_frames": MAX_FRAMES, "max_jump_frames": MAX_FRAMES,
        "max_left_frames": MAX_FRAMES,
    })


def _result(capsule: Mapping[str, Any], session: Any, policy: dict[str, Any]) -> dict[str, Any]:
    # The source, rights metadata, exact controller history, victory and
    # final state are independently replayed, not read from a score claim.
    verified = verify_play_session(capsule, session)
    controls = session["controls"]
    frames = verified["frame_count"]
    active = sum(any(frame.values()) for frame in controls)
    jump = sum(frame["jump"] for frame in controls)
    left = sum(frame["left"] for frame in controls)
    right = sum(frame["right"] for frame in controls)
    neutral = frames - active
    presses = sum(sum(frame.values()) for frame in controls)
    direction_changes = 0
    previous = None
    for frame in controls:
        direction = "left" if frame["left"] and not frame["right"] else (
            "right" if frame["right"] and not frame["left"] else None
        )
        if direction is not None:
            if previous is not None and direction != previous:
                direction_changes += 1
            previous = direction
    won = verified["victory_frame"] is not None
    eligible = (
        won and frames <= policy["max_frames"]
        and jump <= policy["max_jump_frames"]
        and left <= policy["max_left_frames"]
    )
    if policy["mode"] == "fastest":
        ranking = [frames, active, jump, presses]
    elif policy["mode"] == "fewest_inputs":
        ranking = [active, frames, presses, jump]
    else:
        ranking = [jump, frames, active, presses]
    return {
        "schema_version": "skeleton.game.play_challenge_result.v1",
        "capsule_sha256": verified["capsule_sha256"],
        "session_sha256": verified["session_sha256"],
        "challenge_sha256": _digest(policy),
        "frame_count": frames,
        "victory_frame": verified["victory_frame"],
        "eligible": eligible,
        "rank_key": ranking if eligible else None,
        "metrics": {
            "active_frames": active, "neutral_frames": neutral,
            "jump_frames": jump, "left_frames": left,
            "right_frames": right, "button_presses": presses,
            "direction_changes": direction_changes,
        },
        "source_bound_replay_verified": True,
        "native_export_created": False,
        "independent_player_identity_verified": False,
    }


def _seal(body: dict[str, Any], max_bytes: int) -> dict[str, Any]:
    raw = _canonical(body)
    if len(raw) > max_bytes:
        raise GameChallengeError("challenge receipt exceeded byte budget")
    return {**body, "body_sha256": hashlib.sha256(raw).hexdigest()}


def pack_play_score(
    capsule: Mapping[str, Any], session: Any, policy: Any,
) -> dict[str, Any]:
    """Bind a real replayed run and its rules into an offline portable score."""
    admitted = validate_challenge_policy(policy)
    body = {
        "schema_version": SCORE_SCHEMA, "policy": admitted,
        "session": session, "result": _result(capsule, session, admitted),
    }
    return _seal(body, MAX_SCORE_BYTES)


def verify_play_score(capsule: Mapping[str, Any], package: Any) -> dict[str, Any]:
    """Re-run canonical physics; never trust a persisted rank or victory."""
    if type(package) is not dict or set(package) != _SCORE_KEYS:
        raise GameChallengeError("score package schema mismatch")
    if package["schema_version"] != SCORE_SCHEMA:
        raise GameChallengeError("unsupported score package version")
    expected = pack_play_score(capsule, package["session"], package["policy"])
    if _canonical(expected) != _canonical(package):
        raise GameChallengeError("score package differs from verified gameplay")
    return {
        **expected["result"],
        "score_sha256": expected["body_sha256"],
        "score_replay_verified": True,
        "score_signature_verified": False,
    }


def rank_play_scores(
    capsule: Mapping[str, Any], packages: Sequence[Any],
) -> dict[str, Any]:
    """Rank at most eight independently replayed saves of one source/ruleset."""
    if type(packages) is not list or not 1 <= len(packages) <= MAX_BOARD_ENTRIES:
        raise GameChallengeError("challenge board entry count outside bounds")
    seen: set[str] = set()
    challenge: str | None = None
    entries = []
    for package in packages:
        receipt = verify_play_score(capsule, package)
        if challenge is None:
            challenge = receipt["challenge_sha256"]
        if receipt["challenge_sha256"] != challenge:
            raise GameChallengeError("challenge board mixes scoring policies")
        session_sha = receipt["session_sha256"]
        if session_sha in seen:
            raise GameChallengeError("duplicate session in challenge board")
        seen.add(session_sha)
        entries.append(package)
    entries.sort(key=lambda entry: (
        not entry["result"]["eligible"],
        entry["result"]["rank_key"] if entry["result"]["eligible"] else [],
        entry["result"]["session_sha256"],
    ))
    return _seal({
        "schema_version": BOARD_SCHEMA,
        "challenge_sha256": challenge,
        "entries": entries,
    }, MAX_BOARD_BYTES)


def verify_play_board(capsule: Mapping[str, Any], board: Any) -> dict[str, Any]:
    """Re-score, re-sort and verify every entry; an offline hash is not a signature."""
    if type(board) is not dict or set(board) != _BOARD_KEYS:
        raise GameChallengeError("challenge board schema mismatch")
    if board["schema_version"] != BOARD_SCHEMA:
        raise GameChallengeError("unsupported challenge board version")
    expected = rank_play_scores(capsule, board["entries"])
    if _canonical(expected) != _canonical(board):
        raise GameChallengeError("challenge board differs from verified replay")
    return {
        "schema_version": "skeleton.game.play_challenge_board.verify.v1",
        "challenge_sha256": expected["challenge_sha256"],
        "board_sha256": expected["body_sha256"],
        "entry_count": len(expected["entries"]),
        "eligible_count": sum(x["result"]["eligible"] for x in expected["entries"]),
        "ranked_session_sha256": [
            entry["result"]["session_sha256"] for entry in expected["entries"]
        ],
        "source_bound_replay_verified": True,
        "score_signature_verified": False,
        "native_export_created": False,
    }


__all__ = [
    "POLICY_SCHEMA", "SCORE_SCHEMA", "BOARD_SCHEMA", "GameChallengeError",
    "default_challenge_policy", "validate_challenge_policy", "pack_play_score",
    "verify_play_score", "rank_play_scores", "verify_play_board",
]
