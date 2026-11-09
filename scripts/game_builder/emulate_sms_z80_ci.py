"""Independently execute *actual* SMS Z80 ROM through real CPU and hardware I/O.

This is not a full SMS emulator. A separately validated Z80 instruction-core
runs the machine code from the actual CRC-checked 32KB ROM; a narrow, strict
host models the console's ordinary unbanked ROM/RAM, Mode-4 VDP name-table
writes, palette, one PSG channel, active-low controller and VBlank IRQs.

Every original safe move is driven via joypad port $DC and checked against
independently derived game-world expected Z80 RAM and VDP tile state. This
distinguishes actual executable CPU gameplay from source/header simulation.
Real console hardware still requires an independent emulator/bench gate.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from skeleton.ai.game_builder.sms_rom import verify_sms

RAM_START = 0xC000
RAM_SIZE = 0x2000
VDP_NAME = 0x3800
MAX_MOVES = 20_000
MAX_INSTR_PER_FRAME = 150_000
_BUTTONS = {"up":0, "down":1, "left":2, "right":3}


class SMSCPUAcceptanceError(ValueError):
    """Compiled SMS game did not match its guest CPU, video or gameplay contract."""


class SMSHardware:
    def __init__(self, rom: bytes):
        verify_sms(rom)
        self.rom = rom
        self.ram = bytearray(RAM_SIZE)
        self.vram = bytearray(0x4000)
        self.cram = bytearray(32)
        self.registers = bytearray(16)
        self.io_writes = 0
        self.video_writes = 0
        self.psg_writes = 0
        self.cram_writes = 0
        self.vblank_acks = 0
        self.pad = 0xFF
        self.pending_control: int | None = None
        self.vdp_address = 0
        self.video_mode = "vram"

    def read(self, address: int) -> int:
        a=address & 0xFFFF
        if a < 0x8000:
            return self.rom[a]
        if a >= RAM_START:
            return self.ram[(a - RAM_START) % RAM_SIZE]
        return 0xFF

    def write(self, address: int, value: int) -> None:
        a=address & 0xFFFF
        if a < 0x8000:
            raise SMSCPUAcceptanceError("guest Z80 attempted write to read-only cartridge ROM")
        if RAM_START <= a <= 0xFFFF:
            self.ram[(a - RAM_START) % RAM_SIZE] = value & 0xFF
            return
        raise SMSCPUAcceptanceError("guest attempted write to nonexistent Z80 page 2 memory")

    def read_port(self, port: int) -> int:
        low=port & 0xFF
        if low == 0xDC:
            return self.pad
        if low == 0xBF:
            self.vblank_acks += 1
            self.pending_control=None
            return 0x80
        if low in (0xBE, 0xDD, 0x7E, 0x7F):
            return 0xFF
        raise SMSCPUAcceptanceError(f"native Z80 unexpectedly accessed IO port {low:#04x}")

    def write_port(self, port: int, value: int) -> None:
        low=port & 0xFF
        value &= 0xFF
        self.io_writes += 1
        if low == 0x7F or low == 0x7E:
            self.psg_writes += 1
            return
        if low == 0xBF:
            if self.pending_control is None:
                self.pending_control=value
                return
            first=self.pending_control
            self.pending_control=None
            mode=value & 0xC0
            if mode == 0x80:
                self.registers[value & 0x0F] = first
                return
            if mode == 0x40:
                self.video_mode="vram"
                self.vdp_address=((value & 0x3F)<<8)|first
                return
            if mode == 0xC0:
                self.video_mode="cram"
                self.vdp_address=first & 0x1F
                return
            # $0000-$3FFF read address, valid but no writes expected.
            self.video_mode="read"
            self.vdp_address=((value & 0x3F)<<8)|first
            return
        if low == 0xBE:
            if self.pending_control is not None:
                raise SMSCPUAcceptanceError("VDP data written during half-pending address")
            if self.video_mode=="vram":
                self.vram[self.vdp_address & 0x3FFF]=value
                self.vdp_address=(self.vdp_address+1)&0x3FFF
                self.video_writes+=1
                return
            if self.video_mode=="cram":
                if value > 63:
                    raise SMSCPUAcceptanceError("SMS CRAM received an invalid RGB222 byte")
                self.cram[self.vdp_address & 31]=value
                self.vdp_address=(self.vdp_address+1)&31
                self.cram_writes+=1
                return
            raise SMSCPUAcceptanceError("SMS Z80 attempted VDP write without valid write mode")
        raise SMSCPUAcceptanceError(f"Z80 output to unsupported SMS hardware port {low:#04x}")

    def ram_snapshot(self) -> dict[str,int]:
        mem=self.ram
        return {
            "level":mem[0], "x":mem[1], "y":mem[2],
            "gems_remaining":mem[5], "health":mem[6],
            "won":mem[7], "lost":mem[8],
            "score":mem[0x0C]+(mem[0x0D]<<8),
        }

    def player_vram_address(self) -> int:
        return VDP_NAME+64*(self.ram[2]+1)+2*(self.ram[1]+1)

    def assert_video(self) -> None:
        if self.registers[0] != 0x04 or self.registers[1] != 0x60:
            raise SMSCPUAcceptanceError("SMS Z80 failed to initialize genuine Mode4 VDP")
        if self.registers[2] != 0x0E:
            raise SMSCPUAcceptanceError("SMS tile name-table is not at $3800")
        if self.cram_writes < 32 or not any(self.cram):
            raise SMSCPUAcceptanceError("real guest CPU did not initialize original palette")
        address=self.player_vram_address()
        if not VDP_NAME <= address < 0x3F00 or self.vram[address] != 5:
            raise SMSCPUAcceptanceError("actual video RAM lacks authored hero tile at guest position")
        if self.vram[address+1] != 0:
            raise SMSCPUAcceptanceError("SMS hero uses unreviewed tile palette/bank attribute")


def _accepted_route(route: Any) -> dict[str, Any]:
    if not isinstance(route,dict):
        raise SMSCPUAcceptanceError("typed replay route required")
    if route.get("schema") != "skeleton.game_builder.game_boy_memory_replay.v1":
        raise SMSCPUAcceptanceError("not an independently generated source-game route")
    if route.get("binary_compiled") is not False or route.get("emulator_executed") is not False:
        raise SMSCPUAcceptanceError("replay source falsely claims binary or emulator acceptance")
    steps=route.get("steps")
    if not isinstance(steps,list) or not 1 <= len(steps) <= MAX_MOVES:
        raise SMSCPUAcceptanceError("empty or unbounded independent gameplay inputs")
    digest=route.get("route_sha256")
    packed={k:v for k,v in route.items() if k!="route_sha256"}
    expected=sha256(json.dumps(packed,sort_keys=True,separators=(",",":")).encode()).hexdigest()
    if digest != expected:
        raise SMSCPUAcceptanceError("tampered canonical original game route digest")
    for index,step in enumerate(steps):
        if not isinstance(step,dict) or step.get("button") not in _BUTTONS:
            raise SMSCPUAcceptanceError(f"invalid guest Z80 gameplay action at {index}")
        for attr in ("level","x","y","health","score","gems_remaining","won","lost"):
            if type(step.get(attr)) is not int or step[attr] < 0 or step[attr] > 65535:
                raise SMSCPUAcceptanceError("invalid bound Z80 RAM expectation")
    if steps[-1]["won"] != 1:
        raise SMSCPUAcceptanceError("only original winning replay accepted")
    return route


def _wait_for_halt(cpu: Any, *, instruction_budget: int) -> int:
    instructions=0
    while not cpu.halted and instructions < instruction_budget:
        cpu.step()
        instructions+=1
    if not cpu.halted:
        raise SMSCPUAcceptanceError("native game CPU failed to reach interrupt-synchronized HALT")
    return instructions


def _frame(cpu: Any, machine: SMSHardware, button: str | None) -> int:
    machine.pad=0xFF if button is None else (0xFF ^ (1<<_BUTTONS[button]))
    cpu.request_maskable_interrupt()
    cpu.step()
    return 1+_wait_for_halt(cpu,instruction_budget=MAX_INSTR_PER_FRAME)


def play(rom_path: Path, route_path: Path) -> dict[str,object]:
    if not rom_path.is_file() or not route_path.is_file():
        raise SMSCPUAcceptanceError("real native SMS ROM and independent original reference required")
    if route_path.stat().st_size > 8*1024*1024:
        raise SMSCPUAcceptanceError("unbounded original Z80 game route evidence")
    rom=rom_path.read_bytes()
    verified=verify_sms(rom)
    route=_accepted_route(json.loads(route_path.read_text(encoding="utf-8")))
    try:
        from z80_python import Z80CPU
    except ImportError as exc:
        raise SMSCPUAcceptanceError("independent z80-python 0.4 CPU emulator required") from exc
    machine=SMSHardware(rom)
    cpu=Z80CPU(machine.read,machine.write,read_port=machine.read_port,
               write_port=machine.write_port)
    cpu.pc=0
    total_instructions=_wait_for_halt(cpu,instruction_budget=MAX_INSTR_PER_FRAME)
    machine.assert_video()
    if machine.ram_snapshot()!=route["initial"]:
        raise SMSCPUAcceptanceError("native Z80 boot RAM differs from authored gameplay initial state")
    for index,step in enumerate(route["steps"]):
        total_instructions+=_frame(cpu,machine,step["button"])
        expected={k:step[k] for k in (
            "level","x","y","gems_remaining","health","won","lost"
        )}
        # Guest ROM has authored reward rules: +10 per crystal, +100 per gate.
        expected["score"]=step["score"]*10+(step["level"]+step["won"])*100
        actual=machine.ram_snapshot()
        if actual!=expected:
            raise SMSCPUAcceptanceError(
                "Z80 native RAM replay divergence at action "+
                str(index)+": actual="+str(actual)+" expected="+str(expected)
            )
        machine.assert_video()
        if index+1<len(route["steps"]):
            for _ in range(7):
                total_instructions+=_frame(cpu,machine,None)
    final=machine.ram_snapshot()
    if not final["won"] or final["lost"] or final["level"]+1 != route["levels"]:
        raise SMSCPUAcceptanceError("real native SMS CPU failed to finish all levels")
    if machine.vblank_acks < len(route["steps"]):
        raise SMSCPUAcceptanceError("actual SMS ROM never acknowledged enough video frames")
    if machine.video_writes < 1536 or machine.psg_writes < 4:
        raise SMSCPUAcceptanceError("real SMS hardware IO did not run correctly")
    return {
        "schema":"skeleton.game_builder.sms_guest_z80_cpu_acceptance.v1",
        "rom_sha256":verified["sha256"],
        "reference_route_sha256":route["route_sha256"],
        "world_digest":route["world_digest"],
        "real_z80_instructions_executed":total_instructions,
        "original_controller_actions_verified":len(route["steps"]),
        "all_original_stages_verified":route["levels"],
        "final_guest_z80_ram":final,
        "video_io_writes":machine.video_writes,
        "palette_io_writes":machine.cram_writes,
        "sound_io_writes":machine.psg_writes,
        "actual_interrupt_acks":machine.vblank_acks,
        "native_cpu_and_mode4_io_passed":True,
        "independent_full_console_emulator_verified":False,
        "physical_hardware_verified":False,
        "release_approved":False,
    }


def main() -> None:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rom",required=True,type=Path)
    parser.add_argument("--route",required=True,type=Path)
    parser.add_argument("--out",required=True,type=Path)
    args=parser.parse_args()
    if args.out.exists() or args.out.is_symlink():
        raise FileExistsError(str(args.out))
    report=play(args.rom,args.route)
    with args.out.open("x",encoding="utf-8",newline="\n") as stream:
        json.dump(report,stream,sort_keys=True,indent=2)
        stream.write("\n")
    print(json.dumps({
        "native_cpu_and_mode4_io_passed":report["native_cpu_and_mode4_io_passed"],
        "original_controller_actions_verified":report["original_controller_actions_verified"],
        "all_original_stages_verified":report["all_original_stages_verified"],
    },sort_keys=True))


if __name__=="__main__":
    main()
