"""Run a *compiled* original Game Boy ROM in PyBoy and prove every move in RAM.

A valid Game Boy header proves almost nothing about gameplay. This script uses
the independent world-derived trajectory to check stage transitions, coordinates,
collectible consumption, scoring, health and win/loss *inside the emulated CPU*.
Neither host RAM writes nor hard-coded ROM offsets are used to force success.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any, Callable

_FIELDS = {
    "level": "Level",
    "x": "PlayerX",
    "y": "PlayerY",
    "health": "Health",
    "score": "Score",
    "gems_remaining": "GemsRemaining",
    "won": "GameWon",
    "lost": "GameLost",
}
_SYM = re.compile(r"^\s*([0-9a-fA-F]{2}):([0-9a-fA-F]{4})\s+([A-Za-z_][A-Za-z0-9_]*)\s*$")
_SCHEMA = "skeleton.game_builder.game_boy_memory_replay.v1"
_ACTIONS = frozenset(("up", "down", "left", "right"))
_MAX_STEPS = 20_000


class EmulatorAcceptanceError(ValueError):
    """A real Game Boy native replay did not reproduce the reference world."""


def read_wram_symbols(sym: str) -> dict[str, int]:
    symbols: dict[str, int] = {}
    for line in sym.splitlines():
        match = _SYM.fullmatch(line)
        if not match:
            continue
        bank, address, name = match.groups()
        if name not in _FIELDS.values():
            continue
        addr = int(address, 16)
        if bank.lower() != "00" or not 0xC000 <= addr <= 0xDFFF:
            raise EmulatorAcceptanceError(f"game state {name} is not in normal WRAM")
        if name in symbols:
            raise EmulatorAcceptanceError(f"duplicated RAM symbol {name}")
        symbols[name] = addr
    if set(symbols) != set(_FIELDS.values()):
        raise EmulatorAcceptanceError("complete native runtime state symbols missing")
    if len(set(symbols.values())) != len(symbols):
        raise EmulatorAcceptanceError("multiple state symbols alias the same memory byte")
    return symbols


def validate_route(route: Any) -> dict[str, Any]:
    if not isinstance(route, dict) or route.get("schema") != _SCHEMA:
        raise EmulatorAcceptanceError("unknown replay schema")
    if route.get("binary_compiled") is not False or route.get("emulator_executed") is not False:
        raise EmulatorAcceptanceError("expected a pre-execution reference, not a claimed success")
    if route.get("release_approved") is not False or route.get("hardware_verified") is not False:
        raise EmulatorAcceptanceError("reference must not self-certify distribution or hardware")
    if not isinstance(route.get("world_digest"), str) or not re.fullmatch("[0-9a-f]{64}", route["world_digest"]):
        raise EmulatorAcceptanceError("missing exact original world identity")
    records = route.get("steps")
    if not isinstance(records, list) or not 1 <= len(records) <= _MAX_STEPS:
        raise EmulatorAcceptanceError("empty or unbounded control trace")
    states = [route.get("initial"), *records]
    if not isinstance(route.get("levels"), int) or not 1 <= route["levels"] <= 8:
        raise EmulatorAcceptanceError("invalid replay level budget")
    for index, state in enumerate(states):
        if not isinstance(state, dict):
            raise EmulatorAcceptanceError(f"state {index} is not an object")
        if index and state.get("button") not in _ACTIONS:
            raise EmulatorAcceptanceError(f"unsupported controller action at step {index}")
        for key in _FIELDS:
            value = state.get(key)
            if type(value) is not int or not 0 <= value <= 255:
                raise EmulatorAcceptanceError(f"invalid {key} at step {index}")
        if state["level"] >= route["levels"] or state["won"] > 1 or state["lost"] > 1:
            raise EmulatorAcceptanceError(f"invalid state flag at step {index}")
    if states[0]["score"] != 0 or states[0]["level"] != 0 or states[0]["won"] or states[0]["lost"]:
        raise EmulatorAcceptanceError("invalid starting hardware state")
    if states[-1]["won"] != 1 or states[-1]["lost"] != 0:
        raise EmulatorAcceptanceError("reference does not end in victory")
    h = route.get("route_sha256")
    signed = {key: value for key, value in route.items() if key != "route_sha256"}
    observed_hash = sha256(json.dumps(signed, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if not isinstance(h, str) or h != observed_hash:
        raise EmulatorAcceptanceError("route data changed since original-world generation")
    return route


def _ram(pyboy: Any, symbols: dict[str, int]) -> dict[str, int]:
    return {name: int(pyboy.memory[symbols[label]]) for name, label in _FIELDS.items()}


def _assert_state(pyboy: Any, symbols: dict[str, int], state: dict[str, Any], *, index: int) -> None:
    observed = _ram(pyboy, symbols)
    expected = {key: state[key] for key in _FIELDS}
    if observed != expected:
        raise EmulatorAcceptanceError(
            f"actual emulated Game Boy diverged at step {index}: "
            f"expected={expected!r}, observed={observed!r}"
        )


def drive_emulator(pyboy: Any, symbols: dict[str, int], route: dict[str, Any]) -> dict[str, Any]:
    """Drive a provided emulator, making no memory edits, hacks or success overrides."""
    route = validate_route(route)
    pyboy.set_emulation_speed(0)
    pyboy.tick(120, False, False)  # DMG startup, CPU and original game's initialization
    _assert_state(pyboy, symbols, route["initial"], index=0)
    for index, expected in enumerate(route["steps"], start=1):
        button = expected["button"]
        # One frame of input, a release frame and enough frames to clear the
        # original 7-frame repeat cooldown. Never hold a key across moves.
        pyboy.button_press(button)
        pyboy.tick(2, False, False)
        pyboy.button_release(button)
        pyboy.tick(9, False, False)
        _assert_state(pyboy, symbols, expected, index=index)
    result = {
        "schema": "skeleton.game_builder.game_boy_emulator_attestation.v1",
        "world_digest": route["world_digest"],
        "route_sha256": route["route_sha256"],
        "emulated_steps": len(route["steps"]),
        "emulated_levels": route["levels"],
        "final_ram": _ram(pyboy, symbols),
        "emulator_gameplay_passed": True,
        "physical_hardware_verified": False,
        "release_approved": False,
    }
    return result


def run(rom: Path, sym: Path, route_path: Path, *, cgb: bool = False) -> dict[str, Any]:
    if not rom.is_file() or not sym.is_file() or not route_path.is_file():
        raise EmulatorAcceptanceError("ROM, linker symbol file and reference route required")
    if rom.stat().st_size < 32768 or rom.stat().st_size > 256 * 1024:
        raise EmulatorAcceptanceError("unexpected compiled DMG ROM length")
    if sym.stat().st_size > 1024 * 1024 or route_path.stat().st_size > 8 * 1024 * 1024:
        raise EmulatorAcceptanceError("oversized emulator evidence")
    symbols = read_wram_symbols(sym.read_text(encoding="utf-8"))
    route = validate_route(json.loads(route_path.read_text(encoding="utf-8")))
    try:
        from pyboy import PyBoy
    except ImportError as exc:
        raise EmulatorAcceptanceError("PyBoy is required for actual ROM emulation") from exc
    if type(cgb) is not bool:
        raise EmulatorAcceptanceError("Game Boy emulator hardware mode must be boolean")
    if cgb and rom.read_bytes()[0x143] != 0xC0:
        raise EmulatorAcceptanceError("CGB-only emulator run requires authentic color-only ROM header")
    player = PyBoy(str(rom), window="null", cgb=cgb, sound_emulated=False)
    try:
        attestation = drive_emulator(player, symbols, route)
    finally:
        player.stop()
    attestation["emulated_hardware_mode"] = "CGB" if cgb else "DMG"
    attestation["rom_sha256"] = sha256(rom.read_bytes()).hexdigest()
    attestation["symbol_file_sha256"] = sha256(sym.read_bytes()).hexdigest()
    return attestation


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rom", required=True, type=Path)
    parser.add_argument("--cgb", action="store_true", help="Execute in actual Game Boy Color mode")
    parser.add_argument("--symbols", required=True, type=Path)
    parser.add_argument("--route", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    output = run(args.rom, args.symbols, args.route, cgb=args.cgb)
    if args.out.exists() or args.out.is_symlink():
        raise FileExistsError(str(args.out))
    with args.out.open("x", encoding="utf-8") as stream:
        json.dump(output, stream, indent=2, sort_keys=True)
        stream.write("\n")
    print(json.dumps({
        "emulator_gameplay_passed": output["emulator_gameplay_passed"],
        "emulated_steps": output["emulated_steps"],
        "emulated_levels": output["emulated_levels"],
        "rom_sha256": output["rom_sha256"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
