"""Bounded, accessible offline turn-by-turn terminal gameplay.

This is a real local controller interface to the canonical deterministic
platformer, not a frame-rate renderer, native export, or network service.
Every action advances one authoritative source-bound simulation frame.
"""
from __future__ import annotations

from typing import Any, Mapping, TextIO

from .game_play_session import (
    GamePlaySessionError, MAX_BATCH_FRAMES, MAX_FRAMES, render_play_session,
    resume_play_session, start_play_session, verify_play_session,
)
from .game_project_capsule import verify_game_capsule
from .game_input_profile import validate_terminal_input_profile, terminal_profile_receipt

MAX_COMMAND_BYTES = 16


def parse_terminal_control(
    command: str, *, input_profile: Any = None,
) -> dict[str, bool] | None:
    """Parse semantic controls using a strictly validated local key layout."""
    bindings = validate_terminal_input_profile(input_profile)
    if type(command) is not str or len(command) > MAX_COMMAND_BYTES:
        raise GamePlaySessionError("terminal command exceeded input budget")
    word = command.strip().lower()
    if word == bindings["quit"]:
        return None
    if word == bindings["wait"]:
        word = ""
    movement_keys = {bindings[action] for action in ("left", "right", "jump")}
    if any(letter not in movement_keys for letter in word) or len(set(word)) != len(word):
        raise GamePlaySessionError("terminal command contains unknown or duplicate keys")
    if bindings["left"] in word and bindings["right"] in word:
        raise GamePlaySessionError("terminal cannot press left and right together")
    return {action: bindings[action] in word for action in ("left", "right", "jump")}


def run_terminal_play(
    capsule: Mapping[str, Any],
    saved: Any,
    input_stream: TextIO,
    output_stream: TextIO,
    *,
    max_frames: int = 32,
    input_profile: Any = None,
) -> dict[str, Any]:
    """Read bounded commands, display actual grid frames, return replayable save.

    No implicit save is written. The caller must persist the resulting verified
    session to an exclusive new path. An early quit without new input is an
    error rather than a fabricated progress receipt.
    """
    bindings = validate_terminal_input_profile(input_profile)
    profile_receipt = terminal_profile_receipt(input_profile)
    if type(max_frames) is not int or not 1 <= max_frames <= MAX_BATCH_FRAMES:
        raise GamePlaySessionError("terminal frame budget must be between 1 and 64")
    verify_game_capsule(capsule)
    if saved is not None:
        verify_play_session(capsule, saved)
        if saved["victory_frame"] is not None:
            raise GamePlaySessionError("terminal victory cannot be resumed")
        if saved["frame_count"] >= MAX_FRAMES:
            raise GamePlaySessionError("terminal history exhausted its frame budget")
    remaining = MAX_FRAMES - (saved["frame_count"] if saved is not None else 0)
    session = saved
    played = 0
    for _ in range(min(max_frames, remaining)):
        output_stream.write("Controls: " + " ".join(
            bindings[action] + "=" + action
            for action in ("left", "right", "jump", "wait", "quit")
        ) + " > ")
        output_stream.flush()
        line = input_stream.readline(MAX_COMMAND_BYTES + 1)
        if len(line) > MAX_COMMAND_BYTES:
            raise GamePlaySessionError("terminal command exceeded input budget")
        if line == "":
            break
        control = parse_terminal_control(line, input_profile=input_profile)
        if control is None:
            break
        if session is None:
            session = start_play_session(capsule, [control])
        else:
            session = resume_play_session(capsule, session, [control])
        played += 1
        view = render_play_session(capsule, session)
        output_stream.write(
            "Frame " + str(session["frame_count"]) + "\n"
            + "\n".join(view["grid"]) + "\n"
        )
        output_stream.flush()
        if view["victory"]:
            break
    if played == 0:
        raise GamePlaySessionError("terminal play produced no new gameplay frames")
    assert session is not None
    receipt = verify_play_session(capsule, session)
    return {
        "schema_version": "skeleton.game.play_terminal.v1",
        "session": session,
        "frames_played": played,
        "total_frames": receipt["frame_count"],
        "victory_frame": receipt["victory_frame"],
        "session_sha256": receipt["session_sha256"],
        "terminal_backend": "ascii_turn_based",
        "input_profile_sha256": profile_receipt["profile_sha256"],
        "native_renderer_used": False,
    }


__all__ = ["MAX_COMMAND_BYTES", "parse_terminal_control", "run_terminal_play"]
