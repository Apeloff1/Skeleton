"""Operator-authorized Game Boy/Color machine-code gameplay qualification.

Runs the *compiled* original ROM in PyBoy, issues physical-console-shaped
D-pad button inputs, reads the WRAM state through the assembler-generated RGBDS
symbol map, and compares the actual cartridge outcome to the Python proof.
No AST simulation or speculative ROM result is accepted. Optional dependency:
PyBoy. A verified emulated input is not a verified USB controller or console.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import tempfile
from time import monotonic

from .contracts import canonical_digest
from .studio_build_qualification import (
    _header, _regular, parse_game_boy_symbols,
)
from .studio_runtime_qualification import _inputs as _engine_inputs

SCHEMA = "skeleton.game_builder.game_boy_emulator_playthrough.v1"
PLATFORMS = frozenset(("nintendo_game_boy", "nintendo_game_boy_color"))
_BUTTONS = frozenset(("up", "down", "left", "right"))
_MAX_ACTIONS = 20_000


class GameBoyEmulationError(ValueError):
    """The real ROM, its state/symbol map or its replay is not qualified."""


@dataclass(frozen=True, slots=True)
class GameBoyEmulationResult:
    target: str
    rom_sha256: str
    symbols_sha256: str
    world_digest: str
    proof_sha256: str
    emulator_available: bool
    emulator_executed: bool
    full_controller_replay: bool
    machine_code_victory: bool
    frames_advanced: int
    source_actions: int
    framebuffer_sha256: str | None
    last_state: dict | None
    blocker: str | None
    receipt_digest: str

    def as_receipt(self) -> dict:
        body = {
            "schema": SCHEMA, "target": self.target,
            "rom_sha256": self.rom_sha256, "symbols_sha256": self.symbols_sha256,
            "world_digest": self.world_digest, "proof_sha256": self.proof_sha256,
            "emulator_available": self.emulator_available,
            "emulator_executed": self.emulator_executed,
            "full_controller_replay": self.full_controller_replay,
            "machine_code_victory": self.machine_code_victory,
            "frames_advanced": self.frames_advanced,
            "source_actions": self.source_actions,
            "framebuffer_sha256": self.framebuffer_sha256,
            "last_state": self.last_state,
            "blocker": self.blocker,
            "physical_controller_verified": False,
            "emulator_audio_verified": False,
            "physical_console_verified": False,
            "model_training_performed": False,
            "release_authorized": False,
        }
        if canonical_digest(body) != self.receipt_digest:
            raise GameBoyEmulationError("native emulator evidence was modified")
        return {**body, "receipt_digest": self.receipt_digest}


def _receipt(target: str, rom: str, symbols: str, world: str, proof: str, *,
             available: bool, executed: bool = False, full: bool = False,
             won: bool = False, frames: int = 0, actions: int = 0,
             framebuffer: str | None = None, state: dict | None = None,
             blocker: str | None = None) -> GameBoyEmulationResult:
    body = {
        "schema": SCHEMA, "target": target, "rom_sha256": rom,
        "symbols_sha256": symbols, "world_digest": world,
        "proof_sha256": proof, "emulator_available": available,
        "emulator_executed": executed, "full_controller_replay": full,
        "machine_code_victory": won, "frames_advanced": frames,
        "source_actions": actions, "framebuffer_sha256": framebuffer,
        "last_state": state, "blocker": blocker,
        "physical_controller_verified": False,
        "emulator_audio_verified": False, "physical_console_verified": False,
        "model_training_performed": False, "release_authorized": False,
    }
    return GameBoyEmulationResult(
        target, rom, symbols, world, proof, available, executed, full, won,
        frames, actions, framebuffer, state, blocker, canonical_digest(body),
    )


def _wram(emulator: object, symbols: dict[str, int]) -> dict:
    try:
        return {name: int(emulator.memory[address])
                for name, address in symbols.items()}
    except (AttributeError, IndexError, KeyError, TypeError, ValueError) as exc:
        raise GameBoyEmulationError("emulator cannot expose actual machine state") from exc


def _frame_hash(emulator: object) -> str:
    try:
        # This is actual emulated LCD pixels (not a Python-world rendering).
        screen = emulator.screen
        if hasattr(screen, "ndarray"):
            pixels = screen.ndarray
            return sha256(pixels.tobytes()).hexdigest()
        return sha256(screen.image.tobytes()).hexdigest()
    except (AttributeError, TypeError, ValueError) as exc:
        raise GameBoyEmulationError("emulator has no genuine LCD pixel framebuffer") from exc


def qualify_game_boy_emulator(
    project: str | Path, *, engine_source: str | Path,
    target: str, authorized: bool, execute: bool,
    timeout_seconds: int = 90, max_frames: int = 260_000,
) -> GameBoyEmulationResult:
    if authorized is not True:
        raise PermissionError("native cartridge emulator requires operator permission")
    if type(execute) is not bool:
        raise GameBoyEmulationError("emulation must have explicit execution intent")
    if target not in PLATFORMS:
        raise GameBoyEmulationError("actual cartridge gameplay adapter supports GB/GBC only")
    if (type(timeout_seconds) is not int or not 5 <= timeout_seconds <= 600
            or type(max_frames) is not int or not 16 <= max_frames <= 260_000):
        raise GameBoyEmulationError("emulator CPU-time/frame budget must be bounded")
    root = Path(project)
    if root.is_symlink() or not root.is_dir():
        raise GameBoyEmulationError("immutable original source and qualified ROM directory required")
    rom_path = root / "qualified.rom"
    symbol_path = root / "qualified.sym"
    try:
        rom = _regular(rom_path, 8 * 1024 * 1024)
        sym = _regular(symbol_path, 128_000)
        _header("gbc" if target.endswith("_color") else "gb", rom)
        labels = parse_game_boy_symbols(sym)
        html, proof, world = _engine_inputs(Path(engine_source))
        gameplay = json.loads(proof)
    except (OSError, ValueError, UnicodeError) as exc:
        raise GameBoyEmulationError("actual native ROM/symbol/proof is not current") from exc
    del html
    rom_sha = sha256(rom).hexdigest()
    sym_sha = sha256(sym).hexdigest()
    proof_sha = sha256(proof).hexdigest()
    actions = gameplay["actions"]
    expected = gameplay["final_state"]
    if (not isinstance(actions, list)
            or not 1 <= len(actions) <= _MAX_ACTIONS
            or any(action not in _BUTTONS for action in actions)
            or expected.get("status") != "won"
            or not all(type(expected.get(name)) is int
                       for name in ("x", "y", "level_index", "health", "score"))):
        raise GameBoyEmulationError("independent Python winning replay has invalid shape")
    available = importlib.util.find_spec("pyboy") is not None
    if not available:
        return _receipt(target, rom_sha, sym_sha, world, proof_sha,
                        available=False, blocker="pyboy_not_installed")
    if not execute:
        return _receipt(target, rom_sha, sym_sha, world, proof_sha,
                        available=True, blocker="cartridge_execution_not_authorized")
    # PyBoy can write save/RTC files. Never allow it to mutate the immutable
    # source project, authoritative ROM or user-specified paths.
    from pyboy import PyBoy
    advanced = 0
    state = None
    deadline = monotonic() + timeout_seconds
    with tempfile.TemporaryDirectory(prefix="skeleton-pyboy-original-") as scratch:
        private_rom = Path(scratch) / ("original.gbc" if target.endswith("_color") else "original.gb")
        private_rom.write_bytes(rom)
        emulator = PyBoy(str(private_rom), window="null", sound_emulated=False)
        try:
            emulator.set_emulation_speed(0)
            for _ in range(90):
                if monotonic() > deadline or advanced >= max_frames:
                    return _receipt(target, rom_sha, sym_sha, world, proof_sha,
                                    available=True, executed=True, frames=advanced,
                                    actions=len(actions), blocker="emulator_initialization_budget_exceeded")
                emulator.tick()
                advanced += 1
            first = _wram(emulator, labels)
            if first["GameWon"] or first["GameLost"]:
                return _receipt(target, rom_sha, sym_sha, world, proof_sha,
                                available=True, executed=True, frames=advanced,
                                actions=len(actions), state=first,
                                blocker="cartridge_not_in_initial_playing_state")
            for index, action in enumerate(actions):
                if monotonic() > deadline or advanced + 12 > max_frames:
                    return _receipt(target, rom_sha, sym_sha, world, proof_sha,
                                    available=True, executed=True, frames=advanced,
                                    actions=len(actions), state=_wram(emulator, labels),
                                    blocker="emulator_playthrough_budget_exceeded")
                emulator.button_press(action)
                for _ in range(2):
                    emulator.tick()
                    advanced += 1
                emulator.button_release(action)
                for _ in range(10):
                    emulator.tick()
                    advanced += 1
                state = _wram(emulator, labels)
                if state["GameLost"]:
                    return _receipt(target, rom_sha, sym_sha, world, proof_sha,
                                    available=True, executed=True, frames=advanced,
                                    actions=len(actions), state=state,
                                    blocker="cartridge_lost_before_verified_victory")
                if state["GameWon"] and index + 1 < len(actions):
                    return _receipt(target, rom_sha, sym_sha, world, proof_sha,
                                    available=True, executed=True, frames=advanced,
                                    actions=len(actions), state=state,
                                    blocker="cartridge_won_before_reference_trace_complete")
            if state is None:
                raise GameBoyEmulationError("no actual controller input was replayed")
            actual = state
            outcome = (
                actual["GameWon"] == 1 and actual["GameLost"] == 0
                and actual["GemsRemaining"] == 0
                and actual["PlayerX"] == expected["x"]
                and actual["PlayerY"] == expected["y"]
                and actual["Level"] == expected["level_index"] + 1
                and actual["Score"] + 256 * actual["ScoreHigh"] == expected["score"]
                and actual["Health"] == expected["health"]
            )
            frame = _frame_hash(emulator)
            return _receipt(
                target, rom_sha, sym_sha, world, proof_sha,
                available=True, executed=True, full=True, won=outcome,
                frames=advanced, actions=len(actions), state=actual,
                framebuffer=frame,
                blocker=None if outcome else "compiled_cartridge_diverged_from_reference_replay",
            )
        finally:
            emulator.stop(save=False)


__all__ = [
    "GameBoyEmulationError", "GameBoyEmulationResult",
    "qualify_game_boy_emulator",
]
