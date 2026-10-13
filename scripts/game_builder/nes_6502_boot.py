"""Bounded original NES 6502 startup against a minimal observable PPU bus.

Runs actual ca65/ld65 NROM PRG instructions with the BSD-licensed Py65 NMOS
6502 core. Implements just the NES CPU RAM, ROM, PPU status/address/data,
OAM DMA and controller ports needed to independently *observe* our boot.
This is not cycle-accurate emulation, not NES certification and not a
claim of gameplay completion or publisher/distribution permission.
"""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

from scripts.game_builder.native_nes_ci import inspect_rom
from skeleton.ai.game_builder.native_release_intake import _read_bounded

_ROM_SIZE = 16 + 32768 + 8192
_FRAME_CPU_CYCLES = 29781
_VBLANK_START = 27394
_MAX_INSTRUCTIONS = 850000


class NES6502BootError(ValueError):
    """Real compiled NES cartridge failed bounded CPU/PPU startup."""


class ObservableNESBus:
    """Strict NROM bus with time-advanced PPU vblank and original OAM DMA."""

    def __init__(self, data: bytes):
        if len(data) != _ROM_SIZE or data[:16] != bytes.fromhex(
            "4e45531a020100000000000000000000"
        ):
            raise NES6502BootError("exact original NROM-256 mapper-zero bytes required")
        self.ram=bytearray(0x800)
        self.prg=data[16:16+32768]
        self.palette=bytearray(32)
        self.nametable=bytearray(2048)
        self.oam=bytearray(256)
        self.ppuaddr=0
        self.ppuaddr_high=True
        self.ppu_increment=1
        self.ppu_reads=0
        self.palette_writes=0
        self.nametable_writes=0
        self.oam_dma_count=0
        self.cpu=None
        self.vblank_latch=False
        self.vblank_generation=-1
        self.reads_4016=0
        self.button_state=0
        self.button_shift=0
        self.button_strobe=0
        self.last_control=0
        self.last_mask=0

    def _cycles(self) -> int:
        return 0 if self.cpu is None else int(self.cpu.processorCycles)

    def _update_vblank(self) -> None:
        ticks=self._cycles()
        frame=ticks//_FRAME_CPU_CYCLES
        if ticks%_FRAME_CPU_CYCLES >= _VBLANK_START and frame>self.vblank_generation:
            self.vblank_latch=True
            self.vblank_generation=frame

    def __getitem__(self, address: int) -> int:
        a=int(address)&65535
        if a < 0x2000:
            return self.ram[a&0x7ff]
        if a < 0x4000:
            reg=0x2000+(a&7)
            if reg==0x2002:
                self._update_vblank()
                val=0x80 if self.vblank_latch else 0
                self.vblank_latch=False
                self.ppuaddr_high=True
                self.ppu_reads+=1
                return val
            if reg==0x2007:
                addr=self.ppuaddr&0x3fff
                val=self.palette[addr&31] if 0x3f00<=addr<=0x3fff else (
                    self.nametable[(addr-0x2000)&0x7ff] if 0x2000<=addr<0x3f00 else 0
                )
                self.ppuaddr=(self.ppuaddr+self.ppu_increment)&0x3fff
                return val
            return 0
        if a==0x4016:
            self.reads_4016+=1
            val=self.button_shift&1
            if not self.button_strobe:
                self.button_shift=(self.button_shift>>1)|0x80
            return val
        if a>=0x8000:
            return self.prg[a-0x8000]
        return 0

    def __setitem__(self, address: int, value: int) -> None:
        a=int(address)&65535
        v=int(value)&255
        if a<0x2000:
            self.ram[a&0x7ff]=v
        elif a<0x4000:
            reg=0x2000+(a&7)
            if reg==0x2000:
                self.last_control=v
                self.ppu_increment=32 if v&4 else 1
            elif reg==0x2001:
                self.last_mask=v
            elif reg==0x2006:
                if self.ppuaddr_high:
                    self.ppuaddr=(self.ppuaddr&255)|((v&63)<<8)
                else:
                    self.ppuaddr=(self.ppuaddr&0x3f00)|v
                self.ppuaddr_high=not self.ppuaddr_high
            elif reg==0x2007:
                addr=self.ppuaddr&0x3fff
                if 0x3f00<=addr<=0x3fff:
                    self.palette[addr&31]=v
                    self.palette_writes+=1
                elif 0x2000<=addr<0x3f00:
                    self.nametable[(addr-0x2000)&0x7ff]=v
                    self.nametable_writes+=1
                self.ppuaddr=(self.ppuaddr+self.ppu_increment)&0x3fff
        elif a==0x4014:
            page=(v<<8)&65535
            for i in range(256):
                self.oam[i]=self[(page+i)&65535]
            self.oam_dma_count+=1
        elif a==0x4016:
            old=self.button_strobe
            self.button_strobe=v&1
            if self.button_strobe or (old and not self.button_strobe):
                self.button_shift=self.button_state

    def set_button(self, name: str | None) -> None:
        buttons={None:0,"up":1<<4,"down":1<<5,"left":1<<6,"right":1<<7}
        if name not in buttons:
            raise NES6502BootError("unsupported original NES controller action")
        self.button_state=buttons[name]


def verify_original_nes_6502_boot(
    rom_path: str | Path, *, expected_sha256: str,
    instruction_budget: int = _MAX_INSTRUCTIONS,
    expected_stage_zero_bg_sha256: str | None = None,
) -> dict[str, object]:
    """Execute the actual compiled 6502 reset path and observe PPU/OAM writes.

    Deliberately scoped to source game's visible startup only. Actual full
    reference route, PPU rendering accuracy and physical device behavior
    require separate future verification.
    """
    if type(instruction_budget) is not int or not 25000<=instruction_budget<=_MAX_INSTRUCTIONS:
        raise NES6502BootError("native 6502 execution budget outside fixed limits")
    if not isinstance(expected_sha256,str) or len(expected_sha256)!=64 or any(
        c not in "0123456789abcdef" for c in expected_sha256
    ):
        raise NES6502BootError("pinned NES binary digest missing")
    if expected_stage_zero_bg_sha256 is not None and (
        not isinstance(expected_stage_zero_bg_sha256,str)
        or len(expected_stage_zero_bg_sha256)!=64
        or any(c not in "0123456789abcdef" for c in expected_stage_zero_bg_sha256)
    ):
        raise NES6502BootError("original first-stage map requires exact SHA-256")
    data=_read_bounded(Path(rom_path),max_bytes=_ROM_SIZE)
    if sha256(data).hexdigest()!=expected_sha256:
        raise NES6502BootError("NES game bytes changed after original build")
    binary=inspect_rom(Path(rom_path))
    if binary["sha256"]!=expected_sha256:
        raise NES6502BootError("real NES ROM replaced during structural validation")
    try:
        from py65.devices.mpu6502 import MPU
    except ImportError as exc:
        raise NES6502BootError("Py65 NMOS 6502 CPU runtime required for native boot verification") from exc

    bus=ObservableNESBus(data)
    cpu=MPU(memory=bus,pc=None)
    bus.cpu=cpu
    pcs=[]
    for index in range(instruction_budget):
        if len(pcs)<12:
            pcs.append(cpu.pc)
        if not 0x8000<=cpu.pc<=0xffff:
            raise NES6502BootError("compiled NES CPU escaped 32KiB mapped PRG")
        cpu.step()
        # A real game reaches its main loop and copies an authored 960-tile
        # name table, 32 palette colors, and its sprite-DMA buffer.
        if (bus.palette_writes>=32 and bus.nametable_writes>=960
            and bus.oam_dma_count>=1 and bus.ppu_reads>=2):
            actual_stage_bg_sha256=sha256(bus.nametable[:960]).hexdigest()
            if (expected_stage_zero_bg_sha256 is not None
                and actual_stage_bg_sha256 != expected_stage_zero_bg_sha256):
                raise NES6502BootError(
                    "real 6502 PPU stage-zero map differs from original authored world"
                )
            return {
                "schema":"skeleton.game_builder.nes_original_6502_boot.v1",
                "target":"nintendo_famicom",
                "rom_sha256":expected_sha256,
                "cpu_kind":"py65-nmos6502",
                "reset_vector":binary["reset_vector"],
                "nmi_vector":binary["nmi_vector"],
                "irq_vector":binary["irq_vector"],
                "actual_6502_cpu_executed":True,
                "original_ppu_palette_writes_observed":bus.palette_writes,
                "original_ppu_nametable_writes_observed":bus.nametable_writes,
                "actual_sprite_dma_transfers_observed":bus.oam_dma_count,
                "ppu_status_reads_observed":bus.ppu_reads,
                "actual_cpu_instructions_executed":index+1,
                "simulated_cpu_cycles":cpu.processorCycles,
                "original_palette_sha256":sha256(bus.palette).hexdigest(),
                "original_nametable_sha256":sha256(bus.nametable[:960]).hexdigest(),
                "sampled_reset_program_counters":pcs,
                "cpu_interpreter_validated_for_boot_subset":True,
                "cycle_accurate_ppu_apu_verified":False,
                "full_gameplay_playthrough_verified":False,
                "physical_hardware_verified":False,
                "copyright_status_certified":False,
                "publication_authorized":False,
            }
    raise NES6502BootError(
        "original NES game startup exceeded bounded CPU instructions; "
        f"pc={cpu.pc:#06x} palette={bus.palette_writes} "
        f"nametable={bus.nametable_writes} dma={bus.oam_dma_count} "
        f"ppu_status={bus.ppu_reads} cpu_cycles={cpu.processorCycles}"
    )


def main() -> None:
    import argparse
    from scripts.game_builder.sega_reproducibility_ci import emit_receipt
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rom",required=True,type=Path)
    parser.add_argument("--expected-sha256",required=True)
    parser.add_argument("--expected-bg-sha256")
    parser.add_argument("--receipt-out",required=True,type=Path)
    args=parser.parse_args()
    result=verify_original_nes_6502_boot(
        args.rom, expected_sha256=args.expected_sha256,
        expected_stage_zero_bg_sha256=args.expected_bg_sha256,
    )
    emit_receipt(args.receipt_out,result)
    print(json.dumps(result,sort_keys=True))


if __name__=="__main__":
    main()
