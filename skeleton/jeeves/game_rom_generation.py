"""Original, seeded ROM-only DMG maze cartridges for the local Jeeves lab.

The emitted bytes are a native Game Boy program, not a commercial ROM copy.
Hardware compatibility is unverified. This is a small maze adaptation, rather
than an implementation of every genre supported by the portable game designer.
"""

from __future__ import annotations

import base64
import hashlib
import random
from typing import Any

from .game_rom_runtime import inspect_dmg_cartridge


class _Assembler:
    def __init__(self) -> None:
        self.code = bytearray()
        self.labels: dict[str, int] = {}
        self.references: list[tuple[int, str]] = []

    def emit(self, *values: int) -> None:
        self.code.extend(values)

    def word(self, opcode: int, value: int) -> None:
        self.emit(opcode, value & 255, value >> 8)

    def label(self, name: str) -> None:
        if name in self.labels:
            raise ValueError("Duplicate native program label")
        self.labels[name] = 0x150 + len(self.code)

    def jump(self, name: str, opcode: int = 0xC3) -> None:
        self.emit(opcode, 0, 0)
        self.references.append((len(self.code) - 2, name))

    def address(self, opcode: int, name: str) -> None:
        self.jump(name, opcode)

    def finish(self) -> bytes:
        for offset, name in self.references:
            value = self.labels[name]
            self.code[offset : offset + 2] = value.to_bytes(2, "little")
        if len(self.code) > 32768 - 0x150:
            raise ValueError("Native generated program exceeds ROM-only capacity")
        return bytes(self.code)


def _maze(seed: int) -> list[list[int]]:
    rng = random.Random(seed)
    width, height = 19, 17
    grid = [[2] * width for _ in range(height)]
    grid[1][1] = 0
    stack = [(1, 1)]
    while stack:
        x, y = stack[-1]
        options = [
            (dx, dy)
            for dx, dy in ((2, 0), (-2, 0), (0, 2), (0, -2))
            if 0 < x + dx < width - 1 and 0 < y + dy < height - 1 and grid[y + dy][x + dx] == 2
        ]
        if not options:
            stack.pop()
            continue
        dx, dy = rng.choice(options)
        grid[y + dy // 2][x + dx // 2] = 0
        grid[y + dy][x + dx] = 0
        stack.append((x + dx, y + dy))
    grid[15][17] = 3
    return grid


def build_original_dmg_game(*, seed: int, title: str = "Signal Garden") -> dict[str, Any]:
    if type(seed) is not int or not 0 <= seed <= 2**63 - 1:
        raise ValueError("Native game seed must be a nonnegative bounded integer")
    if not isinstance(title, str) or not 1 <= len(title) <= 120:
        raise ValueError("Native game title is invalid")
    maze = _maze(seed)
    asm = _Assembler()
    asm.emit(0xF3)  # DI: this small cartridge polls the actual VBlank register.
    asm.word(0x31, 0xFFFE)
    asm.emit(0xAF, 0xE0, 0x40)  # Disable LCD before writing VRAM.
    asm.word(0x21, 0xFE00)
    asm.emit(0x06, 160, 0xAF)
    asm.label("clear_oam")
    asm.emit(0x22, 0x05)
    asm.jump("clear_oam", 0xC2)
    asm.word(0x21, 0xC000)
    asm.emit(0x06, 6, 0xAF)
    asm.label("clear_state")
    asm.emit(0x22, 0x05)
    asm.jump("clear_state", 0xC2)
    asm.address(0x11, "tiles")
    asm.word(0x21, 0x8000)
    asm.emit(0x06, 64)
    asm.label("copy_tiles")
    asm.emit(0x1A, 0x22, 0x13, 0x05)
    asm.jump("copy_tiles", 0xC2)
    asm.address(0x11, "tilemap")
    asm.word(0x21, 0x9800)
    asm.word(0x01, 1024)
    asm.label("copy_map")
    asm.emit(0x1A, 0x22, 0x13, 0x0B, 0x78, 0xB1)
    asm.jump("copy_map", 0xC2)
    asm.emit(0x3E, 1)
    asm.word(0xEA, 0xC000)
    asm.word(0xEA, 0xC001)
    asm.emit(0x3E, 24)
    asm.word(0xEA, 0xFE00)
    asm.emit(0x3E, 16)
    asm.word(0xEA, 0xFE01)
    asm.emit(0x3E, 1)
    asm.word(0xEA, 0xFE02)
    asm.emit(0x3E, 0xE4, 0xE0, 0x47, 0xE0, 0x48, 0x3E, 0x93, 0xE0, 0x40)
    asm.label("wait_visible")
    asm.emit(0xF0, 0x44, 0xFE, 144)
    asm.jump("wait_visible", 0xD2)
    asm.label("wait_vblank")
    asm.emit(0xF0, 0x44, 0xFE, 144)
    asm.jump("wait_vblank", 0xDA)
    asm.word(0xFA, 0xC003)
    asm.emit(0x3C)
    asm.word(0xEA, 0xC003)
    asm.emit(0xE6, 3)
    asm.jump("wait_visible", 0xC2)
    asm.word(0xFA, 0xC004)
    asm.emit(0xB7)
    asm.jump("wait_visible", 0xC2)
    asm.word(0xFA, 0xC000)
    asm.emit(0x5F)
    asm.word(0xFA, 0xC001)
    asm.emit(0x57, 0x3E, 0x20, 0xE0, 0, 0xF0, 0, 0xF0, 0, 0x2F, 0xE6, 15, 0x47)
    for index, direction in enumerate(("right", "left", "up", "down")):
        asm.emit(0xCB, 0x40 + index * 8)
        asm.jump(direction, 0xC2)
    asm.jump("wait_visible")
    for direction, opcode in (("right", 0x1C), ("left", 0x1D), ("up", 0x15), ("down", 0x14)):
        asm.label(direction)
        asm.emit(opcode)
        asm.jump("try_move")
    asm.label("try_move")
    asm.emit(0x26, 0, 0x6A, 0x29, 0x29, 0x29, 0x29, 0x29, 0x06, 0, 0x4B, 0x09)
    asm.word(0x01, 0x9800)
    asm.emit(0x09, 0x7E, 0xFE, 2)
    asm.jump("wait_visible", 0xCA)
    asm.emit(0xFE, 3)
    asm.jump("save_position", 0xC2)
    asm.word(0xFA, 0xC002)
    asm.emit(0x3C)
    asm.word(0xEA, 0xC002)
    asm.emit(0x3E, 1)
    asm.word(0xEA, 0xC004)
    asm.emit(0x36, 0)
    asm.label("save_position")
    asm.emit(0x7B)
    asm.word(0xEA, 0xC000)
    asm.emit(0x87, 0x87, 0x87, 0xC6, 8)
    asm.word(0xEA, 0xFE01)
    asm.emit(0x7A)
    asm.word(0xEA, 0xC001)
    asm.emit(0x87, 0x87, 0x87, 0xC6, 16)
    asm.word(0xEA, 0xFE00)
    asm.jump("wait_visible")
    asm.label("tiles")
    # Original four tiles: background, player, brick, goal.
    tiles = bytes(
        [0] * 16
        + [0x3C, 0x3C, 0x7E, 0x7E, 0xFF, 0xFF, 0xDB, 0xDB, 0xFF, 0xFF, 0x7E, 0x7E, 0x3C, 0x3C, 0, 0]
        + [0xFF, 0xFF, 0x81, 0x81, 0xBD, 0xBD, 0xA5, 0xA5, 0xA5, 0xA5, 0xBD, 0xBD, 0x81, 0x81, 0xFF, 0xFF]
        + [0x18, 0x18, 0x3C, 0x3C, 0x7E, 0x7E, 0xFF, 0xFF, 0xFF, 0xFF, 0x7E, 0x7E, 0x3C, 0x3C, 0x18, 0x18]
    )
    asm.emit(*tiles)
    asm.label("tilemap")
    tilemap = bytearray([2] * 1024)
    for y, row in enumerate(maze):
        tilemap[y * 32 : y * 32 + len(row)] = bytes(row)
    asm.emit(*tilemap)
    program = asm.finish()
    rom = bytearray(32768)
    rom[0x100:0x104] = bytes((0, 0xC3, 0x50, 1))
    # Publicly documented cartridge header boot protocol, not a game asset.
    rom[0x104:0x134] = bytes.fromhex(
        "CEED6666CC0D000B03730083000C000D0008111F8889000EDCCC6EE6DDDDD999BBBB67636E0EECCCDDDC999FBBB9333E"
    )
    cartridge_title = title.encode("ascii", errors="replace")[:15]
    rom[0x134 : 0x134 + len(cartridge_title)] = cartridge_title
    rom[0x144:0x146] = b"00"
    rom[0x14A], rom[0x14B] = 1, 0x33
    rom[0x150 : 0x150 + len(program)] = program
    checksum = 0
    for byte in rom[0x134:0x14D]:
        checksum = (checksum - byte - 1) & 255
    rom[0x14D] = checksum
    global_checksum = sum(rom) & 65535
    rom[0x14E:0x150] = global_checksum.to_bytes(2, "big")
    result = bytes(rom)
    metadata = inspect_dmg_cartridge(result)
    occupied = result[: 0x150 + len(program)]
    native_source = (
        '; Original Jeeves DMG cartridge. Assemble with RGBDS and link using zero padding.\nSECTION "Original cartridge", ROM0[$0000]\n'
        + "\n".join(
            "db " + ",".join(f"${byte:02x}" for byte in occupied[offset : offset + 32])
            for offset in range(0, len(occupied), 32)
        )
        + f'\nds {16384-len(occupied)},0\nSECTION "Empty bank", ROMX[$4000],BANK[1]\nds 16384,0\n'
    )
    return {
        "rom_base64": base64.b64encode(result).decode(),
        "rom_digest": metadata["rom_digest"],
        "rom_bytes": len(result),
        "files": {
            "game/generated/native/original-game.gb.base64": base64.b64encode(result).decode(),
            "game/generated/native/original-game.asm": native_source,
        },
        "manifest": {
            "schema_version": "skeleton.original_dmg_game.v1",
            "target": "game_boy",
            "seed": seed,
            "title": title,
            "program_digest": hashlib.sha256(program).hexdigest(),
            "rom_digest": metadata["rom_digest"],
            "rom_bytes": len(result),
            "mapper": "rom_only",
            "genre": "seeded_maze_adaptation",
            "controls": ["up", "down", "left", "right"],
            "goal": "Reach the bottom-right diamond; score is committed by actual cartridge instructions",
            "memory_observations": {
                "player_x": 0xC000,
                "player_y": 0xC001,
                "score": 0xC002,
                "completed": 0xC004,
            },
            "compatibility": "Experimental DMG ROM-only output; no executed hardware compatibility evidence",
            "assets": "Original tile artwork and generated connected maze; no imported ROM assets",
        },
    }
