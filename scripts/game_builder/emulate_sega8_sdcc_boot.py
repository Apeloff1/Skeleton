"""Instruction-level boot smoke test for actual compiled original SMS/Game Gear ROMs.

An independent Z80 interpreter runs *cartridge bytes*, not host-translated C.
A deliberately narrow Mode-4/PSG/controller test bench observes game startup.
It is NOT a cycle-perfect emulator, a complete game replay, or physical
hardware certification. Fail closed on unknown device I/O or exhausted budget.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from skeleton.ai.game_builder.sega_8bit_rom import validate_rom
from skeleton.ai.game_builder.native_release_intake import _read_bounded

MAX_INSTRUCTIONS = 3_000_000
DEFAULT_FRAME_INSTRUCTIONS = 25000
MAX_FRAMES = 128
# NTSC Sega VDP scanline clock: 228 Z80 T-states per line, 262 lines/frame.
# Scanline counter 0x00..0xDA then 0xD5..0xFF on 192-line NTSC consoles.
_TSTATES_PER_LINE = 228
_LINES_PER_FRAME = 262
_FRAME_TSTATES = _TSTATES_PER_LINE * _LINES_PER_FRAME
_MAP_NAMES = {"sega_master_system": "sms", "sega_game_gear": "gg"}


class SDCCSegaBootError(ValueError):
    """Compiled original Z80 game failed hardware-facing boot acceptance."""


class Sega8Machine:
    """Unbanked 32KiB ROM, mirrored 8KiB RAM, VDP, PSG and joypad ports."""

    def __init__(self, rom: bytes, *, target: str):
        if target not in _MAP_NAMES or len(rom) != 32768:
            raise SDCCSegaBootError("typed SMS or Game Gear 32KB ROM required")
        self.rom = rom
        self.target = target
        self.ram = bytearray(8192)
        self.vram = bytearray(16384)
        self.cram = bytearray(64)
        self.registers = bytearray(16)
        self.vdp_write_addr = 0
        self.vdp_mode = "vram"
        self.pending_vdp_address: int | None = None
        self.controller = 0xFF
        self.controller_high = 0xFF
        self.gg_start = 0xFF
        self.frame_ready = False
        self.vdp_writes = 0
        self.cram_writes = 0
        self.psg_writes = 0
        self.last_psg_data: int | None = None
        self.vdp_read_status = 0
        self.vdp_register_updates = 0
        self.unexpected_port_reads = 0
        self.io_control_writes = 0
        self.interrupts_issued = 0
        self.io_reads = 0
        # Count *guest* controller-port reads while a real physical button
        # signal is asserted. Playback cannot pass by host-writing game RAM.
        self.active_joypad_reads = 0
        self.active_joypad_bits_observed = 0
        self.z80_tstates = 0
        self.vcounter_reads = 0
        self.vcounter_b0_seen = False
        self.vcounter_c8_seen = False

    def read(self, address: int) -> int:
        address &= 0xFFFF
        if address < 0x8000:
            return self.rom[address]
        if address < 0xC000:
            return 0xFF
        return self.ram[(address - 0xC000) & 0x1FFF]

    def write(self, address: int, value: int) -> None:
        address &= 0xFFFF
        if address < 0xC000:
            raise SDCCSegaBootError(
                f"compiled Z80 attempted write to immutable cartridge/bus at {address:#06x}"
            )
        self.ram[(address - 0xC000) & 0x1FFF] = value & 0xFF

    @property
    def vcounter(self) -> int:
        """Actual port 0x7E value for the current NTSC display scanline."""
        scanline = (self.z80_tstates // _TSTATES_PER_LINE) % _LINES_PER_FRAME
        if scanline < 219:
            return scanline
        return 0xD5 + (scanline - 219)

    def advance_tstates(self, value: int) -> None:
        if type(value) is not int or not 1 <= value <= 64:
            raise SDCCSegaBootError("invalid actual Z80 instruction-cycle count")
        self.z80_tstates += value

    def read_port(self, port: int) -> int:
        low = port & 0xFF
        self.io_reads += 1
        if low == 0xDC:
            if self.controller != 0xFF:
                self.active_joypad_reads += 1
                self.active_joypad_bits_observed |= (~self.controller) & 0x0F
            return self.controller
        if low == 0xDD:
            return self.controller_high
        if low == 0x00 and self.target == "sega_game_gear":
            return self.gg_start
        if low == 0xBF:
            self.pending_vdp_address = None
            self.vdp_read_status += 1
            status = 0x80 if self.frame_ready else 0x00
            self.frame_ready = False
            return status
        if low == 0x7E:
            # devkitSMS SMS_init() busy-waits for lines 0xB0 and 0xC8
            # *before* VDP register initialization or EI. A constant FF
            # deadlocks both otherwise playable original cartridge ports.
            self.vcounter_reads += 1
            current = self.vcounter
            if current == 0xB0:
                self.vcounter_b0_seen = True
            if current == 0xC8:
                self.vcounter_c8_seen = True
            return current
        if low in (0xBE, 0x7F):
            return 0xFF
        if low in (0x3F, 0x3E):
            return 0xFF
        raise SDCCSegaBootError(f"unexpected actual Z80 IN port {low:#04x}")

    def write_port(self, port: int, value: int) -> None:
        low = port & 0xFF
        value &= 0xFF
        if low in (0x7E, 0x7F):
            self.psg_writes += 1
            self.last_psg_data = value
            return
        if low in (0x3E, 0x3F):
            self.io_control_writes += 1
            return
        if low == 0x06 and self.target == "sega_game_gear":
            self.io_control_writes += 1
            return
        if low == 0xBF:
            if self.pending_vdp_address is None:
                self.pending_vdp_address = value
                return
            first = self.pending_vdp_address
            self.pending_vdp_address = None
            mode = value & 0xC0
            if mode == 0x80:
                self.registers[value & 15] = first
                self.vdp_register_updates += 1
                return
            self.vdp_write_addr = ((value & 0x3F) << 8) | first
            self.vdp_mode = "cram" if mode == 0xC0 else (
                "vram" if mode == 0x40 else "read"
            )
            return
        if low == 0xBE:
            if self.pending_vdp_address is not None:
                raise SDCCSegaBootError("VDP data written during incomplete VDP command")
            if self.vdp_mode == "vram":
                self.vram[self.vdp_write_addr & 0x3FFF] = value
                self.vdp_writes += 1
                self.vdp_write_addr = (self.vdp_write_addr + 1) & 0x3FFF
                return
            if self.vdp_mode == "cram":
                if self.target == "sega_master_system" and value > 0x3F:
                    raise SDCCSegaBootError("Master System CRAM exceeds real 6-bit limit")
                span = 64 if self.target == "sega_game_gear" else 32
                self.cram[self.vdp_write_addr % span] = value
                self.vdp_write_addr = (self.vdp_write_addr + 1) % span
                self.cram_writes += 1
                return
            raise SDCCSegaBootError("VDP wrote into unsupported read mode")
        raise SDCCSegaBootError(f"unexpected actual Z80 OUT port {low:#04x}")

    def observed_background(self) -> dict[str, object]:
        base = (self.registers[2] & 0x0E) << 10
        left, top, hud = (
            (0, 2, 0) if self.target == "sega_master_system" else (6, 5, 3)
        )
        def tile(x: int, y: int) -> int:
            offset = (base + y * 64 + x * 2) & 0x3FFF
            return self.vram[offset]
        # The game draws the HUD at the fixed location for this target.
        digits = [tile(left + x, hud) for x in (13, 14, 15, 16)]
        companion = tile(left + 18, hud)
        hero = [
            (x, y) for y in range(top, top + 15)
            for x in range(left, left + 17) if tile(x, y) in (5, 16)
        ]
        return {
            "name_table_base": base,
            "hero_screen_tile_positions": hero,
            "score_digit_tiles": digits,
            "companion_expression_tile": companion,
            "background_display_enabled": bool(self.registers[1] & 0x40),
        }

    def observe_boot(self) -> dict[str, object]:
        background = self.observed_background()
        expected_digits = [6, 6, 6, 6]
        if self.vdp_writes < 1000 or self.cram_writes < (8 if self.target == "sega_game_gear" else 4):
            raise SDCCSegaBootError("real game did not load meaningful graphics and palette")
        if self.psg_writes < 1:
            raise SDCCSegaBootError("real game did not initialize its native PSG")
        if not background["background_display_enabled"]:
            raise SDCCSegaBootError("compiled game did not enable video display")
        if len(background["hero_screen_tile_positions"]) != 1:
            raise SDCCSegaBootError("real Z80 game did not draw exactly one player")
        if background["score_digit_tiles"] != expected_digits:
            raise SDCCSegaBootError("compiled game did not draw expected zero-score HUD")
        if not 17 <= background["companion_expression_tile"] <= 21:
            raise SDCCSegaBootError("real game omitted original companion expression")
        if not self.vcounter_b0_seen or not self.vcounter_c8_seen:
            raise SDCCSegaBootError("devkitSMS boot did not encounter genuine scanline counter transitions")
        if self.vdp_read_status < 1:
            raise SDCCSegaBootError("compiled Z80 game never acknowledged a video interrupt")
        return background


def boot_rom(
    path: Path, *, target: str,
    max_instructions: int = MAX_INSTRUCTIONS,
    frame_instructions: int = DEFAULT_FRAME_INSTRUCTIONS,
) -> dict[str, object]:
    if target not in _MAP_NAMES:
        raise SDCCSegaBootError("unknown native Sega target")
    if type(max_instructions) is not int or not 1 <= max_instructions <= MAX_INSTRUCTIONS:
        raise SDCCSegaBootError("invalid bounded instruction limit")
    if type(frame_instructions) is not int or not 500 <= frame_instructions <= 100_000:
        raise SDCCSegaBootError("invalid synthetic VBlank cadence")
    # Intake once, with the repository's no-follow descriptor reader.
    # Do not reopen the path after checking it: a concurrent symlink swap
    # could otherwise change which bytes the Z80 CPU actually executes.
    binary = _read_bounded(path, max_bytes=32768)
    actual = validate_rom(binary, target)
    try:
        from z80_python import Z80CPU
    except ImportError as exc:
        raise SDCCSegaBootError("separate z80-python==0.4.0 interpreter required") from exc
    machine = Sega8Machine(binary, target=target)
    cpu = Z80CPU(machine.read, machine.write,
                 read_port=machine.read_port,
                 write_port=machine.write_port)
    cpu.pc = 0
    frames = 0
    observed = None
    # Bounded instruction samples help distinguish a dead startup vector,
    # HALT/IRQ deadlock and a real machine initialization failure. This is
    # diagnostic evidence only, never a permissive path to success.
    sample_pc: list[tuple[int, int, bool, int, int]] = []
    for n in range(1, max_instructions + 1):
        if n in (1, 2, 4, 8, 16, 32, 64, 128, 256, 512, 1024) or (
            n % 250000 == 0
        ):
            sample_pc.append((n, cpu.pc, bool(cpu.halted),
                              int(getattr(cpu, "iff1", 0)), cpu.sp))
        if n % frame_instructions == 0:
            frames += 1
            machine.frame_ready = True
            cpu.request_maskable_interrupt()
            machine.interrupts_issued += 1
            if frames > MAX_FRAMES:
                raise SDCCSegaBootError("hardware boot frame budget exceeded")
        try:
            machine.advance_tstates(cpu.step())
        except SDCCSegaBootError:
            raise
        except Exception as exc:
            raise SDCCSegaBootError(
                f"compiled Z80 CPU failed after {n} instructions"
            ) from exc
        if n % (frame_instructions * 2) == 0:
            try:
                observed = machine.observe_boot()
                break
            except SDCCSegaBootError:
                continue
    if observed is None:
        raise SDCCSegaBootError(
            "compiled Sega cartridge did not initialize and draw expected game "
            f"in {max_instructions} CPU instructions; "
            f"VDP writes={machine.vdp_writes}, CRAM writes={machine.cram_writes}, "
            f"V-counter reads={machine.vcounter_reads}, "
            f"B0 seen={machine.vcounter_b0_seen}, C8 seen={machine.vcounter_c8_seen}, "
            f"PSG writes={machine.psg_writes}, status reads={machine.vdp_read_status}; "
            f"PC samples={sample_pc}; reset vector={binary[:16].hex()}; "
            f"final_pc={cpu.pc:#06x} sp={cpu.sp:#06x} halted={cpu.halted}; "
            f"final_bc={cpu.bc:#06x} final_hl={cpu.hl:#06x} "
            f"final_de={cpu.de:#06x} final_a={cpu.a:#04x}; "
            f"trap_code={binary[max(0, cpu.pc-16):cpu.pc+24].hex()}; "
            f"boot_code={binary[0x1190:0x11b0].hex()}; "
            f"VBlank events={machine.interrupts_issued}"
        )
    return {
        "schema": "skeleton.game_builder.sega8_real_z80_boot_smoke.v1",
        "target": target,
        "rom_sha256": actual["sha256"],
        "real_compiled_z80_cpu_instructions_executed": n,
        "synthetic_vblank_interrupts_issued": machine.interrupts_issued,
        "native_vdp_vcounter_b0_observed": machine.vcounter_b0_seen,
        "native_vdp_vcounter_c8_observed": machine.vcounter_c8_seen,
        "real_z80_tstates_executed": machine.z80_tstates,
        "vdp_name_table_base": observed["name_table_base"],
        "game_hero_rendered": True,
        "original_companion_rendered": True,
        "zero_score_hud_verified": True,
        "video_io_writes": machine.vdp_writes,
        "palette_io_writes": machine.cram_writes,
        "psg_io_writes": machine.psg_writes,
        "hardware_boot_smoke_verified": True,
        "entire_game_playthrough_verified": False,
        "independent_cycle_exact_emulator_verified": False,
        "physical_hardware_verified": False,
        "distribution_licensed": False,
        "release_approved": False,
    }


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--rom", type=Path, required=True)
    p.add_argument("--target", required=True, choices=sorted(_MAP_NAMES))
    p.add_argument("--receipt-out", type=Path)
    args = p.parse_args()
    report = boot_rom(args.rom, target=args.target)
    if args.receipt_out is not None:
        if args.receipt_out.exists() or args.receipt_out.is_symlink():
            raise FileExistsError(str(args.receipt_out))
        with args.receipt_out.open("x", encoding="utf-8") as fp:
            json.dump(report, fp, sort_keys=True, indent=2)
            fp.write("\n")
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
