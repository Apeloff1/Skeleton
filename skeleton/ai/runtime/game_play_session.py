"""Bounded, deterministic, offline play sessions for verified original game capsules.

This is an engine-neutral input/replay interface, not a native renderer or a
claim of legal release clearance. A session is replayed from the source capsule
on every restore; self-signed JSON cannot invent a victory or player position.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

from .game_project_capsule import verify_game_capsule
from .gameplay_capabilities import compile_level, platformer_step

SCHEMA = "skeleton.game.play_session.v1"
MAX_FRAMES = 1024
MAX_BATCH_FRAMES = 64
_CONTROL_KEYS = frozenset(("left", "right", "jump"))
_SESSION_KEYS = frozenset((
    "schema_version", "capsule_sha256", "frame_count", "controls",
    "final_avatar", "victory_frame", "trace_sha256", "session_sha256",
    "offline_replay", "native_export_created",
))


class GamePlaySessionError(ValueError):
    """Malformed, tampered, over-budget or incompatible play session."""


def _canonical(value: Any) -> bytes:
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii")
    except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
        raise GamePlaySessionError("noncanonical play session value") from exc


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _admit_controls(controls: Any, *, batch: bool) -> list[dict[str, bool]]:
    limit = MAX_BATCH_FRAMES if batch else MAX_FRAMES
    if type(controls) is not list or not 1 <= len(controls) <= limit:
        raise GamePlaySessionError("controller frame count outside admitted bounds")
    accepted: list[dict[str, bool]] = []
    for item in controls:
        if type(item) is not dict or set(item) != _CONTROL_KEYS:
            raise GamePlaySessionError("controller frame must contain left/right/jump")
        if any(type(value) is not bool for value in item.values()):
            raise GamePlaySessionError("controller buttons must be boolean")
        accepted.append({key: item[key] for key in sorted(_CONTROL_KEYS)})
    return accepted


def _replay(capsule: Mapping[str, Any], controls: list[dict[str, bool]]) -> dict[str, Any]:
    if type(capsule) is not dict:
        raise GamePlaySessionError("play session requires a capsule object")
    # Recompute source rights, edits, platform claims and playability evidence.
    verified = verify_game_capsule(capsule)
    if len(controls) > MAX_FRAMES:
        raise GamePlaySessionError("play session exceeded frame budget")
    tiles = capsule["tilemap"]
    spawn = compile_level({"tiles": tiles})["spawn"]
    avatar = {"x": spawn["x"], "y": spawn["y"], "vx": 0, "vy": 0}
    won_at: int | None = None
    chain = _hash({"schema_version": SCHEMA, "capsule_sha256": verified["capsule_sha256"]})
    for index, control in enumerate(controls, 1):
        if won_at is not None:
            raise GamePlaySessionError("terminal victory forbids further gameplay inputs")
        outcome = platformer_step({"tiles": tiles, "avatar": avatar, "control": control})
        avatar = outcome["avatar"]
        chain = _hash({
            "previous": chain, "frame": index, "control": control,
            "avatar": avatar, "goal_reached": outcome["goal_reached"],
        })
        if outcome["goal_reached"]:
            won_at = index
    return {
        "schema_version": SCHEMA,
        "capsule_sha256": verified["capsule_sha256"],
        "frame_count": len(controls),
        "controls": controls,
        "final_avatar": avatar,
        "victory_frame": won_at,
        "trace_sha256": chain,
        "offline_replay": True,
        "native_export_created": False,
    }


def _seal(capsule: Mapping[str, Any], controls: list[dict[str, bool]]) -> dict[str, Any]:
    body = _replay(capsule, controls)
    return {**body, "session_sha256": _hash(body)}


def start_play_session(capsule: Mapping[str, Any], controls: Any) -> dict[str, Any]:
    """Start a bounded controller-driven game, with a replayable save receipt."""
    return _seal(capsule, _admit_controls(controls, batch=True))


def verify_play_session(capsule: Mapping[str, Any], session: Any) -> dict[str, Any]:
    """Reject forged or stale state by replaying all authoritative controls."""
    if type(session) is not dict or set(session) != _SESSION_KEYS:
        raise GamePlaySessionError("play session schema mismatch")
    if session.get("schema_version") != SCHEMA:
        raise GamePlaySessionError("unsupported play session version")
    controls = _admit_controls(session["controls"], batch=False)
    expected = _seal(capsule, controls)
    # Python dict equality treats bool as int (True == 1). Compare typed
    # canonical JSON, not loose object equality, before trusting a save.
    if _canonical(expected) != _canonical(session):
        raise GamePlaySessionError("play session differs from source-bound replay")
    return {
        "schema_version": "skeleton.game.play_session.verify.v1",
        "capsule_sha256": expected["capsule_sha256"],
        "session_sha256": expected["session_sha256"],
        "frame_count": expected["frame_count"],
        "victory_frame": expected["victory_frame"],
        "source_bound_replay_verified": True,
        "native_export_created": False,
    }


def resume_play_session(
    capsule: Mapping[str, Any], session: Any, controls: Any,
) -> dict[str, Any]:
    """Verify prior state before appending up to 64 new deterministic frames."""
    verify_play_session(capsule, session)
    admitted = _admit_controls(controls, batch=True)
    if session["victory_frame"] is not None:
        raise GamePlaySessionError("terminal victory cannot be resumed")
    if session["frame_count"] + len(admitted) > MAX_FRAMES:
        raise GamePlaySessionError("play session exceeded frame budget")
    return _seal(capsule, session["controls"] + admitted)


def render_play_session(
    capsule: Mapping[str, Any], session: Any,
) -> dict[str, Any]:
    """Show verified, bounded ASCII game state without native renderer claims."""
    receipt = verify_play_session(capsule, session)
    rows = [list(row) for row in capsule["tilemap"]]
    position = session["final_avatar"]
    rows[position["y"]][position["x"]] = "@"
    return {
        "schema_version": "skeleton.game.play_session.render.v1",
        "project_id": capsule["project_id"],
        "frame_count": receipt["frame_count"],
        "victory": receipt["victory_frame"] is not None,
        "grid": ["".join(row) for row in rows],
        "legend": {"@": "player", "#": "wall", ".": "floor", "G": "goal"},
        "render_backend": "ascii_offline",
        "native_renderer_used": False,
        "session_sha256": receipt["session_sha256"],
    }


def inspect_play_frame(
    capsule: Mapping[str, Any], session: Any, frame: Any,
) -> dict[str, Any]:
    """Seek a verified save to an exact deterministic frame, including spawn."""
    receipt = verify_play_session(capsule, session)
    if type(frame) is not int or not 0 <= frame <= receipt["frame_count"]:
        raise GamePlaySessionError("play timeline frame outside verified history")
    prefix = _replay(capsule, session["controls"][:frame])
    return {
        "schema_version": "skeleton.game.play_session.frame.v1",
        "capsule_sha256": receipt["capsule_sha256"],
        "source_session_sha256": receipt["session_sha256"],
        "frame": frame,
        "total_frames": receipt["frame_count"],
        "avatar": prefix["final_avatar"],
        "victory_frame": prefix["victory_frame"],
        "prefix_trace_sha256": prefix["trace_sha256"],
        "source_bound_replay_verified": True,
        "native_renderer_used": False,
    }


def render_play_frame(
    capsule: Mapping[str, Any], session: Any, frame: Any,
) -> dict[str, Any]:
    """Read-only offline ASCII timeline view, never trusting saved coordinates."""
    receipt = inspect_play_frame(capsule, session, frame)
    rows = [list(row) for row in capsule["tilemap"]]
    avatar = receipt["avatar"]
    rows[avatar["y"]][avatar["x"]] = "@"
    return {
        **receipt,
        "grid": ["".join(row) for row in rows],
        "legend": {"@": "player", "#": "wall", ".": "floor", "G": "goal"},
        "render_backend": "ascii_offline",
    }


def fork_play_session(
    capsule: Mapping[str, Any], session: Any, frame: Any, controls: Any,
) -> dict[str, Any]:
    """Branch verified history at a frame, then execute real alternate inputs.

    No source save is modified. A fork at frame zero starts from the canonical
    spawn. A fork after terminal victory is prohibited, and each newly appended
    control is bounded by the same session and batch limits as normal play.
    """
    receipt = verify_play_session(capsule, session)
    if type(frame) is not int or not 0 <= frame <= receipt["frame_count"]:
        raise GamePlaySessionError("play fork frame outside verified history")
    if receipt["victory_frame"] is not None and frame >= receipt["victory_frame"]:
        raise GamePlaySessionError("terminal victory cannot be forked after winning")
    admitted = _admit_controls(controls, batch=True)
    if frame + len(admitted) > MAX_FRAMES:
        raise GamePlaySessionError("forked play session exceeded frame budget")
    return _seal(capsule, session["controls"][:frame] + admitted)


def compare_play_sessions(
    capsule: Mapping[str, Any], left: Any, right: Any,
) -> dict[str, Any]:
    """Read-only comparison of independently replayed alternate game histories.

    The first divergent frame is one-based, including the point at which one
    history ends. Stored avatar positions and victory claims are never trusted
    without canonical replay against the verified original source capsule.
    """
    left_receipt = verify_play_session(capsule, left)
    right_receipt = verify_play_session(capsule, right)
    if left_receipt["capsule_sha256"] != right_receipt["capsule_sha256"]:
        raise GamePlaySessionError("comparison requires the same source capsule")
    left_controls = left["controls"]
    right_controls = right["controls"]
    common = 0
    for left_frame, right_frame in zip(left_controls, right_controls):
        if _canonical(left_frame) != _canonical(right_frame):
            break
        common += 1
    identical = common == len(left_controls) == len(right_controls)
    return {
        "schema_version": "skeleton.game.play_session.compare.v1",
        "capsule_sha256": left_receipt["capsule_sha256"],
        "left_session_sha256": left_receipt["session_sha256"],
        "right_session_sha256": right_receipt["session_sha256"],
        "left_frame_count": left_receipt["frame_count"],
        "right_frame_count": right_receipt["frame_count"],
        "shared_prefix_frames": common,
        "first_divergent_frame": None if identical else common + 1,
        "identical_history": identical,
        "left_avatar": left["final_avatar"],
        "right_avatar": right["final_avatar"],
        "left_victory_frame": left_receipt["victory_frame"],
        "right_victory_frame": right_receipt["victory_frame"],
        "source_bound_replay_verified": True,
        "native_renderer_used": False,
    }


__all__ = [
    "SCHEMA", "MAX_FRAMES", "MAX_BATCH_FRAMES", "GamePlaySessionError",
    "start_play_session", "resume_play_session", "verify_play_session",
    "render_play_session", "inspect_play_frame", "render_play_frame",
    "fork_play_session", "compare_play_sessions",
]
