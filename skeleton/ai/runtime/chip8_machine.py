"""Classic CHIP-8 homebrew interpreter with explicit 1970s VM semantics.

Implements the documented classic 35-instruction families, 64x32 XOR
display, keypad, original independently-authored 4x5 digits, timers,
16-depth call stack, deterministic RNG, bounded RAM and explicit quirks.
Does not emulate COSMAC VIP hardware cycles, modern Super-CHIP/XO-CHIP,
BIOS, device ROMs or protected third-party game content. No I/O occurs.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Any

MEMORY_BYTES = 4096
START = 0x200
DISPLAY_W = 64
DISPLAY_H = 32
MAX_ROM_BYTES = MEMORY_BYTES - START
FONT_ADDR = 0x050

# Original authored 4x5 patterns for hexadecimal numbers; not copied
# from any proprietary hardware boot ROM or game distribution.
_FONT: tuple[tuple[str, ...], ...] = (
    ("0110", "1001", "1001", "1001", "0110"),  # 0
    ("0010", "0110", "0010", "0010", "0111"),  # 1
    ("1110", "0001", "0110", "1000", "1111"),  # 2
    ("1110", "0001", "0110", "0001", "1110"),  # 3
    ("1001", "1001", "1111", "0001", "0001"),  # 4
    ("1111", "1000", "1110", "0001", "1110"),  # 5
    ("0111", "1000", "1110", "1001", "0110"),  # 6
    ("1111", "0001", "0010", "0100", "0100"),  # 7
    ("0110", "1001", "0110", "1001", "0110"),  # 8
    ("0110", "1001", "0111", "0001", "1110"),  # 9
    ("0110", "1001", "1111", "1001", "1001"),  # A
    ("1110", "1001", "1110", "1001", "1110"),  # B
    ("0111", "1000", "1000", "1000", "0111"),  # C
    ("1110", "1001", "1001", "1001", "1110"),  # D
    ("1111", "1000", "1110", "1000", "1111"),  # E
    ("1111", "1000", "1110", "1000", "1000"),  # F
)


class Chip8Error(ValueError):
    """Malformed, unsupported or resource-exhausting CHIP-8 operation."""


@dataclass(frozen=True, slots=True)
class Chip8Quirks:
    """Interpreters differ; the selected shift/store rules are recorded."""
    shift_uses_vy: bool = False
    increment_i_after_transfer: bool = False
    wrap_sprites: bool = True


class Chip8Machine:
    def __init__(
        self, rom: bytes, *,
        quirks: Chip8Quirks | None = None,
        random_seed: int = 0xC801,
    ) -> None:
        if not isinstance(rom, bytes) or not 2 <= len(rom) <= MAX_ROM_BYTES:
            raise Chip8Error("CHIP-8 ROM must fit original machine memory")
        if (
            type(random_seed) is not int
            or not 0 <= random_seed <= 0xFFFFFFFF
        ):
            raise Chip8Error("CHIP-8 deterministic RNG seed outside uint32 range")
        if quirks is not None and not isinstance(quirks, Chip8Quirks):
            raise Chip8Error("unsupported CHIP-8 interpreter quirk profile")
        self.quirks = quirks or Chip8Quirks()
        self.memory = bytearray(MEMORY_BYTES)
        for glyph, rows in enumerate(_FONT):
            for row, bits in enumerate(rows):
                self.memory[FONT_ADDR + 5 * glyph + row] = int(bits, 2) << 4
        self.memory[START:START + len(rom)] = rom
        self.pc = START
        self.i = 0
        self.v = [0] * 16
        self.pixels = bytearray(DISPLAY_W * DISPLAY_H)
        self.stack: list[int] = []
        self.held_keys: frozenset[int] = frozenset()
        self.delay_timer = 0
        self.sound_timer = 0
        self._rng = random_seed or 0xA341316C
        self.halted = False
        self.instructions = 0
        self.rom_sha256 = hashlib.sha256(rom).hexdigest()
        self.waiting_for_key = False

    def set_keys(self, keys: frozenset[int] | set[int]) -> None:
        if not isinstance(keys, (frozenset, set)) or any(
            type(key) is not int or not 0 <= key <= 15 for key in keys
        ):
            raise Chip8Error("pressed keys must be a set of hexadecimal codes")
        if len(keys) > 16:
            raise Chip8Error("pressed-key set exceeds CHIP-8 keypad")
        self.held_keys = frozenset(keys)

    def tick_60hz(self, *, frames: int = 1) -> dict[str, Any]:
        """Advance timers explicitly; instruction count is NOT a wall clock."""
        if type(frames) is not int or not 1 <= frames <= 600:
            raise Chip8Error("timer frames must be between 1 and 600")
        self.delay_timer = max(0, self.delay_timer - frames)
        self.sound_timer = max(0, self.sound_timer - frames)
        return {
            "delay_timer": self.delay_timer,
            "sound_timer": self.sound_timer,
            "sound_active": self.sound_timer > 0,
            "hardware_cycle_accuracy_claimed": False,
        }

    def _jump(self, address: int) -> int:
        if not START <= address <= MEMORY_BYTES - 2:
            raise Chip8Error("CHIP-8 jump outside available user program memory")
        return address

    def _random_byte(self) -> int:
        """Xorshift32 is reproducible; NEVER a cryptographic random source."""
        state = self._rng
        state ^= (state << 13) & 0xFFFFFFFF
        state ^= state >> 17
        state ^= (state << 5) & 0xFFFFFFFF
        self._rng = state & 0xFFFFFFFF
        return self._rng & 0xFF

    def _draw(self, x: int, y: int, height: int) -> None:
        if height == 0 or self.i + height > MEMORY_BYTES:
            raise Chip8Error("CHIP-8 draw references invalid sprite memory")
        self.v[0xF] = 0
        for row in range(height):
            bits = self.memory[self.i + row]
            py = self.v[y] + row
            for bit in range(8):
                if not bits & (128 >> bit):
                    continue
                px = self.v[x] + bit
                if self.quirks.wrap_sprites:
                    px %= DISPLAY_W
                    py_fixed = py % DISPLAY_H
                else:
                    if px >= DISPLAY_W or py >= DISPLAY_H:
                        continue
                    py_fixed = py
                idx = py_fixed * DISPLAY_W + px
                if self.pixels[idx]:
                    self.v[0xF] = 1
                self.pixels[idx] ^= 1

    def step(self, key: int | None = None) -> dict[str, Any]:
        if self.halted:
            raise Chip8Error("cannot execute halted CHIP-8 VM")
        if key is not None and (type(key) is not int or not 0 <= key <= 15):
            raise Chip8Error("CHIP-8 key event must be hexadecimal")
        if not START <= self.pc <= MEMORY_BYTES - 2:
            self.halted = True
            raise Chip8Error("program counter left user memory")
        op = (self.memory[self.pc] << 8) | self.memory[self.pc + 1]
        group = op >> 12
        x, y, nibble = (op >> 8) & 15, (op >> 4) & 15, op & 15
        kk, nnn = op & 255, op & 0xFFF
        next_pc = self.pc + 2
        self.waiting_for_key = False
        if op == 0x00E0:
            self.pixels[:] = bytes(len(self.pixels))
        elif op == 0x00EE:
            if not self.stack:
                raise Chip8Error("CHIP-8 return without prior subroutine call")
            next_pc = self.stack.pop()
        elif group == 1:
            next_pc = self._jump(nnn)
        elif group == 2:
            if len(self.stack) >= 16:
                raise Chip8Error("CHIP-8 call stack exceeds 16 frames")
            self.stack.append(next_pc)
            next_pc = self._jump(nnn)
        elif group == 3:
            if self.v[x] == kk:
                next_pc += 2
        elif group == 4:
            if self.v[x] != kk:
                next_pc += 2
        elif group == 5 and nibble == 0:
            if self.v[x] == self.v[y]:
                next_pc += 2
        elif group == 6:
            self.v[x] = kk
        elif group == 7:
            self.v[x] = (self.v[x] + kk) & 0xFF
        elif group == 8:
            a, b = self.v[x], self.v[y]
            if nibble == 0:
                self.v[x] = b
            elif nibble == 1:
                self.v[x] = a | b
            elif nibble == 2:
                self.v[x] = a & b
            elif nibble == 3:
                self.v[x] = a ^ b
            elif nibble == 4:
                self.v[x] = (a + b) & 0xFF
                self.v[15] = int(a + b > 255)
            elif nibble == 5:
                self.v[x] = (a - b) & 0xFF
                self.v[15] = int(a >= b)
            elif nibble == 6:
                value = b if self.quirks.shift_uses_vy else a
                self.v[x] = value >> 1
                self.v[15] = value & 1
            elif nibble == 7:
                self.v[x] = (b - a) & 0xFF
                self.v[15] = int(b >= a)
            elif nibble == 0xE:
                value = b if self.quirks.shift_uses_vy else a
                self.v[x] = (value << 1) & 0xFF
                self.v[15] = int(bool(value & 0x80))
            else:
                raise Chip8Error("unsupported CHIP-8 register ALU instruction")
        elif group == 9 and nibble == 0:
            if self.v[x] != self.v[y]:
                next_pc += 2
        elif group == 0xA:
            self.i = nnn
        elif group == 0xB:
            next_pc = self._jump(nnn + self.v[0])
        elif group == 0xC:
            self.v[x] = self._random_byte() & kk
        elif group == 0xD:
            self._draw(x, y, nibble)
        elif group == 0xE:
            if kk not in (0x9E, 0xA1):
                raise Chip8Error("unsupported CHIP-8 keypad skip instruction")
            pressed = self.v[x] in self.held_keys
            if pressed == (kk == 0x9E):
                next_pc += 2
        elif group == 0xF:
            if kk == 0x07:
                self.v[x] = self.delay_timer
            elif kk == 0x0A:
                active = key if key is not None else (
                    min(self.held_keys) if self.held_keys else None
                )
                if active is None:
                    self.waiting_for_key = True
                    return self.snapshot()
                self.v[x] = active
            elif kk == 0x15:
                self.delay_timer = self.v[x]
            elif kk == 0x18:
                self.sound_timer = self.v[x]
            elif kk == 0x1E:
                if self.i + self.v[x] >= MEMORY_BYTES:
                    raise Chip8Error("CHIP-8 address register exceeded VM memory")
                self.i += self.v[x]
            elif kk == 0x29:
                self.i = FONT_ADDR + 5 * (self.v[x] & 0xF)
            elif kk == 0x33:
                if self.i + 3 > MEMORY_BYTES:
                    raise Chip8Error("CHIP-8 BCD store exceeded VM memory")
                val = self.v[x]
                self.memory[self.i:self.i + 3] = bytes((
                    val // 100, (val // 10) % 10, val % 10,
                ))
            elif kk in (0x55, 0x65):
                count = x + 1
                if self.i + count > MEMORY_BYTES:
                    raise Chip8Error("CHIP-8 register transfer exceeded VM memory")
                if kk == 0x55:
                    self.memory[self.i:self.i + count] = bytes(self.v[:count])
                else:
                    self.v[:count] = self.memory[self.i:self.i + count]
                if self.quirks.increment_i_after_transfer:
                    self.i = min(MEMORY_BYTES - 1, self.i + count)
            else:
                raise Chip8Error("unsupported CHIP-8 register/timer instruction")
        else:
            self.halted = True
            raise Chip8Error(f"unsupported CHIP-8 opcode: {op:04X}")
        next_pc = self._jump(next_pc)
        self.pc = next_pc
        self.instructions += 1
        return self.snapshot()

    def run_until_wait(
        self, *, key: int | None = None, max_instructions: int = 10000,
    ) -> dict[str, Any]:
        if type(max_instructions) is not int or not 1 <= max_instructions <= 100000:
            raise Chip8Error("invalid CHIP-8 execution instruction budget")
        consumed = False
        for _ in range(max_instructions):
            op = (self.memory[self.pc] << 8) | self.memory[self.pc + 1]
            waiting = (op & 0xF0FF) == 0xF00A
            supplied = key if waiting and not consumed else None
            state = self.step(key=supplied)
            if self.waiting_for_key:
                return state
            if supplied is not None:
                consumed = True
        raise Chip8Error("CHIP-8 execution budget exhausted")

    def snapshot(self) -> dict[str, Any]:
        return {
            "pc": self.pc, "i": self.i,
            "registers": list(self.v),
            "stack_depth": len(self.stack),
            "delay_timer": self.delay_timer,
            "sound_timer": self.sound_timer,
            "display_sha256": hashlib.sha256(self.pixels).hexdigest(),
            "lit_pixels": sum(self.pixels),
            "waiting_for_key": self.waiting_for_key,
            "instructions": self.instructions,
            "rom_sha256": self.rom_sha256,
            "no_firmware_loaded": True,
            "hardware_cycle_accuracy_claimed": False,
        }


__all__ = [
    "Chip8Error", "Chip8Quirks", "Chip8Machine", "START",
    "MAX_ROM_BYTES", "DISPLAY_W", "DISPLAY_H", "FONT_ADDR",
]
