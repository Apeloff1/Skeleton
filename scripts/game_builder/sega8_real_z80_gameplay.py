"""Replay every original winning input in an actual compiled Sega Z80 ROM.

Uses the independently tested Z80 CPU core and a bounded VDP/joypad/PSG bus.
Game rules are NEVER mirrored in this adapter: the independent source-game
reference determines all expected player actions and states. Only *guest*
hardware name tables, palette and sprite memory supply actual observations.

Scope is instruction-boundary Z80 + narrow deterministic hardware devices,
not cycle-accurate VDP/audio, full consumer emulator or physical validation.
Cartridge rights and release approval remain independent, false by default.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any

from skeleton.ai.game_builder.native_release_intake import _read_bounded, _json
from skeleton.ai.game_builder.sega_8bit_rom import validate_rom
from scripts.game_builder.emulate_sega8_sdcc_boot import (
    Sega8Machine, SDCCSegaBootError, DEFAULT_FRAME_INSTRUCTIONS,
    _MAP_NAMES,
)
from scripts.game_builder.sega8_source_replay import _parse_reference

MAX_ACTIONS = 20_000
MAX_BOOT_FRAMES = 120
MAX_INPUT_FRAMES = 16
MAX_SETTLE_FRAMES = 9
MAX_INSTRUCTION_FRAMES = DEFAULT_FRAME_INSTRUCTIONS
MAX_TOTAL_GAMEPLAY_FRAMES = 9000
MAX_TOTAL_GAMEPLAY_INSTRUCTIONS = MAX_TOTAL_GAMEPLAY_FRAMES * MAX_INSTRUCTION_FRAMES
_STATE_KEYS = (
    "level", "x", "y", "health", "score",
    "gems_remaining", "bond_rank",
)
_ACTION_BITS = {"up": 0, "down": 1, "left": 2, "right": 3}
_HASH = re.compile(r"[0-9a-f]{64}\Z")


def advance_semantic_trace(
    previous: bytes, index: int, button: str | None,
    hardware_state: dict[str, int],
) -> bytes:
    """Hash actual guest screen snapshots and original action in sequence.

    Excludes hardware clock timings so the same authored game should match
    across SMS and Game Gear, while divergent game state will not.
    """
    if not isinstance(previous, bytes) or len(previous) != 32:
        raise Sega8NativeGameplayError("invalid previous native semantic digest")
    if type(index) is not int or index < 0 or index > MAX_ACTIONS:
        raise Sega8NativeGameplayError("semantic gameplay index out of bounds")
    if (button is None) != (index == 0) or (
        button is not None and button not in _ACTION_BITS
    ):
        raise Sega8NativeGameplayError("unreviewed game controller action")
    if not isinstance(hardware_state, dict) or set(hardware_state) != set(_STATE_KEYS):
        raise Sega8NativeGameplayError("untrusted hardware state fields")
    if any(type(hardware_state[k]) is not int or not 0 <= hardware_state[k] <= 65535
           for k in _STATE_KEYS):
        raise Sega8NativeGameplayError("invalid actual Z80 screen state")
    payload = json.dumps(
        {"index": index, "button": button, "screen": hardware_state},
        sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")
    return sha256(previous + payload).digest()


class Sega8NativeGameplayError(ValueError):
    """The actual Z80 cartridge diverged from the independently authored game."""


def _read_project(source_dir: Path, target: str) -> dict[str, Any]:
    try:
        parts = tuple(_read_bounded(source_dir / leaf, max_bytes=1024*1024)
                      for leaf in ("game.c", "Makefile", "manifest.json"))
        meta = _json(parts[2], "original native Z80 game manifest")
    except (OSError, ValueError, UnicodeDecodeError) as exc:
        raise Sega8NativeGameplayError("native source project failed bounded intake") from exc
    if not isinstance(meta, dict):
        raise Sega8NativeGameplayError("native source manifest is not a typed object")
    if (
        meta.get("schema") != "skeleton.game_builder.native_sega8_source.v1"
        or meta.get("platform") != target
        or meta.get("target_rom_suffix") != _MAP_NAMES[target]
        or type(meta.get("width")) is not int
        or type(meta.get("height")) is not int
        or meta["width"] > (31 if target == "sega_master_system" else 19)
        or meta["height"] > (21 if target == "sega_master_system" else 15)
        or meta.get("width", 0) < 9
        or meta.get("height", 0) < 9
        or type(meta.get("levels")) is not int
        or not 1 <= meta["levels"] <= 8
    ):
        raise Sega8NativeGameplayError("native source cannot target requested real console")
    for key in ("binary_compiled", "emulator_playthrough_verified",
                "physical_hardware_verified", "release_approved",
                "distribution_licensed", "third_party_game_or_firmware_redistributed"):
        if meta.get(key) is not False:
            raise Sega8NativeGameplayError(f"native game source forged {key}")
    digest = sha256(b"\0".join(parts)).hexdigest()
    return {"manifest": meta, "source_digest": digest}


def _glyph(machine: Sega8Machine, x: int, y: int) -> int:
    """Read the lowest eight VDP name-table bits, never a host gameplay state."""
    if not 0 <= x < 32 or not 0 <= y < 24:
        raise Sega8NativeGameplayError("native VDP name-table coordinate outside display")
    base = (machine.registers[2] & 0x0E) << 10
    offset = (base + y*64 + x*2) & 0x3FFF
    # A palette/priority attribute must never turn HUD digits into a
    # different character without changing the corresponding tile ID.
    if machine.vram[(offset+1) & 0x3FFF] & 0x01:
        raise Sega8NativeGameplayError("native name-table tile index used unchecked high bit")
    return machine.vram[offset]


def _digits(machine: Sega8Machine, positions: tuple[int, ...], y: int, xoffset: int) -> int:
    value = 0
    for column in positions:
        digit = _glyph(machine, xoffset + column, y) - 6
        if not 0 <= digit <= 9:
            raise Sega8NativeGameplayError("hardware score/status tile is not an original digit")
        value = 10*value + digit
    return value


def observe_actual_gameplay(machine: Sega8Machine, *, width: int, height: int) -> dict[str, int]:
    """Derive everything visible from real emulated game pixels and palette."""
    if machine.target == "sega_game_gear":
        left, top, hud = (6, 5, 3)
    elif machine.target == "sega_master_system":
        left, top, hud = (0, 2, 0)
    else:
        raise Sega8NativeGameplayError("unsupported screen target")
    heroes = [
        (x, y) for y in range(height) for x in range(width)
        if _glyph(machine, left+x, top+y) in (5, 16)
    ]
    if len(heroes) != 1:
        raise Sega8NativeGameplayError(
            f"native video RAM must show one hero, not {len(heroes)}"
        )
    x, y = heroes[0]
    companion = _glyph(machine, left+18, hud)
    if companion not in range(17, 22):
        raise Sega8NativeGameplayError("native game lost original companion HUD")
    stage = _digits(machine, (9, 10), hud, left)-1
    if not 0 <= stage <= 7:
        raise Sega8NativeGameplayError("native game shows invalid active stage")
    rank = _digits(machine, (12,), hud, left)
    if rank > 7:
        raise Sega8NativeGameplayError("native companion progressed past cap")
    return {
        "level": stage,
        "x": x, "y": y,
        "gems_remaining": _digits(machine, (1, 2), hud, left),
        "health": _digits(machine, (5, 6), hud, left),
        "score": _digits(machine, (13, 14, 15, 16), hud, left),
        "bond_rank": rank,
    }


class ActualZ80GameSession:
    """Interrupt-paced Z80 guest, without host-authoritative game mutations."""

    def __init__(self, rom: bytes, target: str):
        try:
            from z80_python import Z80CPU
        except ImportError as exc:
            raise Sega8NativeGameplayError(
                "independently verified z80-python==0.4.0 CPU core required"
            ) from exc
        self.machine = Sega8Machine(rom, target=target)
        self.cpu = Z80CPU(
            self.machine.read, self.machine.write,
            read_port=self.machine.read_port,
            write_port=self.machine.write_port,
        )
        self.cpu.pc = 0
        self.frames = 0
        self.instructions = 0
        self.tstates = 0

    def step_frame(self, button: str | None) -> None:
        if button is not None and button not in _ACTION_BITS:
            raise Sega8NativeGameplayError("unrecognized game controller action")
        if self.frames >= MAX_TOTAL_GAMEPLAY_FRAMES:
            raise Sega8NativeGameplayError("native Z80 controller frame cap exceeded")
        if self.instructions + MAX_INSTRUCTION_FRAMES > MAX_TOTAL_GAMEPLAY_INSTRUCTIONS:
            raise Sega8NativeGameplayError("native game exceeded total CPU instruction budget")
        self.machine.controller = (
            0xFF if button is None else (0xFF ^ (1 << _ACTION_BITS[button]))
        )
        self.machine.frame_ready = True
        self.cpu.request_maskable_interrupt()
        self.machine.interrupts_issued += 1
        for _ in range(MAX_INSTRUCTION_FRAMES):
            try:
                delta = self.cpu.step()
                self.machine.advance_tstates(delta)
                self.tstates += delta
                self.instructions += 1
            except SDCCSegaBootError as exc:
                raise Sega8NativeGameplayError("compiled native game rejected hardware I/O") from exc
            except Exception as exc:
                raise Sega8NativeGameplayError("Z80 guest instruction execution failed") from exc
        self.frames += 1

    def run_to_playable_boot(self, width: int, height: int) -> dict[str, int]:
        for frame in range(MAX_BOOT_FRAMES):
            self.step_frame(None)
            try:
                self.machine.observe_boot()
                observed = observe_actual_gameplay(self.machine,width=width,height=height)
                if observed["level"] == 0 and observed["score"] == 0:
                    return observed
            except (Sega8NativeGameplayError, SDCCSegaBootError):
                continue
        raise Sega8NativeGameplayError(
            f"real Z80 ROM never reached independently observable playable boot; "
            f"frames={self.frames} pc={self.cpu.pc:#06x} "
            f"vcounter_reads={self.machine.vcounter_reads} "
            f"VRAM_writes={self.machine.vdp_writes}"
        )


def _assert_state(actual: dict[str, int], expected: dict[str, Any], index: int) -> None:
    for key in _STATE_KEYS:
        if actual[key] != expected[key]:
            raise Sega8NativeGameplayError(
                f"real Z80 display diverged at original input {index}, field {key}: "
                f"actual={actual[key]} expected={expected[key]}"
            )


def verify_original_z80_gameplay(
    rom_path: Path, source_dir: Path, route_path: Path, *,
    target: str,
) -> dict[str, object]:
    """Drive the *compiled ROM* to the original winning ending, action by action."""
    if target not in _MAP_NAMES:
        raise Sega8NativeGameplayError("unknown native target console")
    project = _read_project(source_dir, target)
    meta = project["manifest"]
    rom = _read_bounded(rom_path, max_bytes=32768)
    identity = validate_rom(rom, target)
    reference = _parse_reference(_read_bounded(route_path, max_bytes=4*1024*1024))
    if (
        reference["world_digest"] != meta.get("world_digest")
        or reference["source_content_digest"] != project["source_digest"]
        or type(meta.get("reference_safe_moves")) is not int
        or meta["reference_safe_moves"] != len(reference["steps"])
    ):
        raise Sega8NativeGameplayError("cartridge gameplay reference does not match authored source")
    if len(reference["steps"]) > MAX_ACTIONS:
        raise Sega8NativeGameplayError("source game exceeds bounded controller route")

    session = ActualZ80GameSession(rom, target)
    first = session.run_to_playable_boot(meta["width"], meta["height"])
    _assert_state(first, reference["initial"], 0)
    snapshots_checked = 1
    # Only observed native CPU/VDP state enters this content-addressed chain.
    seed = sha256(
        b"skeleton.sega8.native_gameplay.semantic_trace.v1\0"
        + reference["world_digest"].encode("ascii")
    ).digest()
    trace = advance_semantic_trace(seed, 0, None, first)
    max_frames_per_move = 0
    for index, expected in enumerate(reference["steps"], 1):
        observed_controller_reads_before = session.machine.active_joypad_reads
        achieved = False
        last_observed: dict[str, int] | None = None
        for frames in range(1, MAX_INPUT_FRAMES + 1):
            session.step_frame(expected["button"])
            try:
                observed = observe_actual_gameplay(
                    session.machine, width=meta["width"],height=meta["height"],
                )
            except Sega8NativeGameplayError:
                continue
            last_observed = observed
            if all(observed[k] == expected[k] for k in _STATE_KEYS):
                achieved = True
                max_frames_per_move = max(max_frames_per_move, frames)
                break
        if achieved and session.machine.active_joypad_reads <= observed_controller_reads_before:
            raise Sega8NativeGameplayError(
                f"original input {index} was not received from guest Z80 controller port"
            )
        if not achieved:
            raise Sega8NativeGameplayError(
                f"native Z80 controller route differs at action {index}: "
                f"expected={dict((k,expected[k]) for k in _STATE_KEYS)}, "
                f"last observed={last_observed}, cpu_pc={session.cpu.pc:#06x}"
            )
        # Release the controller: the game itself applies its 7-frame movement
        # cooldown and finishes its VBlank tile queue. No host-side mutation
        # to board, coordinates, score, or companion rank is ever allowed.
        for _ in range(MAX_SETTLE_FRAMES):
            session.step_frame(None)
        stable = observe_actual_gameplay(
            session.machine,width=meta["width"],height=meta["height"],
        )
        _assert_state(stable,expected,index)
        trace = advance_semantic_trace(trace,index,expected["button"],stable)
        snapshots_checked += 1

    last = reference["steps"][-1]
    if last["won"] != 1 or last["lost"] != 0:
        raise Sega8NativeGameplayError("reference never won original game")
    machine = session.machine
    # Palette alteration is performed by the *guest C engine* on victory.
    if target == "sega_master_system":
        expected_victory_color = (0x0C,)
        actual_victory_color = (machine.cram[3],)
    else:
        expected_victory_color = (0xF0, 0x00)
        actual_victory_color = (machine.cram[6],machine.cram[7])
    if actual_victory_color != expected_victory_color:
        raise Sega8NativeGameplayError(
            "real Z80 cartridge never entered the original victory state"
        )
    if not machine.vcounter_b0_seen or not machine.vcounter_c8_seen:
        raise Sega8NativeGameplayError("guest initialization did not traverse real VDP scanlines")
    if machine.active_joypad_reads < len(reference["steps"]):
        raise Sega8NativeGameplayError("native game bypassed real input port reads")
    if machine.vdp_writes < 1500 or machine.psg_writes < 4:
        raise Sega8NativeGameplayError("native Z80 did not perform expected video/audio hardware I/O")
    return {
        "schema": "skeleton.game_builder.sega8_actual_z80_gameplay_replay.v1",
        "target": target,
        "rom_sha256": identity["sha256"],
        "original_world_digest": reference["world_digest"],
        "source_content_digest": project["source_digest"],
        "original_route_sha256": reference["route_sha256"],
        "original_levels_replayed": meta["levels"],
        "controller_actions_replayed": len(reference["steps"]),
        "hardware_screen_states_verified": snapshots_checked,
        "semantic_controller_screen_trace_sha256": trace.hex(),
        "semantic_trace_steps_hashed": snapshots_checked,
        "total_instruction_budget_enforced": True,
        "total_frame_budget_enforced": True,
        "real_z80_instruction_count": session.instructions,
        "real_z80_tstates": session.tstates,
        "controller_frame_count": session.frames,
        "max_controller_frames_per_move": max_frames_per_move,
        "real_z80_active_joypad_port_reads": machine.active_joypad_reads,
        "real_z80_directions_seen_as_active_low_buttons":
            machine.active_joypad_bits_observed,
        "original_companion_rank_and_reward_verified": True,
        "actual_victory_palette_verified": True,
        "original_source_game_verified_on_instruction_level_cpu": True,
        "independent_cycle_exact_full_console_emulator_verified": False,
        "physical_hardware_verified": False,
        "rights_independently_verified": False,
        "release_approved": False,
        "distribution_licensed": False,
    }


def main() -> None:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--rom",required=True,type=Path)
    p.add_argument("--source-dir",required=True,type=Path)
    p.add_argument("--route",required=True,type=Path)
    p.add_argument("--target",required=True,choices=sorted(_MAP_NAMES))
    p.add_argument("--receipt-out",type=Path)
    args=p.parse_args()
    report=verify_original_z80_gameplay(
        args.rom,args.source_dir,args.route,target=args.target,
    )
    if args.receipt_out is not None:
        from scripts.game_builder.sega_reproducibility_ci import emit_receipt
        emit_receipt(args.receipt_out, report)
    print(json.dumps(report,sort_keys=True))


if __name__=="__main__":
    main()
