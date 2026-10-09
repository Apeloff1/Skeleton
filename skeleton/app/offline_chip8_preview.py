"""Native, original-only CHIP-8 homebrew player for SkeletonGame.exe.

Provides actual 64x32 CHIP-8 display and keypad-driven machine execution,
never loads copyrighted external ROMs, console firmware, BIOS, SDK data,
or remote assets. The same project provenance is checked by the homebrew
ROM compiler before display. Pure session logic is headless-testable.
"""
from __future__ import annotations

from typing import Any

from skeleton.ai.runtime.chip8_machine import (
    Chip8Error, Chip8Machine, DISPLAY_W, DISPLAY_H,
)
from scripts.game.export_chip8 import (
    _original_capsule, compile_chip8_homebrew, verify_chip8_executable,
)

SCALE = 8
_KEY_CODES = {
    "left": 4, "a": 4,
    "right": 6, "d": 6,
    "up": 8, "w": 8,
    "down": 2, "s": 2,
}


class OriginalChip8Game:
    """An actual bytecode-run homebrew game, not a screenshot approximation."""

    def __init__(self, *, seed: int = 42) -> None:
        # Generates a new, original map capsule and verifies all ROM bytes
        # before using them in the actual independently implemented VM.
        self.compiled = compile_chip8_homebrew(_original_capsule(seed))
        acceptance = verify_chip8_executable(self.compiled)
        if not acceptance["win_state_reached"]:
            raise Chip8Error("original homebrew ROM failed executable proof")
        self.acceptance = acceptance
        self.machine = Chip8Machine(self.compiled["rom"])
        self.machine.run_until_wait(max_instructions=15000)
        self.seed = seed
        self.won = False
        self.inputs_applied = 0

    def frame(self) -> dict[str, Any]:
        return {
            "schema_version": "skeleton.app.chip8_native_game.v1",
            "rom_sha256": self.compiled["rom_sha256"],
            "display_sha256": self.machine.snapshot()["display_sha256"],
            "lit_pixels": sum(self.machine.pixels),
            "waiting_for_key": self.machine.waiting_for_key,
            "current_cell_state": self.machine.v[3],
            "won": self.won,
            "inputs_applied": self.inputs_applied,
            "hardware_1970s_verified": False,
            "license_publication_verified": False,
            "copyrighted_rom_loaded": False,
            "model_inference_used": False,
            "training_examples_added": 0,
        }

    def key(self, value: int) -> dict[str, Any]:
        if type(value) is not int or not 0 <= value <= 15:
            raise Chip8Error("CHIP-8 controller event must be a hexadecimal key")
        if self.won:
            return self.frame()
        sent = False
        for _ in range(15000):
            if self.machine.pc == self.compiled["win_loop_address"]:
                self.won = True
                break
            opcode = (
                (self.machine.memory[self.machine.pc] << 8)
                | self.machine.memory[self.machine.pc + 1]
            )
            waiting = (opcode & 0xF0FF) == 0xF00A
            self.machine.step(key=value if waiting and not sent else None)
            if waiting and not sent:
                sent = True
            elif self.machine.waiting_for_key and sent:
                break
        if not sent:
            raise Chip8Error("original homebrew game did not accept a key event")
        if (
            self.machine.pc != self.compiled["win_loop_address"]
            and not self.machine.waiting_for_key
        ):
            raise Chip8Error("CHIP-8 game exceeded event execution budget")
        self.won = self.machine.pc == self.compiled["win_loop_address"]
        self.inputs_applied += 1
        return self.frame()

    def reset(self) -> dict[str, Any]:
        # New game session has the same verified original ROM identity.
        self.machine = Chip8Machine(self.compiled["rom"])
        self.machine.run_until_wait(max_instructions=15000)
        self.inputs_applied = 0
        self.won = False
        return self.frame()


def verify_native_chip8_player(seed: int = 42) -> dict[str, Any]:
    """Execute an independent GUI-equivalent controller session to a win."""
    game = OriginalChip8Game(seed=seed)
    starting = game.frame()
    for key in game.compiled["shortest_path_keys"]:
        frame = game.key(key)
        if frame["won"]:
            break
    if not game.won:
        raise Chip8Error("original CHIP-8 native game failed to win")
    if game.inputs_applied != len(game.compiled["shortest_path_keys"]):
        raise Chip8Error("controller trace did not match accepted source-map route")
    return {
        "schema_version": "skeleton.app.chip8_native_game_check.v1",
        "rom_sha256": game.compiled["rom_sha256"],
        "original_player_won": True,
        "controller_events": game.inputs_applied,
        "initial_display_sha256": starting["display_sha256"],
        "winning_display_sha256": frame["display_sha256"],
        "win_state_reached": frame["won"],
        "native_window_was_opened": False,
        "real_vintage_hardware_verified": False,
        "copyrighted_firmware_included": False,
        "model_inference_used": False,
        "training_examples_added": 0,
    }


def run_native_chip8_preview(seed: int = 42) -> int:
    """Create actual native desktop graphics; no browser or downloaded ROM."""
    game = OriginalChip8Game(seed=seed)
    try:
        import tkinter as tk
    except ImportError as exc:
        raise Chip8Error("Tk native window support is unavailable") from exc
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        raise Chip8Error("no native desktop display is available") from exc
    root.title("Skeleton - Original CHIP-8 Game")
    root.resizable(False, False)
    canvas = tk.Canvas(
        root, width=DISPLAY_W * SCALE,
        height=DISPLAY_H * SCALE + 32,
        background="#0d141c", highlightthickness=0,
    )
    canvas.pack()
    def render() -> None:
        # Read the current machine every redraw. A reset replaces the VM,
        # so retaining its old pixel buffer would render stale graphics.
        canvas.delete("all")
        for index, filled in enumerate(game.machine.pixels):
            if not filled:
                continue
            x, y = index % DISPLAY_W, index // DISPLAY_W
            canvas.create_rectangle(
                x * SCALE, y * SCALE,
                (x + 1) * SCALE, (y + 1) * SCALE,
                outline="#8beaa8", fill="#8beaa8",
            )
        message = (
            "WIN!  Press R to restart"
            if game.won else
            "Original CHIP-8 | Arrows/WASD move | R restart | Esc exit"
        )
        canvas.create_text(
            DISPLAY_W * SCALE // 2,
            DISPLAY_H * SCALE + 16,
            text=message, fill="#e3f2e8", font=("Arial", 10),
        )

    def key_down(event: Any) -> None:
        key = str(event.keysym).lower()
        if key == "escape":
            root.destroy()
            return
        if key == "r":
            game.reset()
        elif key in _KEY_CODES:
            game.key(_KEY_CODES[key])
        render()

    root.bind("<KeyPress>", key_down)
    render()
    root.focus_force()
    root.mainloop()
    return 0


__all__ = [
    "OriginalChip8Game", "verify_native_chip8_player",
    "run_native_chip8_preview",
]
