"""Small, deterministic CHIP-8 VM for original unencumbered homebrew ROMs.

Only the bounded, explicitly implemented classic opcode subset is admitted;
unsupported operations halt with error rather than silently mis-emulate.
Runs entirely in memory; no original ROM, copyrighted boot logo, BIOS,
firmware, SDK, network, subprocess, filesystem access, or model inference.
"""
from __future__ import annotations

import hashlib
from typing import Any

MEMORY_BYTES = 4096
START = 0x200
DISPLAY_W = 64
DISPLAY_H = 32
MAX_ROM_BYTES = MEMORY_BYTES - START


class Chip8Error(ValueError):
    """Invalid or unsupported original CHIP-8 instruction or machine state."""


class Chip8Machine:
    def __init__(self, rom: bytes) -> None:
        if not isinstance(rom, bytes) or not 2 <= len(rom) <= MAX_ROM_BYTES:
            raise Chip8Error("CHIP-8 ROM must fit available unprotected memory")
        self.memory = bytearray(MEMORY_BYTES)
        self.memory[START:START + len(rom)] = rom
        self.pc = START
        self.i = 0
        self.v = [0] * 16
        self.pixels = bytearray(DISPLAY_W * DISPLAY_H)
        self.halted = False
        self.instructions = 0
        self.rom_sha256 = hashlib.sha256(rom).hexdigest()
        self.waiting_for_key = False

    def step(self, key: int | None = None) -> dict[str, Any]:
        if self.halted:
            raise Chip8Error("cannot execute halted CHIP-8 VM")
        if key is not None and (type(key) is not int or not 0 <= key <= 15):
            raise Chip8Error("CHIP-8 keypad code must be hexadecimal")
        if not START <= self.pc <= MEMORY_BYTES - 2:
            self.halted = True
            raise Chip8Error("program counter left allowed CHIP-8 ROM")
        opcode = (self.memory[self.pc] << 8) | self.memory[self.pc + 1]
        group, x, y, nibble = opcode >> 12, (opcode >> 8) & 15, (opcode >> 4) & 15, opcode & 15
        kk, address = opcode & 255, opcode & 4095
        next_pc = self.pc + 2
        self.waiting_for_key = False
        if opcode == 0x00E0:
            self.pixels[:] = bytes(len(self.pixels))
        elif group == 1:
            if not START <= address <= MEMORY_BYTES - 2:
                raise Chip8Error("jump outside program memory")
            next_pc = address
        elif group == 3:
            if self.v[x] == kk:
                next_pc += 2
        elif group == 6:
            self.v[x] = kk
        elif group == 0xA:
            self.i = address
        elif group == 0xD:
            if nibble == 0 or self.i + nibble > MEMORY_BYTES:
                raise Chip8Error("sprite read outside CHIP-8 memory")
            self.v[0xF] = 0
            for row in range(nibble):
                bits = self.memory[self.i + row]
                py = (self.v[y] + row) % DISPLAY_H
                for bit in range(8):
                    if bits & (128 >> bit):
                        px = (self.v[x] + bit) % DISPLAY_W
                        index = py * DISPLAY_W + px
                        if self.pixels[index]:
                            self.v[0xF] = 1
                        self.pixels[index] ^= 1
        elif group == 0xF and kk == 0x0A:
            if key is None:
                self.waiting_for_key = True
                return self.snapshot()
            self.v[x] = key
        else:
            self.halted = True
            raise Chip8Error(f"unsupported CHIP-8 opcode: {opcode:04X}")
        if not START <= next_pc <= MEMORY_BYTES - 2:
            self.halted = True
            raise Chip8Error("instruction would leave allowed memory")
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
            state = self.step(key=None if consumed else key)
            if self.waiting_for_key:
                return state
            consumed = True
        raise Chip8Error("CHIP-8 execution budget exhausted")

    def snapshot(self) -> dict[str, Any]:
        return {
            "pc": self.pc,
            "i": self.i,
            "registers": list(self.v),
            "display_sha256": hashlib.sha256(self.pixels).hexdigest(),
            "lit_pixels": sum(self.pixels),
            "waiting_for_key": self.waiting_for_key,
            "instructions": self.instructions,
            "rom_sha256": self.rom_sha256,
            "no_firmware_loaded": True,
        }


__all__ = [
    "Chip8Error", "Chip8Machine", "START", "MAX_ROM_BYTES",
    "DISPLAY_W", "DISPLAY_H",
]
