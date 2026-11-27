"""Playtest quality gate: run the emitted input replay and grade its receipt.

``playtest`` proves the project imports and boots. This gate proves the game is
*playable to a standard*. It runs the generated ``interactive_smoke.gd`` (the
same InputMap and physics path a player uses) under headless Godot, parses its
``FORGE_INTERACTIVE_OK`` receipt and grades it against explicit thresholds:

* the run is won with vitality left, inside a pacing window (neither trivially
  short nor a slog);
* pause, restart and save/load were verified by the replay;
* real input drove real movement;
* genre mechanics were exercised: shots and defeats in arena genres; jumps and
  every crystal in platformers; every pad pressed without mistakes, matching
  the content table's move count, in puzzles.

``evaluate_receipt`` is pure and deterministic. ``interactive_playtest`` owns the
engine run, isolating ``user://`` (``XDG_DATA_HOME``) in its temporary project
so a gate run never touches a player's save.
"""

from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
import tempfile
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from skeleton.forge.playable_runtime import SMOKE_PATH
from skeleton.forge.playtest import resolve_binary, scan_log, _native_userdata_supported

GATE_SCHEMA = "skeleton.forge.quality-gate.v1"
RECEIPT_PREFIX = "FORGE_INTERACTIVE_OK "
MIN_INPUT_FRAMES = 20
MIN_MOVEMENT = 100.0
MIN_ELAPSED_S = 3.0
MAX_ELAPSED_S = 75.0
MIN_HP_LEFT = 1.0
ARENA_GENRES = frozenset({"top_down_shooter", "rpg_roguelike"})


def _num(receipt: Mapping[str, Any], key: str) -> float:
    value = receipt.get(key)
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
    ):
        return float("nan")
    return float(value)


def evaluate_receipt(
    receipt: Mapping[str, Any],
    spec: Mapping[str, Any],
    content: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Grade one replay receipt. Returns ``{"passed", "failures", "metrics"}``."""
    failures: list[str] = []
    genre = str(spec.get("genre") or "")

    def need(condition: bool, message: str) -> None:
        if not condition:
            failures.append(message)

    need(
        receipt.get("genre") == genre,
        f"receipt genre {receipt.get('genre')!r} != spec genre {genre!r}",
    )
    need(receipt.get("phase") == "won", "replay did not win")
    for flag in ("pause_verified", "restart_verified", "save_verified"):
        need(receipt.get(flag) is True, f"{flag.replace('_', ' ')} missing")
    input_frames = _num(receipt, "input_frames")
    movement = _num(receipt, "movement_distance")
    elapsed = _num(receipt, "elapsed")
    hp = _num(receipt, "hp")
    need(
        input_frames >= MIN_INPUT_FRAMES,
        f"input frames {input_frames} < {MIN_INPUT_FRAMES}",
    )
    need(movement >= MIN_MOVEMENT, f"movement {movement} < {MIN_MOVEMENT}")
    need(
        MIN_ELAPSED_S <= elapsed <= MAX_ELAPSED_S,
        f"win time {elapsed}s outside pacing window {MIN_ELAPSED_S}-{MAX_ELAPSED_S}s",
    )
    need(hp >= MIN_HP_LEFT, f"won with vitality {hp} < {MIN_HP_LEFT}")
    if genre == "platformer":
        need(_num(receipt, "jumps") >= 1, "platformer replay never jumped")
        need(
            _num(receipt, "collected") >= 5,
            "platformer replay did not collect every crystal",
        )
    elif genre == "puzzle":
        puzzle = (content or {}).get("puzzle") or {}
        need(_num(receipt, "mistakes") == 0, "puzzle replay made mistakes")
        need(receipt.get("puzzle_solved") is True, "puzzle not solved")
        moves = puzzle.get("moves")
        if isinstance(moves, int):
            need(
                _num(receipt, "activations") == moves,
                f"puzzle activations {receipt.get('activations')} != content moves {moves}",
            )
    elif genre in ARENA_GENRES:
        need(_num(receipt, "shots") >= 1, "combat replay never fired or struck")
        need(
            _num(receipt, "defeated") >= 3,
            "combat replay defeated fewer than 3 enemies",
        )
    else:
        failures.append(f"no quality thresholds for genre {genre!r}")
    metrics = {
        key: receipt.get(key)
        for key in (
            "elapsed",
            "hp",
            "score",
            "input_frames",
            "movement_distance",
            "simulated_frames",
            "shots",
            "defeated",
            "jumps",
            "collected",
            "activations",
            "mistakes",
        )
    }
    return {
        "schema": GATE_SCHEMA,
        "passed": not failures,
        "failures": failures,
        "metrics": metrics,
    }


def parse_receipt(log: str) -> dict[str, Any] | None:
    lines = [
        line[len(RECEIPT_PREFIX) :]
        for line in (log or "").splitlines()
        if line.startswith(RECEIPT_PREFIX)
    ]
    if len(lines) != 1:
        return None
    try:
        value = json.loads(lines[0])
    except ValueError:
        return None
    return value if isinstance(value, dict) else None


def _run(
    cmd: list[str], cwd: Path, timeout: float, data_home: Path
) -> tuple[int, str, bool]:
    env = dict(os.environ, GODOT_SILENCE_ROOT_WARNING="1", XDG_DATA_HOME=str(data_home),
               SKELETON_FORGE_NATIVE_PROOF="1")
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            env=env,
        )
        return proc.returncode, (proc.stdout or "") + (proc.stderr or ""), False
    except subprocess.TimeoutExpired as exc:
        out = exc.stdout or b""
        text = out.decode("utf-8", "replace") if isinstance(out, bytes) else str(out)
        return -1, text, True


def interactive_playtest(
    files: Mapping[str, str],
    spec: Mapping[str, Any],
    content: Mapping[str, Any] | None = None,
    *,
    binary: str | None = None,
    timeout: float = 120.0,
    deadline: float | None = None,
) -> dict[str, Any]:
    """Run the emitted input replay and grade it.

    ``status`` is ``passed``, ``failed``, ``unavailable`` (no Godot binary) or
    ``not_applicable`` (the project has no interactive replay).
    """
    base: dict[str, Any] = {
        "schema": GATE_SCHEMA,
        "passed": False,
        "failures": [],
        "metrics": {},
    }
    if SMOKE_PATH not in files:
        return {**base, "status": "not_applicable"}
    if type(timeout) not in (int, float) or not 1 <= timeout <= 600:
        raise ValueError("timeout must be a number in 1..600 seconds")
    path, source, _verified = resolve_binary(binary)
    if path is None:
        return {**base, "status": "unavailable", "reason": source}
    if not _native_userdata_supported():
        return {**base, "status": "unavailable", "reason": "native-userdata-isolation-unavailable"}
    started = time.monotonic()
    root = Path(tempfile.mkdtemp(prefix="forge-quality-gate-"))
    project = root / "project"
    try:
        from skeleton.forge.projector import write_project

        write_project(project, dict(files), overwrite=True)
        log = ""
        for name, cmd in (
            ("import", [path, "--headless", "--path", str(project), "--import"]),
            (
                "replay",
                [
                    path,
                    "--headless",
                    "--fixed-fps",
                    "60",
                    "--path",
                    str(project),
                    "--script",
                    "res://" + SMOKE_PATH,
                ],
            ),
        ):
            budget = timeout
            if deadline is not None:
                budget = min(timeout, deadline - time.monotonic())
                if budget <= 0:
                    return {
                        **base,
                        "status": "failed",
                        "failures": ["deadline exceeded"],
                    }
            code, log, timed_out = _run(cmd, project, budget, root / "userdata")
            errors = scan_log(log)
            if timed_out or code != 0 or errors:
                detail = errors[:5] or (
                    [f"timed out after {budget:.0f}s"]
                    if timed_out
                    else [f"exit {code}"]
                )
                return {
                    **base,
                    "status": "failed",
                    "failures": [f"{name}: {d}" for d in detail],
                    "log_tail": log[-2000:],
                }
        receipt = parse_receipt(log)
        if receipt is None:
            return {
                **base,
                "status": "failed",
                "failures": ["replay printed no single valid receipt"],
                "log_tail": log[-2000:],
            }
        graded = evaluate_receipt(receipt, spec, content)
        return {
            **graded,
            "status": "passed" if graded["passed"] else "failed",
            "receipt": receipt,
            "elapsed_s": round(time.monotonic() - started, 3),
        }
    finally:
        shutil.rmtree(root, ignore_errors=True)


__all__ = ["GATE_SCHEMA", "evaluate_receipt", "interactive_playtest", "parse_receipt"]
