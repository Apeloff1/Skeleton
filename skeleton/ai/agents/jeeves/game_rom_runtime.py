"""Bounded, experimental DMG cartridge execution for the Jeeves engine lab.

This executes real cartridge instructions; it is not a complete or certified
Game Boy emulator. It deliberately excludes audio, battery-backed wall-time RTC, CGB-only cartridges,
cycle-perfect bus contention and unsupported mappers. No boot ROM is bundled.
"""

from __future__ import annotations

import base64
import hashlib
import json
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

MAX_ROM_BYTES = 8_388_608
FRAME_CYCLES = 70_224
RTC_CYCLES_PER_SECOND = 4_194_304
WIDTH, HEIGHT = 160, 144
Z, N, H, C = 0x80, 0x40, 0x20, 0x10
BUTTONS = ("right", "left", "up", "down", "a", "b", "select", "start")
ACTIONS = ("idle", "left", "right", "up", "down", "a", "b", "start", "select", "a_right", "a_left")


RUNTIME_CODE_DIGEST = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


class GameRomRuntimeError(ValueError):
    """Malformed source, unsupported hardware or invalid execution state."""


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def inspect_dmg_cartridge(rom: bytes) -> dict[str, Any]:
    if not isinstance(rom, bytes) or not 0x150 <= len(rom) <= MAX_ROM_BYTES:
        raise GameRomRuntimeError("DMG ROM size is outside the admitted bounds")
    if rom[0x143] == 0xC0:
        raise GameRomRuntimeError("Color-only cartridges are not supported by the DMG runtime")
    cartridge = rom[0x147]
    if cartridge not in (0x00, 0x01, 0x02, 0x03, 0x05, 0x06, 0x08, 0x09, 0x0F, 0x10, 0x11, 0x12, 0x13, 0x19, 0x1A, 0x1B):
        raise GameRomRuntimeError(f"Cartridge mapper 0x{cartridge:02x} is not supported")
    size_code = rom[0x148]
    if size_code > 8 or len(rom) != 32768 << size_code:
        raise GameRomRuntimeError("Cartridge bytes do not match the declared ROM bank count")
    if cartridge in (0x00, 0x08, 0x09) and size_code != 0:
        raise GameRomRuntimeError("ROM-only cartridges must have two ROM banks")
    if cartridge in (0x05, 0x06) and size_code > 3:
        raise GameRomRuntimeError("MBC2 supports no more than 16 ROM banks")
    if cartridge in (0x01, 0x02, 0x03, 0x0F, 0x10, 0x11, 0x12, 0x13) and size_code > 6:
        raise GameRomRuntimeError("MBC1/MBC3 ROM banking cannot address this cartridge size")
    checksum = 0
    for byte in rom[0x134:0x14D]:
        checksum = (checksum - byte - 1) & 255
    if checksum != rom[0x14D]:
        raise GameRomRuntimeError("Cartridge header checksum does not match")
    ram_code = rom[0x149]
    if ram_code not in (0, 1, 2, 3, 4, 5):
        raise GameRomRuntimeError("Cartridge RAM size is unsupported")
    ram_bytes = (0, 2048, 8192, 32768, 131072, 65536)[ram_code]
    if cartridge in (0x05, 0x06):
        if ram_code != 0:
            raise GameRomRuntimeError("MBC2 has fixed internal 512 x 4-bit RAM, not header external SRAM")
        ram_bytes = 512
    if cartridge in (0, 1, 0x0F, 0x11, 0x19) and ram_bytes:
        raise GameRomRuntimeError("Cartridge type declares no external RAM")
    if cartridge in (2, 3, 0x08, 0x09, 0x10, 0x12, 0x13, 0x1A, 0x1B) and not ram_bytes:
        raise GameRomRuntimeError("Cartridge type requires external RAM")
    if ram_bytes > 32768 and cartridge not in (0x1A, 0x1B):
        raise GameRomRuntimeError("Declared RAM exceeds this mapper's address space")
    # Standard MBC1 boards cannot wire the two upper selector bits to
    # extended ROM and four-bank RAM simultaneously: >512 KiB needs the
    # selector for ROM and therefore exposes at most one 8 KiB RAM bank.
    # Multi-game MBC1M wiring is not modeled by this single-cartridge core.
    if cartridge in (0x01, 0x02, 0x03) and size_code >= 5 and ram_bytes > 8192:
        raise GameRomRuntimeError(
            "MBC1 cartridges above 512 KiB cannot expose four RAM banks"
        )
    return {
        "platform": "game_boy",
        "mode": "experimental_dmg_rom",
        "rom_digest": hashlib.sha256(rom).hexdigest(),
        "rom_bytes": len(rom),
        "rom_banks": len(rom) // 16384,
        "ram_bytes": ram_bytes,
        "mapper": (
            "mbc1" if cartridge in (1, 2, 3)
            else "mbc2" if cartridge in (0x05, 0x06)
            else "mbc3" if cartridge in (0x0F, 0x10, 0x11, 0x12, 0x13)
            else "mbc5" if cartridge in (0x19, 0x1A, 0x1B)
            else "rom_only"
        ),
        "cartridge_type": cartridge,
        "virtual_rtc": cartridge in (0x0F, 0x10),
        "title": rom[0x134:0x143].split(b"\0", 1)[0].decode("ascii", errors="replace"),
        "support": "experimental DMG CPU/raster; deterministic virtual cycle RTC on timer cartridges only; real battery time, audio, color and cycle-perfect timing unavailable",
    }


class GameBoyMachine:
    """An explicit-input LR35902 CPU and bounded memory-mapped DMG bus."""

    def __init__(self, rom: bytes) -> None:
        self.metadata = inspect_dmg_cartridge(rom)
        self.rom = rom
        self.memory = bytearray(65536)
        self.external_ram = bytearray(self.metadata["ram_bytes"])
        self.framebuffer = bytearray(WIDTH * HEIGHT)
        self.a, self.f, self.b, self.c, self.d, self.e, self.h, self.l = 1, 0xB0, 0, 0x13, 0, 0xD8, 1, 0x4D
        self.sp, self.pc = 0xFFFE, 0x100
        self.ime, self.ime_delay, self.halted, self.stopped, self.halt_bug = False, 0, False, False, False
        self.rom_bank, self.bank_high, self.bank_mode, self.ram_enabled = (
            1,
            0,
            0,
            self.metadata["mapper"] == "rom_only",
        )
        self.buttons = 0
        self.cycles, self.frames, self.divider, self.line_cycles = 0, 0, 0xAB00, 0
        self.instructions = 0
        self.stat_line = False
        # Battery-backed wall time is intentionally unavailable. RTC grows
        # only through executed CPU cycles and is sealed in source snapshots.
        self.rtc_regs = [0, 0, 0, 0, 0]
        self.rtc_latched = None
        self.rtc_latch_prev = 0
        self.rtc_cycle_remainder = 0
        defaults = {
            0xFF00: 0xCF,
            0xFF07: 0,
            0xFF0F: 0xE1,
            0xFF40: 0x91,
            0xFF41: 0x82,
            0xFF47: 0xFC,
            0xFF48: 0xFF,
            0xFF49: 0xFF,
            0xFF4A: 0,
            0xFF4B: 0,
            0xFFFF: 0,
        }
        for address, value in defaults.items():
            self.memory[address] = value

    def _rtc_advance(self, cycles: int) -> None:
        """Advance the virtual clock in O(1), never using host wall time."""
        if not self.metadata["virtual_rtc"] or self.rtc_regs[4] & 0x40:
            return
        if type(cycles) is not int or cycles < 0:
            raise GameRomRuntimeError("RTC cycle increment is invalid")
        seconds, self.rtc_cycle_remainder = divmod(
            self.rtc_cycle_remainder + cycles, RTC_CYCLES_PER_SECOND
        )
        if not seconds:
            return
        minutes, self.rtc_regs[0] = divmod(self.rtc_regs[0] + seconds, 60)
        hours, self.rtc_regs[1] = divmod(self.rtc_regs[1] + minutes, 60)
        days, self.rtc_regs[2] = divmod(self.rtc_regs[2] + hours, 24)
        day = self.rtc_regs[3] | ((self.rtc_regs[4] & 1) << 8)
        day += days
        carry = bool(self.rtc_regs[4] & 0x80) or day > 511
        day %= 512
        self.rtc_regs[3] = day & 255
        self.rtc_regs[4] = (day >> 8) | (0x80 if carry else 0)

    def _rtc_read(self) -> int:
        if not self.metadata["virtual_rtc"] or not 8 <= self.bank_high <= 12:
            raise GameRomRuntimeError("RTC source register selection is unavailable")
        values = self.rtc_regs if self.rtc_latched is None else self.rtc_latched
        return values[self.bank_high - 8]

    def _rtc_write(self, value: int) -> None:
        if not self.metadata["virtual_rtc"] or not 8 <= self.bank_high <= 12:
            raise GameRomRuntimeError("RTC source register selection is unavailable")
        index = self.bank_high - 8
        if index < 2 and value > 59:
            raise GameRomRuntimeError("RTC seconds/minutes write outside admitted range")
        if index == 2 and value > 23:
            raise GameRomRuntimeError("RTC hours write outside admitted range")
        self.rtc_regs[index] = value & (0xC1 if index == 4 else 0xFF)

    def read(self, address: int) -> int:
        address &= 65535
        if address < 0x8000:
            if address < 0x4000:
                bank = (self.bank_high << 5) if self.bank_mode and self.metadata["mapper"] == "mbc1" else 0
            else:
                bank = self.rom_bank | (self.bank_high << 5 if self.metadata["mapper"] == "mbc1" else 0)
            bank %= self.metadata["rom_banks"]
            return self.rom[bank * 16384 + (address & 0x3FFF)]
        if 0xA000 <= address < 0xC000:
            if not self.ram_enabled:
                return 255
            if self.metadata["virtual_rtc"] and 8 <= self.bank_high <= 12:
                return self._rtc_read()
            if not self.external_ram:
                return 255
            if self.metadata["mapper"] == "mbc2":
                return 0xF0 | (self.external_ram[(address - 0xA000) & 0x1FF] & 0x0F)
            bank = self.bank_high if self.metadata["mapper"] in ("mbc3", "mbc5") or self.bank_mode else 0
            return self.external_ram[(bank * 8192 + address - 0xA000) % len(self.external_ram)]
        if 0xE000 <= address < 0xFE00:
            address -= 0x2000
        if 0xFEA0 <= address < 0xFF00:
            return 255
        if address == 0xFF00:
            select = self.memory[address] & 0x30
            low = 15
            if not select & 0x10:
                low &= ~(self.buttons & 15)
            if not select & 0x20:
                low &= ~((self.buttons >> 4) & 15)
            return 0xC0 | select | low
        if address == 0xFF04:
            return self.divider >> 8
        if address == 0xFF41:
            ly = self.memory[0xFF44]
            mode = (
                0
                if not self.memory[0xFF40] & 0x80
                else (
                    1
                    if ly >= HEIGHT
                    else (2 if self.line_cycles < 80 else 3 if self.line_cycles < 252 else 0)
                )
            )
            return 0x80 | self.memory[address] & 0x78 | (4 if ly == self.memory[0xFF45] else 0) | mode
        return self.memory[address]

    def write(self, address: int, value: int) -> None:
        address, value = address & 65535, value & 255
        if address < 0x8000:
            mapper = self.metadata["mapper"]
            if mapper == "mbc1":
                if address < 0x2000:
                    self.ram_enabled = value & 15 == 10
                elif address < 0x4000:
                    self.rom_bank = (value & 31) or 1
                elif address < 0x6000:
                    self.bank_high = value & 3
                else:
                    self.bank_mode = value & 1
            elif mapper == "mbc2":
                # MBC2 address bit A8 qualifies RAM-enable vs bank-select.
                # 512 built-in four-bit registers mirror through A000-BFFF.
                if address < 0x2000 and not address & 0x100:
                    self.ram_enabled = value & 15 == 10
                elif 0x2000 <= address < 0x4000 and address & 0x100:
                    self.rom_bank = (value & 15) or 1
            elif mapper == "mbc3":
                if address < 0x2000:
                    self.ram_enabled = value & 15 == 10
                elif address < 0x4000:
                    self.rom_bank = (value & 127) or 1
                elif address < 0x6000:
                    if value > 3 and not (
                        self.metadata["virtual_rtc"] and 8 <= value <= 12
                    ):
                        raise GameRomRuntimeError("MBC3 unavailable RTC/RAM register")
                    self.bank_high = value
                elif self.metadata["virtual_rtc"]:
                    # Require an explicit 00 -> 01 command sequence.
                    # Other values cannot silently synthesize a latch edge.
                    if value in (0, 1):
                        if self.rtc_latch_prev == 0 and value == 1:
                            self.rtc_latched = list(self.rtc_regs)
                        self.rtc_latch_prev = value
                # RTC-free types ignore the latch command.
            elif mapper == "mbc5":
                if address < 0x2000:
                    self.ram_enabled = value & 15 == 10
                elif address < 0x3000:
                    self.rom_bank = (self.rom_bank & 256) | value
                elif address < 0x4000:
                    self.rom_bank = (self.rom_bank & 255) | ((value & 1) << 8)
                elif address < 0x6000:
                    self.bank_high = value & 15
            return
        if 0xA000 <= address < 0xC000:
            if self.ram_enabled and self.metadata["virtual_rtc"] and 8 <= self.bank_high <= 12:
                self._rtc_write(value)
                return
            if self.external_ram and self.ram_enabled:
                if self.metadata["mapper"] == "mbc2":
                    self.external_ram[(address - 0xA000) & 0x1FF] = value & 0x0F
                    return
                bank = self.bank_high if self.metadata["mapper"] in ("mbc3", "mbc5") or self.bank_mode else 0
                self.external_ram[(bank * 8192 + address - 0xA000) % len(self.external_ram)] = value
            return
        if 0xE000 <= address < 0xFE00:
            address -= 0x2000
        if 0xFEA0 <= address < 0xFF00 or address == 0xFF44:
            return
        if address == 0xFF04:
            self.divider = 0
            return
        if address == 0xFF00:
            old = self.read(address)
            self.memory[address] = value & 0x30
            if old & ~self.read(address) & 15:
                self.memory[0xFF0F] |= 0x10
            return
        if address == 0xFF46:
            self.memory[address] = value
            for i in range(160):
                self.memory[0xFE00 + i] = self.read(value * 256 + i)
            return
        if address == 0xFF40 and not value & 0x80:
            self.memory[0xFF44] = self.line_cycles = 0
        if address == 0xFF41:
            value &= 0x78
        self.memory[address] = value

    def set_buttons(self, buttons: tuple[str, ...]) -> None:
        if not isinstance(buttons, tuple) or any(button not in BUTTONS for button in buttons):
            raise GameRomRuntimeError("Unknown DMG button")
        old = self.read(0xFF00)
        self.buttons = sum(1 << BUTTONS.index(button) for button in set(buttons))
        if old & ~self.read(0xFF00) & 15:
            self.memory[0xFF0F] |= 0x10
        if self.buttons:
            self.stopped = False

    def _fetch(self) -> int:
        result = self.read(self.pc)
        if self.halt_bug:
            self.halt_bug = False
        else:
            self.pc = self.pc + 1 & 65535
        return result

    def _word(self) -> int:
        low = self._fetch()
        return low | self._fetch() << 8

    def _pair(self, index: int) -> int:
        if index == 3:
            return self.sp
        high, low = ((self.b, self.c), (self.d, self.e), (self.h, self.l))[index]
        return high << 8 | low

    def _set_pair(self, index: int, value: int) -> None:
        value &= 65535
        high, low = value >> 8, value & 255
        if index == 0:
            self.b, self.c = high, low
        elif index == 1:
            self.d, self.e = high, low
        elif index == 2:
            self.h, self.l = high, low
        else:
            self.sp = value

    def _reg(self, index: int) -> int:
        if index == 6:
            return self.read(self._pair(2))
        return (self.b, self.c, self.d, self.e, self.h, self.l, 0, self.a)[index]

    def _set_reg(self, index: int, value: int) -> None:
        value &= 255
        if index == 6:
            self.write(self._pair(2), value)
        else:
            setattr(self, ("b", "c", "d", "e", "h", "l", "", "a")[index], value)

    def _push(self, value: int) -> None:
        self.sp = self.sp - 1 & 65535
        self.write(self.sp, value >> 8)
        self.sp = self.sp - 1 & 65535
        self.write(self.sp, value & 255)

    def _pop(self) -> int:
        low = self.read(self.sp)
        self.sp = self.sp + 1 & 65535
        high = self.read(self.sp)
        self.sp = self.sp + 1 & 65535
        return low | high << 8

    def _condition(self, index: int) -> bool:
        return (not bool(self.f & Z), bool(self.f & Z), not bool(self.f & C), bool(self.f & C))[index]

    def _alu(self, operation: int, value: int) -> None:
        old, carry = self.a, int(bool(self.f & C))
        if operation in (0, 1):
            extra = carry if operation == 1 else 0
            result = old + value + extra
            self.f = (
                (Z if result & 255 == 0 else 0)
                | (H if (old & 15) + (value & 15) + extra > 15 else 0)
                | (C if result > 255 else 0)
            )
            self.a = result & 255
        elif operation in (2, 3, 7):
            extra = carry if operation == 3 else 0
            result = old - value - extra
            self.f = (
                N
                | (Z if result & 255 == 0 else 0)
                | (H if (old & 15) < (value & 15) + extra else 0)
                | (C if result < 0 else 0)
            )
            if operation != 7:
                self.a = result & 255
        else:
            self.a = old & value if operation == 4 else old ^ value if operation == 5 else old | value
            self.f = (Z if self.a == 0 else 0) | (H if operation == 4 else 0)

    def _cb(self) -> int:
        opcode = self._fetch()
        group, operation, target = opcode >> 6, opcode >> 3 & 7, opcode & 7
        value = self._reg(target)
        if group == 1:
            self.f = self.f & C | H | (Z if not value & 1 << operation else 0)
            return 12 if target == 6 else 8
        if group in (2, 3):
            result = value & ~(1 << operation) if group == 2 else value | 1 << operation
        else:
            old_carry = int(bool(self.f & C))
            if operation == 0:
                carry, result = value >> 7, (value << 1 | value >> 7) & 255
            elif operation == 1:
                carry, result = value & 1, value >> 1 | (value & 1) << 7
            elif operation == 2:
                carry, result = value >> 7, (value << 1 | old_carry) & 255
            elif operation == 3:
                carry, result = value & 1, value >> 1 | old_carry << 7
            elif operation == 4:
                carry, result = value >> 7, value << 1 & 255
            elif operation == 5:
                carry, result = value & 1, value >> 1 | value & 0x80
            elif operation == 6:
                carry, result = 0, value << 4 & 255 | value >> 4
            else:
                carry, result = value & 1, value >> 1
            self.f = (Z if result == 0 else 0) | (C if carry else 0)
        self._set_reg(target, result)
        return 16 if target == 6 else 8

    def _execute(self) -> int:
        opcode_pc = self.pc
        opcode = self._fetch()
        if 0x40 <= opcode < 0x80:
            if opcode == 0x76:
                if not self.ime and self.memory[0xFFFF] & self.memory[0xFF0F] & 31:
                    self.halt_bug = True
                else:
                    self.halted = True
                return 4
            self._set_reg(opcode >> 3 & 7, self._reg(opcode & 7))
            return 8 if (opcode & 7 == 6 or opcode >> 3 & 7 == 6) else 4
        if 0x80 <= opcode < 0xC0:
            self._alu(opcode >> 3 & 7, self._reg(opcode & 7))
            return 8 if opcode & 7 == 6 else 4
        if opcode < 0x40:
            pair = opcode >> 4
            if opcode & 15 == 1:
                self._set_pair(pair, self._word())
                return 12
            if opcode & 15 in (3, 11):
                self._set_pair(pair, self._pair(pair) + (1 if opcode & 15 == 3 else -1))
                return 8
            if opcode & 15 == 9:
                old, value = self._pair(2), self._pair(pair)
                self.f = (
                    self.f & Z
                    | (H if (old & 0xFFF) + (value & 0xFFF) > 0xFFF else 0)
                    | (C if old + value > 65535 else 0)
                )
                self._set_pair(2, old + value)
                return 8
            if opcode & 7 in (4, 5):
                index = opcode >> 3 & 7
                old = self._reg(index)
                decrement = opcode & 7 == 5
                result = old + (-1 if decrement else 1) & 255
                half = old & 15 == (0 if decrement else 15)
                self.f = self.f & C | (Z if result == 0 else 0) | (N if decrement else 0) | (H if half else 0)
                self._set_reg(index, result)
                return 12 if index == 6 else 4
            if opcode & 7 == 6:
                index = opcode >> 3 & 7
                self._set_reg(index, self._fetch())
                return 12 if index == 6 else 8
            if opcode & 7 == 2:
                address = self._pair(min(2, pair))
                if opcode & 8:
                    self.a = self.read(address)
                else:
                    self.write(address, self.a)
                if pair >= 2:
                    self._set_pair(2, address + (1 if pair == 2 else -1))
                return 8
            if opcode == 0:
                return 4
            if opcode == 8:
                address = self._word()
                self.write(address, self.sp & 255)
                self.write(address + 1, self.sp >> 8)
                return 20
            if opcode == 0x10:
                self._fetch()
                self.stopped = True
                return 4
            if opcode == 0x18 or opcode in (0x20, 0x28, 0x30, 0x38):
                displacement = self._fetch()
                if opcode == 0x18 or self._condition((opcode - 0x20) // 8):
                    self.pc = self.pc + (displacement if displacement < 128 else displacement - 256) & 65535
                    return 12
                return 8
            if opcode in (7, 15, 23, 31):
                old_carry = int(bool(self.f & C))
                if opcode in (7, 23):
                    carry = self.a >> 7
                    self.a = self.a << 1 & 255 | (carry if opcode == 7 else old_carry)
                else:
                    carry = self.a & 1
                    self.a = self.a >> 1 | (carry if opcode == 15 else old_carry) << 7
                self.f = C if carry else 0
                return 4
            if opcode == 0x27:
                adjustment = 0
                carry = bool(self.f & C)
                if self.f & N:
                    adjustment = (0x60 if carry else 0) | (6 if self.f & H else 0)
                    self.a = self.a - adjustment & 255
                else:
                    if carry or self.a > 0x99:
                        adjustment |= 0x60
                        carry = True
                    if self.f & H or self.a & 15 > 9:
                        adjustment |= 6
                    self.a = self.a + adjustment & 255
                self.f = self.f & N | (Z if self.a == 0 else 0) | (C if carry else 0)
                return 4
            if opcode == 0x2F:
                self.a ^= 255
                self.f |= N | H
                return 4
            if opcode in (0x37, 0x3F):
                carry = opcode == 0x37 or not self.f & C
                self.f = self.f & Z | (C if carry else 0)
                return 4
        if opcode == 0xCB:
            return self._cb()
        if opcode in (0xC0, 0xC8, 0xD0, 0xD8):
            if self._condition((opcode >> 3) & 3):
                self.pc = self._pop()
                return 20
            return 8
        if opcode in (0xC1, 0xD1, 0xE1, 0xF1):
            value = self._pop()
            pair = (opcode >> 4) - 12
            if pair == 3:
                self.a, self.f = value >> 8, value & 0xF0
            else:
                self._set_pair(pair, value)
            return 12
        if opcode in (0xC2, 0xCA, 0xD2, 0xDA, 0xC3):
            address = self._word()
            if opcode == 0xC3 or self._condition(opcode >> 3 & 3):
                self.pc = address
                return 16
            return 12
        if opcode in (0xC4, 0xCC, 0xD4, 0xDC, 0xCD):
            address = self._word()
            if opcode == 0xCD or self._condition(opcode >> 3 & 3):
                self._push(self.pc)
                self.pc = address
                return 24
            return 12
        if opcode in (0xC5, 0xD5, 0xE5, 0xF5):
            pair = (opcode >> 4) - 12
            self._push(self.a << 8 | self.f if pair == 3 else self._pair(pair))
            return 16
        if opcode & 7 == 6:
            self._alu(opcode >> 3 & 7, self._fetch())
            return 8
        if opcode & 7 == 7:
            self._push(self.pc)
            self.pc = opcode & 0x38
            return 16
        if opcode in (0xC9, 0xD9):
            self.pc = self._pop()
            if opcode == 0xD9:
                self.ime, self.ime_delay = True, 0
            return 16
        if opcode in (0xE0, 0xF0, 0xE2, 0xF2):
            address = 0xFF00 | (self.c if opcode & 2 else self._fetch())
            if opcode & 0x10:
                self.a = self.read(address)
            else:
                self.write(address, self.a)
            return 8 if opcode & 2 else 12
        if opcode in (0xE8, 0xF8):
            immediate = self._fetch()
            result = self.sp + (immediate if immediate < 128 else immediate - 256)
            self.f = (H if (self.sp & 15) + (immediate & 15) > 15 else 0) | (
                C if (self.sp & 255) + immediate > 255 else 0
            )
            if opcode == 0xE8:
                self.sp = result & 65535
            else:
                self._set_pair(2, result)
            return 16 if opcode == 0xE8 else 12
        if opcode == 0xE9:
            self.pc = self._pair(2)
            return 4
        if opcode in (0xEA, 0xFA):
            address = self._word()
            if opcode == 0xFA:
                self.a = self.read(address)
            else:
                self.write(address, self.a)
            return 16
        if opcode == 0xF9:
            self.sp = self._pair(2)
            return 8
        if opcode == 0xF3:
            self.ime, self.ime_delay = False, 0
            return 4
        if opcode == 0xFB:
            if not self.ime and not self.ime_delay:
                self.ime_delay = 2
            return 4
        raise GameRomRuntimeError(f"Unsupported/invalid opcode 0x{opcode:02x} at 0x{opcode_pc:04x}")

    def _tile_pixel(self, tile: int, x: int, y: int, unsigned: bool) -> int:
        if unsigned:
            address = 0x8000 + tile * 16
        else:
            address = 0x9000 + (tile if tile < 128 else tile - 256) * 16
        address += y * 2
        bit = 7 - x
        return self.memory[address] >> bit & 1 | (self.memory[address + 1] >> bit & 1) << 1

    def _draw_line(self, line: int) -> None:
        lcd = self.memory[0xFF40]
        row = [0] * WIDTH
        if lcd & 1:
            for x in range(WIDTH):
                window = lcd & 0x20 and line >= self.memory[0xFF4A] and x >= self.memory[0xFF4B] - 7
                if window:
                    tx, ty = x - self.memory[0xFF4B] + 7, line - self.memory[0xFF4A]
                    tilemap = 0x9C00 if lcd & 0x40 else 0x9800
                else:
                    tx, ty = (x + self.memory[0xFF43]) & 255, (line + self.memory[0xFF42]) & 255
                    tilemap = 0x9C00 if lcd & 8 else 0x9800
                tile = self.memory[tilemap + (ty // 8) * 32 + tx // 8]
                row[x] = self._tile_pixel(tile, tx & 7, ty & 7, bool(lcd & 0x10))
        for x, pixel in enumerate(row):
            self.framebuffer[line * WIDTH + x] = 255 - (self.memory[0xFF47] >> (pixel * 2) & 3) * 85
        if not lcd & 2:
            return
        height = 16 if lcd & 4 else 8
        sprites = []
        for index in range(40):
            base = 0xFE00 + index * 4
            sy, sx = self.memory[base] - 16, self.memory[base + 1] - 8
            if sy <= line < sy + height:
                sprites.append((sx, index, sy, base))
                if len(sprites) == 10:
                    break
        occupied = set()
        for sx, _, sy, base in sorted(sprites):
            tile, flags = self.memory[base + 2], self.memory[base + 3]
            py = line - sy
            if flags & 0x40:
                py = height - 1 - py
            if height == 16:
                tile = (tile & 0xFE) + py // 8
            palette = self.memory[0xFF49 if flags & 0x10 else 0xFF48]
            for px in range(8):
                x = sx + px
                if not 0 <= x < WIDTH or x in occupied:
                    continue
                color = self._tile_pixel(tile, 7 - px if flags & 0x20 else px, py & 7, True)
                if not color:
                    continue
                occupied.add(x)
                if not flags & 0x80 or row[x] == 0:
                    self.framebuffer[line * WIDTH + x] = 255 - (palette >> (color * 2) & 3) * 85

    def _advance(self, cycles: int) -> None:
        for _ in range(cycles):
            previous = self.divider
            self.divider = (self.divider + 1) & 65535
            control = self.memory[0xFF07]
            bit = (9, 3, 5, 7)[control & 3]
            if control & 4 and previous & 1 << bit and not self.divider & 1 << bit:
                if self.memory[0xFF05] == 255:
                    self.memory[0xFF05] = self.memory[0xFF06]
                    self.memory[0xFF0F] |= 4
                else:
                    self.memory[0xFF05] += 1
        self.cycles += cycles
        self._rtc_advance(cycles)
        if not self.memory[0xFF40] & 0x80:
            self.stat_line = False
            return
        self.line_cycles += cycles
        while self.line_cycles >= 456:
            self.line_cycles -= 456
            line = self.memory[0xFF44]
            if line < HEIGHT:
                self._draw_line(line)
            line = (line + 1) % 154
            self.memory[0xFF44] = line
            if line == HEIGHT:
                self.frames += 1
                self.memory[0xFF0F] |= 1
        status = self.read(0xFF41)
        mode = status & 3
        requested = bool(
            (status & 4 and status & 0x40)
            or (mode == 0 and status & 8)
            or (mode == 1 and status & 0x10)
            or (mode == 2 and status & 0x20)
        )
        if requested and not self.stat_line:
            self.memory[0xFF0F] |= 2
        self.stat_line = requested

    def instruction(self) -> int:
        pending = self.memory[0xFFFF] & self.memory[0xFF0F] & 31
        if pending:
            self.halted = False
            if self.ime:
                bit = (pending & -pending).bit_length() - 1
                self.ime, self.ime_delay = False, 0
                self.memory[0xFF0F] &= ~(1 << bit)
                self._push(self.pc)
                self.pc = 0x40 + bit * 8
                self._advance(20)
                return 20
        if self.halted or self.stopped:
            self._advance(4)
            return 4
        cycles = self._execute()
        self.instructions += 1
        if self.ime_delay:
            self.ime_delay -= 1
            if not self.ime_delay:
                self.ime = True
        self._advance(cycles)
        return cycles

    def run(self, cycles: int = 1824) -> dict[str, int]:
        if type(cycles) is not int or not 4 <= cycles <= FRAME_CYCLES * 2:
            raise GameRomRuntimeError("ROM step cycle budget is invalid")
        start = self.cycles
        while self.cycles - start < cycles:
            self.instruction()
        return {
            "cycles": self.cycles - start,
            "instructions": self.instructions,
            "frames": self.frames,
            "pc": self.pc,
        }

    def snapshot(self) -> dict[str, Any]:
        names = (
            "a",
            "f",
            "b",
            "c",
            "d",
            "e",
            "h",
            "l",
            "sp",
            "pc",
            "ime",
            "ime_delay",
            "halted",
            "stopped",
            "halt_bug",
            "rom_bank",
            "bank_high",
            "bank_mode",
            "ram_enabled",
            "buttons",
            "cycles",
            "frames",
            "divider",
            "line_cycles",
            "instructions",
            "stat_line",
        )
        result = {
            "schema_version": 1,
            "rom_digest": self.metadata["rom_digest"],
            "registers": {name: getattr(self, name) for name in names},
            "memory": base64.b64encode(self.memory).decode(),
            "external_ram": base64.b64encode(self.external_ram).decode(),
            "framebuffer": base64.b64encode(self.framebuffer).decode(),
        }
        if self.metadata["virtual_rtc"]:
            result["schema_version"] = 2
            result["rtc"] = {
                "live": list(self.rtc_regs),
                "latched": None if self.rtc_latched is None else list(self.rtc_latched),
                "previous_latch_bit": self.rtc_latch_prev,
                "cycle_remainder": self.rtc_cycle_remainder,
                "time_basis": "emulated_cpu_cycles_only",
            }
        result["state_digest"] = _digest(result)
        return result

    def restore(self, snapshot: Mapping[str, Any]) -> None:
        if not isinstance(snapshot, Mapping):
            raise GameRomRuntimeError("ROM snapshot is not an object")
        value = dict(snapshot)
        digest = value.pop("state_digest", None)
        keys = {"schema_version", "rom_digest", "registers", "memory", "external_ram", "framebuffer"}
        if self.metadata["virtual_rtc"]:
            keys.add("rtc")
        if (
            set(value) != keys
            or type(value.get("schema_version")) is not int
            or len(json.dumps(value)) > 400000
            or digest != _digest(value)
            or value.get("schema_version") != (2 if self.metadata["virtual_rtc"] else 1)
            or value.get("rom_digest") != self.metadata["rom_digest"]
        ):
            raise GameRomRuntimeError("ROM snapshot identity, size or digest is invalid")
        expected = self.snapshot()["registers"]
        registers = value.get("registers")
        if not isinstance(registers, dict) or set(registers) != set(expected):
            raise GameRomRuntimeError("ROM snapshot register schema is invalid")
        bounds = {
            "a": 255,
            "f": 240,
            "b": 255,
            "c": 255,
            "d": 255,
            "e": 255,
            "h": 255,
            "l": 255,
            "sp": 65535,
            "pc": 65535,
            "ime_delay": 2,
            "rom_bank": (
                511 if self.metadata["mapper"] == "mbc5"
                else 127 if self.metadata["mapper"] == "mbc3"
                else 15 if self.metadata["mapper"] == "mbc2"
                else 31
            ),
            "bank_high": 15 if self.metadata["mapper"] == "mbc5" else 12 if self.metadata["virtual_rtc"] else 3,
            "bank_mode": 1,
            "buttons": 255,
            "cycles": 2**53 - 1,
            "frames": 2**40,
            "divider": 65535,
            "line_cycles": 455,
            "instructions": 2**53 - 1,
        }
        for name, current in expected.items():
            item = registers[name]
            if isinstance(current, bool):
                if type(item) is not bool:
                    raise GameRomRuntimeError("ROM snapshot boolean is invalid")
            elif type(item) is not int or not 0 <= item <= bounds[name]:
                raise GameRomRuntimeError("ROM snapshot register is outside bounds")
        if (
            registers["f"] & 15
            or (registers["rom_bank"] == 0 and self.metadata["mapper"] != "mbc5")
            or (self.metadata["mapper"] != "mbc1" and registers["bank_mode"] != 0)
            or (self.metadata["mapper"] == "mbc2" and registers["bank_high"] != 0)
            or (self.metadata["virtual_rtc"] and registers["bank_high"] in (4, 5, 6, 7))
        ):
            raise GameRomRuntimeError("ROM snapshot flag/bank is invalid")
        if registers["instructions"] * 4 > registers["cycles"]:
            raise GameRomRuntimeError("ROM snapshot CPU counters are inconsistent")
        decoded = {}
        for name, length in (
            ("memory", 65536),
            ("external_ram", len(self.external_ram)),
            ("framebuffer", WIDTH * HEIGHT),
        ):
            raw = value.get(name)
            if not isinstance(raw, str) or len(raw) > ((length + 2) // 3) * 4:
                raise GameRomRuntimeError("ROM snapshot memory encoding is invalid")
            try:
                data = base64.b64decode(raw, validate=True)
            except (ValueError, TypeError) as exc:
                raise GameRomRuntimeError("ROM snapshot memory encoding is invalid") from exc
            if len(data) != length:
                raise GameRomRuntimeError("ROM snapshot memory length is invalid")
            decoded[name] = bytearray(data)
        if decoded["memory"][0xFF44] > 153 or any(
            pixel not in (0, 85, 170, 255) for pixel in decoded["framebuffer"]
        ):
            raise GameRomRuntimeError("ROM snapshot raster state is invalid")
        if self.metadata["mapper"] == "mbc2" and any(
            byte & 0xF0 for byte in decoded["external_ram"]
        ):
            raise GameRomRuntimeError("MBC2 state contains data outside four-bit internal RAM")
        validated_rtc = None
        if self.metadata["virtual_rtc"]:
            rtc = value["rtc"]
            if not isinstance(rtc, dict) or set(rtc) != {
                "live", "latched", "previous_latch_bit", "cycle_remainder", "time_basis"
            } or rtc["time_basis"] != "emulated_cpu_cycles_only":
                raise GameRomRuntimeError("MBC3 source RTC snapshot schema is invalid")

            def valid_clock(values: Any) -> bool:
                return (
                    isinstance(values, list) and len(values) == 5
                    and all(type(item) is int for item in values)
                    and 0 <= values[0] < 60 and 0 <= values[1] < 60
                    and 0 <= values[2] < 24 and 0 <= values[3] <= 255
                    and 0 <= values[4] <= 0xC1
                    and values[4] & ~0xC1 == 0
                )

            if (
                not valid_clock(rtc["live"])
                or rtc["latched"] is not None and not valid_clock(rtc["latched"])
                or type(rtc["previous_latch_bit"]) is not int
                or rtc["previous_latch_bit"] not in (0, 1)
                or type(rtc["cycle_remainder"]) is not int
                or not 0 <= rtc["cycle_remainder"] < RTC_CYCLES_PER_SECOND
            ):
                raise GameRomRuntimeError("MBC3 virtual RTC clock state is invalid")
            validated_rtc = (
                list(rtc["live"]),
                None if rtc["latched"] is None else list(rtc["latched"]),
                rtc["previous_latch_bit"], rtc["cycle_remainder"],
            )
        for name, item in registers.items():
            setattr(self, name, item)
        self.memory, self.external_ram, self.framebuffer = (
            decoded["memory"],
            decoded["external_ram"],
            decoded["framebuffer"],
        )
        if validated_rtc is not None:
            (self.rtc_regs, self.rtc_latched,
             self.rtc_latch_prev, self.rtc_cycle_remainder) = validated_rtc

    def preview(self) -> dict[str, Any]:
        return {
            "width": WIDTH,
            "height": HEIGHT,
            "format": "gray8",
            "pixels_base64": base64.b64encode(self.framebuffer).decode(),
            "frame": self.frames,
            "cycle": self.cycles,
            "experimental": True,
        }


class GameBoyROMEnvironment:
    """Measured exploration environment; visual change is not game success."""

    def __init__(self, rom: bytes, *, max_steps: int = 256, cycles_per_step: int = 1824) -> None:
        if type(max_steps) is not int or not 1 <= max_steps <= 4096:
            raise GameRomRuntimeError("ROM episode step bound is invalid")
        if type(cycles_per_step) is not int or not 4 <= cycles_per_step <= FRAME_CYCLES * 2:
            raise GameRomRuntimeError("ROM environment cycle budget is invalid")
        self.rom = rom
        self.metadata = inspect_dmg_cartridge(rom)
        self.max_steps, self.cycles_per_step = max_steps, cycles_per_step
        self.machine = GameBoyMachine(rom)
        self.steps, self.seed, self.visual_change = 0, 0, 0.0
        self.environment_digest = _digest(
            {
                "rom": self.metadata["rom_digest"],
                "max_steps": max_steps,
                "cycles_per_step": cycles_per_step,
                "runtime": "dmg_cpu_raster_v1",
                "code_digest": RUNTIME_CODE_DIGEST,
                "python_runtime": sys.version,
                "reset_seed_semantics": "actual_idle_phase_0_to_3_frames_of_the_same_cartridge",
            }
        )

    @property
    def spec(self):
        from .game_learning_runtime import GameEnvironmentSpec

        return GameEnvironmentSpec(
            environment_id="game_boy:rom:" + self.metadata["rom_digest"],
            environment_digest=self.environment_digest,
            actions=ACTIONS,
            observation_bins={
                "pc": (0x100, 0x4000, 0x8000, 0xC000),
                "a": (64.0, 128.0, 192.0),
                "ly": (36.0, 72.0, 108.0, 144.0),
                "screen_mean": (64.0, 128.0, 192.0),
                "visual_change": (0.01, 0.1, 0.5),
                "step_fraction": (0.25, 0.5, 0.75),
            },
            reward_components=("visual_change",),
            max_episode_steps=self.max_steps,
        )

    def _observation(self) -> dict[str, float]:
        return {
            "pc": float(self.machine.pc),
            "a": float(self.machine.a),
            "ly": float(self.machine.memory[0xFF44]),
            "screen_mean": sum(self.machine.framebuffer) / len(self.machine.framebuffer),
            "visual_change": self.visual_change,
            "step_fraction": self.steps / self.max_steps,
        }

    def reset(self, seed: int = 0) -> dict[str, float]:
        if type(seed) is not int or not 0 <= seed <= 2**63 - 1:
            raise GameRomRuntimeError("ROM seed is invalid")
        self.machine = GameBoyMachine(self.rom)
        self.steps, self.seed, self.visual_change = 0, seed, 0.0
        remaining = seed % 4 * FRAME_CYCLES
        while remaining:
            budget = min(remaining, FRAME_CYCLES * 2)
            self.machine.run(budget)
            remaining -= budget
        return self._observation()

    def step(self, action: str):
        from .game_learning_runtime import EpisodeStep

        if action not in ACTIONS or self.steps >= self.max_steps:
            raise GameRomRuntimeError("ROM action or terminal episode state is invalid")
        before = bytes(self.machine.framebuffer)
        buttons = () if action == "idle" else tuple(action.split("_"))
        self.machine.set_buttons(buttons)
        measured = self.machine.run(self.cycles_per_step)
        self.steps += 1
        self.visual_change = sum(
            left != right for left, right in zip(before, self.machine.framebuffer, strict=True)
        ) / len(before)
        return EpisodeStep(
            observation=self._observation(),
            reward_components={"visual_change": self.visual_change},
            terminated=False,
            truncated=self.steps >= self.max_steps,
            info={
                **measured,
                "reward_semantics": "visual exploration only; game success is unknown",
                "rom_digest": self.metadata["rom_digest"],
            },
        )

    def snapshot(self) -> dict[str, Any]:
        result = {
            "schema_version": 1,
            "environment_digest": self.environment_digest,
            "steps": self.steps,
            "seed": self.seed,
            "visual_change": self.visual_change,
            "machine": self.machine.snapshot(),
        }
        result["state_digest"] = _digest(result)
        return result

    def restore(self, snapshot: Mapping[str, Any]) -> dict[str, float]:
        if not isinstance(snapshot, Mapping):
            raise GameRomRuntimeError("ROM environment snapshot is invalid")
        value = dict(snapshot)
        digest = value.pop("state_digest", None)
        if (
            set(value)
            != {"schema_version", "environment_digest", "steps", "seed", "visual_change", "machine"}
            or type(value.get("schema_version")) is not int
            or len(json.dumps(value)) > 410000
            or digest != _digest(value)
            or value.get("schema_version") != 1
            or value.get("environment_digest") != self.environment_digest
        ):
            raise GameRomRuntimeError("ROM environment snapshot identity is invalid")
        steps, seed, change = value.get("steps"), value.get("seed"), value.get("visual_change")
        if (
            type(steps) is not int
            or not 0 <= steps <= self.max_steps
            or type(seed) is not int
            or not 0 <= seed <= 2**63 - 1
            or type(change) not in (float, int)
            or not 0 <= change <= 1
        ):
            raise GameRomRuntimeError("ROM environment snapshot counters are invalid")
        machine = GameBoyMachine(self.rom)
        machine.restore(value.get("machine"))
        if machine.cycles < steps * self.cycles_per_step:
            raise GameRomRuntimeError("ROM environment snapshot step counters are inconsistent")
        self.machine, self.steps, self.seed, self.visual_change = machine, steps, seed, float(change)
        return self._observation()

    def preview(self) -> dict[str, Any]:
        return self.machine.preview()
