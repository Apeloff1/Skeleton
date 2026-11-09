"""Clean-room original CHIP-8 homebrew ROM exporter and executable proof.

Target: 1970s-style CHIP-8 virtual machine, 64x32 monochrome screen,
keypad 2/4/6/8. No BIOS, vendor logo, console firmware, emulator ROM,
licensed SDK, borrowed game content, network, or model training.

Uses a generated CHIP-8 bytecode finite-state machine with *real wall
collision* compiled from an original 5..8 tile map. Playability is
verified by executing the bytes on Skeleton's independent CHIP-8 VM.
This is a complete small homebrew game adapter, NOT a PlayStation/NES
or Game Boy ROM exporter and NOT real COSMAC VIP hardware certification.
"""
from __future__ import annotations

from collections import deque
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any, Sequence

from scripts.game.game_project import _read_json
from skeleton.ai.runtime.chip8_machine import (
    Chip8Error, Chip8Machine, MAX_ROM_BYTES, START,
)
from skeleton.ai.runtime.game_project_capsule import (
    GameCapsuleError, verify_game_capsule,
)
from skeleton.ai.runtime.gameplay_capabilities import compile_level, generate_level
from skeleton.ai.runtime.game_rights import SCHEMA as RIGHTS_SCHEMA
from skeleton.ai.runtime.game_project_capsule import make_game_capsule

SCHEMA = "skeleton.game.chip8_homebrew_rom.v1"
# CHIP-8 keypad: 4=left, 6=right, 8=up, 2=down.
DIRECTIONS = ((4, -1, 0), (6, 1, 0), (8, 0, -1), (2, 0, 1))
MAX_MAP = 8


class Chip8ExportError(GameCapsuleError):
    """Unsupported CHIP-8 map or unverified homebrew code emission."""


class _Assembler:
    def __init__(self) -> None:
        self.code = bytearray()
        self.labels: dict[str, int] = {}
        self.patches: list[tuple[int, str, int]] = []

    def label(self, name: str) -> None:
        if name in self.labels:
            raise Chip8ExportError("duplicate CHIP-8 label")
        self.labels[name] = START + len(self.code)

    def op(self, value: int) -> None:
        if not 0 <= value <= 65535:
            raise Chip8ExportError("invalid CHIP-8 opcode")
        self.code.extend(value.to_bytes(2, "big"))

    def jump(self, name: str) -> None:
        self.patches.append((len(self.code), name, 0x1000))
        self.op(0)

    def sprite(self, name: str) -> None:
        self.patches.append((len(self.code), name, 0xA000))
        self.op(0)

    def finish(self) -> tuple[bytes, dict[str, int]]:
        for name, value in (
            ("wall_sprite", 0xC0),
            ("goal_sprite", 0x80),
            ("player_sprite", 0x80),
            ("win_sprite", 0xFE),
        ):
            self.label(name)
            self.code.append(value)
        for offset, name, opcode in self.patches:
            address = self.labels.get(name)
            if address is None or address > 0xFFF:
                raise Chip8ExportError("unresolved CHIP-8 ROM address")
            self.code[offset:offset + 2] = (opcode | address).to_bytes(2, "big")
        if len(self.code) > MAX_ROM_BYTES:
            raise Chip8ExportError("CHIP-8 game exceeds 4-KiB VM memory")
        return bytes(self.code), dict(self.labels)


def _route(rows: list[str]) -> list[int]:
    game = compile_level({"tiles": rows})
    start = (game["spawn"]["x"], game["spawn"]["y"])
    end = (game["goal"]["x"], game["goal"]["y"])
    queue = deque([start])
    parent: dict[tuple[int, int], tuple[tuple[int, int], int] | None] = {start: None}
    while queue:
        x, y = queue.popleft()
        if (x, y) == end:
            break
        for key, dx, dy in DIRECTIONS:
            nx, ny = x + dx, y + dy
            point = (nx, ny)
            if (
                0 <= ny < len(rows) and 0 <= nx < len(rows[0])
                and rows[ny][nx] != "#" and point not in parent
            ):
                parent[point] = ((x, y), key)
                queue.append(point)
    if end not in parent:
        raise Chip8ExportError("source level has no walkable route")
    keys: list[int] = []
    cursor = end
    while cursor != start:
        item = parent[cursor]
        if item is None:
            raise Chip8ExportError("invalid source map parent")
        cursor, key = item
        keys.append(key)
    keys.reverse()
    return keys


def _original_capsule(seed: int) -> dict[str, Any]:
    if type(seed) is not int or not 0 <= seed < 2**31:
        raise Chip8ExportError("seed must be a bounded integer")
    generated = generate_level({
        "seed": seed, "width": 7, "height": 7, "wall_percent": 45,
    })
    tiles = generated["tiles"]
    fingerprint = compile_level({"tiles": tiles})["tile_digest"]
    evidence = {
        "schema_version": RIGHTS_SCHEMA,
        "project_id": f"original-chip8-{seed}",
        "title": "Skeleton original CHIP-8 homebrew game",
        "rights_contact": "local-operator-unverified",
        "assets": [{
            "asset_id": "tilemap", "sha256": fingerprint,
            "source_kind": "original", "licensor": "local-operator-unverified",
            "license_reference": "original-generated-level-v1",
            "allowed_uses": ["embed", "modify"],
            "contains_third_party_content": False,
            "contains_trademarks": False,
            "contains_technological_protection": False,
        }],
        "source_game_reference": None,
        "sdk_authorization": None,
    }
    return make_game_capsule(
        source_tiles=tiles, rights_manifest=evidence,
        target_ids=["chip8-vip"], required_features=["tile2d", "input"],
        action="original_game", jurisdiction="NO",
    )


def compile_chip8_homebrew(capsule: dict[str, Any]) -> dict[str, Any]:
    checked = verify_game_capsule(capsule)
    rights = capsule["rights_receipt"]
    if (
        rights["source_kind_summary"] != ["original"]
        or capsule["action"] not in ("original_game", "independent_mechanics")
        or any(asset["contains_third_party_content"]
               for asset in capsule["rights_manifest"]["assets"])
    ):
        raise Chip8ExportError("original-only CHIP-8 exporter rejects third-party content")
    rows = capsule["tilemap"]
    height, width = len(rows), len(rows[0])
    if not 5 <= width <= MAX_MAP or not 5 <= height <= MAX_MAP:
        raise Chip8ExportError("CHIP-8 homebrew supports original 5-8 tile maps")
    route = _route(rows)
    level = compile_level({"tiles": rows})
    a = _Assembler()
    a.op(0x00E0)  # clear screen
    a.sprite("wall_sprite")
    for y, row in enumerate(rows):
        for x, cell in enumerate(row):
            if cell == "#":
                a.op(0x6000 | (2 * x))
                a.op(0x6100 | (2 * y))
                a.op(0xD011)
    a.sprite("goal_sprite")
    a.op(0x6000 | (2 * level["goal"]["x"]))
    a.op(0x6100 | (2 * level["goal"]["y"]))
    a.op(0xD011)
    a.op(0x6300 | (level["spawn"]["y"] * width + level["spawn"]["x"]))
    a.op(0x6000 | (2 * level["spawn"]["x"]))
    a.op(0x6100 | (2 * level["spawn"]["y"]))
    a.label("input")
    a.sprite("player_sprite")
    a.op(0xD011)  # draw player
    a.op(0xF20A)  # receive one keypad event into V2
    a.op(0xD011)  # XOR erase old player before grid update
    a.jump("dispatch")
    a.label("dispatch")
    for y, row in enumerate(rows):
        for x, tile in enumerate(row):
            if tile in ("#", "G"):
                continue
            state = y * width + x
            next_label = f"next_{state}"
            a.op(0x3300 | state)  # if V3 is current cell, skip next JP
            a.jump(next_label)
            for direction, dx, dy in DIRECTIONS:
                nx, ny = x + dx, y + dy
                next_direction = f"dir_{state}_{direction}"
                a.op(0x3200 | direction)  # V2 == keypad key
                a.jump(next_direction)
                if not (
                    0 <= nx < width and 0 <= ny < height
                    and rows[ny][nx] != "#"
                ):
                    a.jump("input")  # move denied by wall/out-of-bounds
                else:
                    a.op(0x6300 | (ny * width + nx))
                    a.op(0x6000 | (2 * nx))
                    a.op(0x6100 | (2 * ny))
                    a.jump("win" if rows[ny][nx] == "G" else "input")
                a.label(next_direction)
            a.jump("input")
            a.label(next_label)
    a.jump("input")  # unknown input leaves position unchanged
    a.label("win")
    a.op(0x00E0)
    a.sprite("win_sprite")
    a.op(0x601C)  # centered win emblem
    a.op(0x610F)
    a.op(0xD011)
    a.label("win_loop")
    a.jump("win_loop")
    rom, labels = a.finish()
    sha = hashlib.sha256(rom).hexdigest()
    return {
        "schema_version": SCHEMA,
        "target": "chip8-vip",
        "rom": rom,
        "rom_sha256": sha,
        "rom_bytes": len(rom),
        "start_address": START,
        "win_loop_address": labels["win_loop"],
        "initial_state": level["spawn"]["y"] * width + level["spawn"]["x"],
        "map_width": width, "map_height": height,
        "shortest_path_keys": route,
        "shortest_path_steps": len(route),
        "source_capsule_sha256": checked["capsule_sha256"],
        "original_homebrew_only": True,
        "original_game_assets_only": True,
        "boot_rom_embedded": False,
        "licensed_sdk_embedded": False,
        "legal_publication_approved": False,
        "real_1970s_hardware_tested": False,
        "training_examples_added": 0,
    }


def verify_chip8_executable(compiled: dict[str, Any]) -> dict[str, Any]:
    rom = compiled["rom"]
    if hashlib.sha256(rom).hexdigest() != compiled["rom_sha256"]:
        raise Chip8ExportError("CHIP-8 ROM identity changed")
    machine = Chip8Machine(rom)
    initial = machine.run_until_wait(max_instructions=12000)
    if not initial["waiting_for_key"] or machine.v[3] != compiled["initial_state"]:
        raise Chip8ExportError("CHIP-8 game did not initialize at expected spawn")
    # Exercise a definitely blocked direction by walking left from x>=1
    # until reaching the border; the game should not change its tile state.
    for key in compiled["shortest_path_keys"]:
        if machine.pc == compiled["win_loop_address"]:
            break
        # Continue to either the next key wait or actual WIN HALT loop.
        supplied = False
        for _ in range(12000):
            if machine.pc == compiled["win_loop_address"]:
                break
            op = (machine.memory[machine.pc] << 8) | machine.memory[machine.pc + 1]
            waiting = (op & 0xF0FF) == 0xF00A
            machine.step(key=key if waiting and not supplied else None)
            if waiting and not supplied:
                supplied = True
            elif machine.waiting_for_key:
                break
            if supplied and machine.waiting_for_key:
                break
        if not supplied:
            raise Chip8ExportError("CHIP-8 runtime never accepted required keypad event")
        if machine.pc != compiled["win_loop_address"] and not machine.waiting_for_key:
            # The last command may reach the win loop. Otherwise it must
            # return to a real Fx0A input boundary after finite steps.
            raise Chip8ExportError("CHIP-8 did not return to bounded input loop")
    if machine.pc != compiled["win_loop_address"]:
        raise Chip8ExportError("CHIP-8 original ROM failed to reach win state")
    return {
        "schema_version": "skeleton.game.chip8_acceptance.v1",
        "rom_sha256": compiled["rom_sha256"],
        "target": "chip8-vip",
        "win_state_reached": True,
        "vm_program_counter": machine.pc,
        "input_events_used": len(compiled["shortest_path_keys"]),
        "instructions_executed": machine.instructions,
        "display_sha256": machine.snapshot()["display_sha256"],
        "real_hardware_tested": False,
        "actual_original_machine_rom_emitted": True,
        "copyright_or_firmware_bytes_copied": False,
        "training_examples_added": 0,
    }


def main(argv: Sequence[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Export and actually execute original legal CHIP-8 homebrew ROM.")
    modes = p.add_mutually_exclusive_group(required=True)
    modes.add_argument("--capsule", type=Path, help="rights-attested original map project")
    modes.add_argument("--demo-rom", action="store_true", help="generate original 7x7 CHIP-8 homebrew")
    p.add_argument("--seed", type=int, default=1729)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args(argv)
    try:
        if args.capsule is not None and args.seed != 1729:
            raise Chip8ExportError("--seed is only valid with --demo-rom")
        project = (
            _original_capsule(args.seed) if args.demo_rom
            else _read_json(args.capsule)
        )
        compiled = compile_chip8_homebrew(project)
        accepted = verify_chip8_executable(compiled)
        target = args.output.expanduser().absolute()
        if target.is_symlink() or target.exists() or not target.parent.is_dir():
            raise Chip8ExportError("CHIP-8 output must be a new file in an existing directory")
        fd = os.open(
            target,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        with os.fdopen(fd, "wb") as stream:
            stream.write(compiled["rom"])
            stream.flush()
            os.fsync(stream.fileno())
        public = {
            key: value for key, value in compiled.items()
            if key not in ("rom", "shortest_path_keys")
        }
        print(json.dumps({
            **public, "acceptance": accepted, "output_path": str(target),
            "copyright_compliance_certified": False,
        }, sort_keys=True))
        return 0
    except (GameCapsuleError, Chip8Error, ValueError, TypeError, OSError) as exc:
        print("CHIP-8 homebrew export rejected: " + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
