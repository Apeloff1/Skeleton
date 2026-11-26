"""Scripted playtest agent for the existing playtest flag.

This is not a second builder. ``prove_and_repair`` calls it when playtest mode
is ``auto`` or ``require``. The agent replays a fixed input script and reads
the Python core-loop oracle. It never starts Godot, a GPU, or a model.

The repair loop reads ``repair_codes``. A Godot boot is reported only by
``classify_godot_report``, and only when a binary actually ran and the engine
log contains ``CORE_LOOP_OK``.
"""
from __future__ import annotations

from typing import Any, Mapping

from skeleton.forge.genre_project import MARKER_PREFIX, execute_core_loop, loop_succeeded

SCHEMA = "skeleton.playtest_agent.v1"
MAX_FRAMES = 64

SCRIPTS: dict[str, tuple[str, ...]] = {
    "top_down_shooter": ("move", "aim", "fire", "salvage"),
    "platformer": ("run", "jump", "jump", "reach"),
    "rpg_roguelike": ("enter", "fight", "pay", "follow"),
}

_OBJECTIVE = frozenset({"dead", "broke", "short", "unfinished"})


def taxonomy_for_marker(marker: str) -> str:
    """Map a core-loop marker onto the repair-loop taxonomy."""
    if loop_succeeded(marker):
        return "passed"
    if marker == "stuck":
        return "softlock"
    if marker in _OBJECTIVE:
        return "objective_missed"
    return "marker_missing"


def scripted_playtest(
    content: Mapping[str, Any],
    genre: str,
    *,
    frames: int = 4,
) -> dict[str, Any]:
    """Replay ``frames`` scripted inputs and classify the oracle marker.

    Fewer frames than the genre script is a ``timeout``. The agent does not
    invent a Godot log.
    """
    if not isinstance(genre, str) or genre not in SCRIPTS:
        raise ValueError("playtest agent genre must be a golden-brief genre")
    if isinstance(frames, bool) or not isinstance(frames, int) or not 1 <= frames <= MAX_FRAMES:
        raise ValueError(f"frames must be an integer from 1 to {MAX_FRAMES}")
    if not isinstance(content, Mapping):
        raise ValueError("playtest agent content must be a mapping")
    script = SCRIPTS[genre]
    inputs: list[dict[str, Any]] = []
    for index in range(frames):
        action = script[index] if index < len(script) else script[-1]
        inputs.append({"frame": index, "action": action, "accepted": action in script})
    if any(not step["accepted"] for step in inputs):
        taxonomy = "input_rejected"
        marker = ""
    elif frames < len(script):
        taxonomy = "timeout"
        marker = ""
    else:
        marker = execute_core_loop(content, genre)
        taxonomy = taxonomy_for_marker(marker)
    return {
        "schema_version": SCHEMA,
        "mode": "scripted",
        "genre": genre,
        "frames_requested": frames,
        "frames_run": len(inputs),
        "inputs": inputs,
        "marker": marker,
        "taxonomy": taxonomy,
        "repair_codes": [f"playtest_agent:{taxonomy}"],
        "godot_ran": False,
        "core_loop_ok": False,
    }


def _engine_log(report: Mapping[str, Any]) -> str:
    chunks: list[str] = []
    steps = report.get("steps")
    if isinstance(steps, list):
        for step in steps:
            if isinstance(step, Mapping):
                chunks.append(str(step.get("log_tail") or ""))
    if report.get("log"):
        chunks.append(str(report.get("log")))
    return "\n".join(chunks)


def classify_godot_report(report: Mapping[str, Any] | None) -> dict[str, Any]:
    """Say whether Godot actually booted. Never treat an absent binary as a pass."""
    if not isinstance(report, Mapping):
        return {
            "godot_ran": False,
            "core_loop_ok": False,
            "degraded": True,
            "degraded_reason": "playtest_not_run",
            "playtest_status": None,
        }
    status = report.get("status")
    binary = report.get("binary")
    ran = status in {"passed", "failed"} and isinstance(binary, str) and bool(binary)
    log = _engine_log(report)
    proved = bool(ran and report.get("passed") is True and MARKER_PREFIX in log)
    if status == "unavailable" or not ran:
        reason = report.get("reason") or report.get("binary_source") or "missing-godot-binary"
        return {
            "godot_ran": False,
            "core_loop_ok": False,
            "degraded": True,
            "degraded_reason": str(reason)[:160],
            "playtest_status": status,
        }
    return {
        "godot_ran": True,
        "core_loop_ok": proved,
        "degraded": False,
        "degraded_reason": None if proved else "godot_log_missing_core_loop_ok",
        "playtest_status": status,
    }


__all__ = [
    "MAX_FRAMES",
    "SCHEMA",
    "SCRIPTS",
    "classify_godot_report",
    "scripted_playtest",
    "taxonomy_for_marker",
]
