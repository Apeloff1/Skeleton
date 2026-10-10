"""Differential execution of the *actual* native Sega game's authored C rules.

This is a host-compiled gameplay integration test with a narrow SMSlib I/O
stand-in, NOT a Z80 emulator, native-ROM execution or physical verification.
It detects missed rewards, unsafe stage indices, broken score displays, level
transition regressions, and companion rank divergence from the Python game.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from typing import Any

from skeleton.ai.game_builder.native_release_intake import _read_bounded, _json, NativeIntakeError
from skeleton.ai.game_builder.playable_simulation import advance, initial_state
from skeleton.ai.game_builder.playable_world import PlayableWorld

_MAX_ACTIONS = 20_000
_MAX_DATA_BYTES = 4 * 1024 * 1024
_MOVE_CODES = {"up": "U", "down": "D", "left": "L", "right": "R"}
_BOND_GOALS = (3, 7, 12, 18, 25, 33, 42)
_FIELDS = ("level", "x", "y", "health", "score",
           "gems_remaining", "won", "lost", "bond_rank")
_HASH = re.compile(r"[a-f0-9]{64}\Z")


class Sega8HostReplayError(ValueError):
    """Original game failed host-executed native-rule acceptance."""


def _canonical(value: dict[str, object]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def plan_host_reference(world: PlayableWorld, source_digest: str) -> dict[str, object]:
    """Build independent expectations using authoritative PlayState transitions."""
    if not isinstance(world, PlayableWorld) or not _HASH.fullmatch(source_digest):
        raise Sega8HostReplayError("typed original game and exact source required")
    actions = [move for stage in world.levels for move in stage.safe_solution]
    if not 1 <= len(actions) <= _MAX_ACTIONS:
        raise Sega8HostReplayError("native reference route is empty or oversized")
    state = initial_state(world, authorized=True)
    initial = {
        "level": 0, "x": state.x, "y": state.y,
        "health": state.health, "score": 0,
        "gems_remaining": len(world.levels[0].collectibles),
        "won": 0, "lost": 0, "bond_rank": 0,
    }
    steps: list[dict[str, int | str]] = []
    collectibles = 0
    for move in actions:
        old_score = state.score
        state = advance(world, state, move, authorized=True)
        gained = state.score - old_score
        if gained == 10:
            collectibles += 1
        elif gained not in (0, 100):
            raise Sega8HostReplayError("unexpected original game score delta")
        steps.append({
            "button": move,
            "level": state.level_index, "x": state.x, "y": state.y,
            "health": state.health, "score": state.score,
            "gems_remaining": (
                len(world.levels[state.level_index].collectibles)
                - len(state.collected)
            ),
            "won": int(state.status == "won"),
            "lost": int(state.status == "lost"),
            "bond_rank": sum(collectibles >= goal for goal in _BOND_GOALS),
        })
    if state.status != "won" or collectibles != sum(
        len(stage.collectibles) for stage in world.levels
    ):
        raise Sega8HostReplayError("source replay failed final objective")
    raw: dict[str, object] = {
        "schema": "skeleton.game_builder.sega8_authoritative_host_route.v1",
        "world_digest": world.digest,
        "source_content_digest": source_digest,
        "initial": initial,
        "steps": steps,
        "native_cartridge_compiled": False,
        "host_c_executed": False,
        "z80_cpu_emulator_executed": False,
        "physical_hardware_verified": False,
        "release_approved": False,
    }
    raw["route_sha256"] = sha256(_canonical(raw)).hexdigest()
    return raw


def export_host_reference(
    world: PlayableWorld, source_digest: str, output: Path,
) -> dict[str, object]:
    route = plan_host_reference(world, source_digest)
    if output.exists() or output.is_symlink():
        raise FileExistsError(str(output))
    with output.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(route, stream, indent=2, sort_keys=True)
        stream.write("\n")
    return route


def _parse_reference(raw: bytes) -> dict[str, Any]:
    try:
        obj = _json(raw, "original host reference")
    except (NativeIntakeError, ValueError, UnicodeDecodeError) as exc:
        raise Sega8HostReplayError("invalid independent route JSON") from exc
    expected_keys = {
        "schema", "world_digest", "source_content_digest", "initial", "steps",
        "native_cartridge_compiled", "host_c_executed",
        "z80_cpu_emulator_executed", "physical_hardware_verified",
        "release_approved", "route_sha256",
    }
    if set(obj) != expected_keys:
        raise Sega8HostReplayError("unexpected field or missing original route evidence")
    digest = obj.get("route_sha256")
    payload = {k: v for k, v in obj.items() if k != "route_sha256"}
    if not isinstance(digest, str) or not _HASH.fullmatch(digest):
        raise Sega8HostReplayError("missing canonical route digest")
    if sha256(_canonical(payload)).hexdigest() != digest:
        raise Sega8HostReplayError("reference replay was modified")
    if obj.get("schema") != "skeleton.game_builder.sega8_authoritative_host_route.v1":
        raise Sega8HostReplayError("unrecognized original Sega replay")
    for claim in (
        "native_cartridge_compiled", "host_c_executed",
        "z80_cpu_emulator_executed", "physical_hardware_verified",
        "release_approved",
    ):
        if obj.get(claim) is not False:
            raise Sega8HostReplayError("route forged game-execution or legal evidence")
    if any(
        not isinstance(obj.get(name), str) or not _HASH.fullmatch(obj[name])
        for name in ("world_digest", "source_content_digest")
    ):
        raise Sega8HostReplayError("missing exact world/source identity")
    steps = obj.get("steps")
    initial = obj.get("initial")
    if not isinstance(steps, list) or not 1 <= len(steps) <= _MAX_ACTIONS:
        raise Sega8HostReplayError("host reference has invalid action count")
    if not isinstance(initial, dict):
        raise Sega8HostReplayError("host reference initial state missing")
    for index, item in enumerate([initial, *steps]):
        expected = set(_FIELDS) if index == 0 else set(_FIELDS) | {"button"}
        if (not isinstance(item, dict) or set(item) != expected or any(
            type(item.get(key)) is not int
            or not 0 <= item[key] <= 65535
            for key in _FIELDS
        ) or item["won"] not in (0, 1) or item["lost"] not in (0, 1)
            or (item["won"] == 1 and item["lost"] == 1)):
            raise Sega8HostReplayError("invalid state expectation in original route")
    for step in steps:
        if step.get("button") not in _MOVE_CODES:
            raise Sega8HostReplayError("unsupported original game input")
    if initial["won"] != 0 or initial["lost"] != 0:
        raise Sega8HostReplayError("original authored route cannot start already won or lost")
    if steps[-1]["won"] != 1 or steps[-1]["lost"] != 0:
        raise Sega8HostReplayError("reference does not finish successfully")
    return obj


def run_host_replay(
    source_dir: Path, reference_path: Path, *, compiler: str = "gcc",
) -> dict[str, object]:
    """Actually compile emitted original C and compare every gameplay transition."""
    if compiler != "gcc" or not shutil.which("gcc"):
        raise Sega8HostReplayError("reviewed GCC host differential compiler missing")
    source = _read_bounded(source_dir / "game.c", max_bytes=1024 * 1024)
    makefile = _read_bounded(source_dir / "Makefile", max_bytes=1024 * 1024)
    manifest_raw = _read_bounded(source_dir / "manifest.json", max_bytes=1024 * 1024)
    source_digest = sha256(b"\0".join((source, makefile, manifest_raw))).hexdigest()
    reference = _parse_reference(
        _read_bounded(reference_path, max_bytes=_MAX_DATA_BYTES)
    )
    try:
        manifest = _json(manifest_raw, "original host gameplay manifest")
    except (ValueError, UnicodeDecodeError) as exc:
        raise Sega8HostReplayError("native manifest JSON invalid") from exc
    if (
        not isinstance(manifest, dict)
        or manifest.get("schema") != "skeleton.game_builder.native_sega8_source.v1"
        or manifest.get("platform") not in {"sega_master_system", "sega_game_gear"}
        or manifest.get("world_digest") != reference["world_digest"]
        or reference["source_content_digest"] != source_digest
    ):
        raise Sega8HostReplayError("generated game diverges from independent reference")
    if any(manifest.get(field) is not False for field in (
        "binary_compiled", "emulator_playthrough_verified",
        "physical_hardware_verified", "release_approved",
        "distribution_licensed",
    )):
        raise Sega8HostReplayError("generated C manifest forged an acceptance claim")
    shim = Path(__file__).with_name("sega8_host_shim.h")
    driver = Path(__file__).with_name("sega8_host_replay.c")
    actual_source = source.decode("utf-8", errors="strict")
    if "__sfr __at (0x7F) PSG_PORT;" not in actual_source:
        raise Sega8HostReplayError("native PSG binding changed unexpectedly")
    if "void main(void)" not in actual_source:
        raise Sega8HostReplayError("original game entry point missing")
    commands = "".join(_MOVE_CODES[row["button"]] + "\n" for row in reference["steps"])
    with tempfile.TemporaryDirectory(prefix="skeleton-sega-host-") as temp:
        workspace = Path(temp)
        (workspace / "game-host.c").write_text(actual_source, encoding="utf-8")
        (workspace / "SMSlib.h").write_bytes(_read_bounded(shim, max_bytes=64 * 1024))
        (workspace / "host_replay.c").write_bytes(_read_bounded(driver, max_bytes=64 * 1024))
        executable = workspace / "host-game"
        command = [
            "gcc", "-std=c11", "-O0", "-Wall", "-Wextra", "-Werror",
            "-Wno-unused-function", "-Wno-unused-parameter", "-pedantic",
            "-I", str(workspace), "-o", str(executable),
            str(workspace / "host_replay.c"),
        ]
        if manifest["platform"] == "sega_game_gear":
            command.insert(1, "-DTARGET_GG")
        try:
            build = subprocess.run(
                command, cwd=workspace, capture_output=True, text=True,
                timeout=60, check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise Sega8HostReplayError("host compilation exceeded budget") from exc
        if build.returncode:
            raise Sega8HostReplayError(
                f"actual generated game C failed host compile: {build.stderr[:2500]}"
            )
        binary_digest = sha256(executable.read_bytes()).hexdigest()
        try:
            execution = subprocess.run(
                [str(executable)], input=commands, cwd=workspace,
                capture_output=True, text=True, timeout=60, check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise Sega8HostReplayError("actual game C replay exceeded budget") from exc
        if execution.returncode:
            raise Sega8HostReplayError(
                "real original C gameplay failed: "
                + execution.stderr[:1000]
            )
    states = execution.stdout.splitlines()
    expectations = [reference["initial"], *reference["steps"]]
    if len(states) != len(expectations):
        raise Sega8HostReplayError("host gameplay returned incorrect frame count")
    for index, (line, expected) in enumerate(zip(states, expectations)):
        parts = line.split()
        if len(parts) != len(_FIELDS) + 1 or parts[0] != "S":
            raise Sega8HostReplayError("actual game state output malformed")
        try:
            values = [int(part, 10) for part in parts[1:]]
        except ValueError as exc:
            raise Sega8HostReplayError("non-numeric game state output") from exc
        for field, actual in zip(_FIELDS, values):
            if expected[field] != actual:
                raise Sega8HostReplayError(
                    f"actual C differs from independent source game at "
                    f"action {index} field {field}: {actual} != {expected[field]}"
                )
    return {
        "schema": "skeleton.game_builder.sega8_c_gameplay_differential.v1",
        "target": manifest["platform"],
        "world_digest": reference["world_digest"],
        "source_content_digest": source_digest,
        "authoritative_reference_sha256": reference["route_sha256"],
        "host_executable_sha256": binary_digest,
        "original_controller_actions_verified": len(reference["steps"]),
        "original_levels_verified": manifest["levels"],
        "all_level_completion_verified": True,
        "original_companion_rank_progression_verified": True,
        "original_score_and_screen_state_verified": True,
        "native_game_c_compiled_and_executed_on_host": True,
        "native_z80_rom_executed": False,
        "full_console_emulator_playthrough_verified": False,
        "physical_hardware_verified": False,
        "release_approved": False,
        "rights_independently_verified": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", required=True, type=Path)
    parser.add_argument("--reference", required=True, type=Path)
    parser.add_argument("--receipt-out", type=Path)
    args = parser.parse_args()
    result = run_host_replay(args.source_dir, args.reference)
    if args.receipt_out is not None:
        if args.receipt_out.exists() or args.receipt_out.is_symlink():
            raise FileExistsError(str(args.receipt_out))
        with args.receipt_out.open("x", encoding="utf-8") as stream:
            json.dump(result, stream, indent=2, sort_keys=True)
            stream.write("\n")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
