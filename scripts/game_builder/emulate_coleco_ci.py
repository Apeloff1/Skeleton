"""Bounded real ColecoVision Z80 CPU replay with rights-clean BIOS entry stubs.

Actual ColecoVision .col Z80 opcodes execute on an independent, oracle-tested
Z80CPU. This host supplies only a transparent two-entry BIOS stub (MODE_1 and
LOAD_ASCII, modeled as RET) and an OS7 $0066 -> cartridge-$8021 NMI vector.
It does NOT ship or emulate Coleco's proprietary BIOS ROM and DOES NOT claim
a complete TMS9918 pixel-rendering or physical-console test.

Every direction is injected at physical controller port $FC, and every Z80
state transition is compared to an independent safe route. The host observes
hardware-originating VRAM name-table updates and game health/score/gems
from the Z80's mirrored 1 KiB physical RAM, not from the game source text.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
from struct import unpack_from
from typing import Any

from skeleton.ai.game_builder.coleco_rom import verify_col

COL_BIOS_MODE1=0x1F85
COL_BIOS_ASCII=0x1F7F
MAX_GAME_ACTIONS=20_000
FRAME_BUDGET=180_000
TMS_NAME=0x1800
MOVES={"up":0,"right":1,"down":2,"left":3}


class ColecoCPUError(ValueError):
    """Original Coleco game CPU, TMS9918 state or reference deviated."""


class ColecoMachine:
    def __init__(self, rom:bytes):
        info=verify_col(rom)
        self.rom=rom
        self.entry=info["boot_address"]
        self.nmi=info["nmi_address"]
        self.ram=bytearray(1024)
        self.vram=bytearray(16384)
        self.vdp_registers=bytearray(8)
        self.ctrl_first:int|None=None
        self.vdp_addr=0
        self.vdp_write_enabled=False
        self.pad=0xFF
        self.pad_selected=False
        self.rom_firmware_bundled=False
        self.bios_calls={"MODE_1":0,"LOAD_ASCII":0}
        self.vblank_acks=0
        self.video_writes=0
        self.psg_writes=0
        self.controller_reads=0

    def read(self,address:int)->int:
        a=address&0xFFFF
        if a==COL_BIOS_MODE1:
            self.bios_calls["MODE_1"]+=1
            return 0xC9         # Narrow BIOS entry stub: RET, no firmware.
        if a==COL_BIOS_ASCII:
            self.bios_calls["LOAD_ASCII"]+=1
            return 0xC9         # VIDEO NAME TABLE logic remains native.
        if 0x0066<=a<=0x0068:
            return bytes((0xC3,self.nmi&255,self.nmi>>8))[a-0x0066]
        if 0x6000<=a<=0x7FFF:
            return self.ram[a&1023]
        if a>=0x8000:
            return self.rom[a-0x8000]
        raise ColecoCPUError("Coleco Z80 attempted to execute unspecified private OS7 firmware")

    def write(self,address:int,value:int)->None:
        a=address&0xFFFF
        if 0x6000<=a<=0x7FFF:
            self.ram[a&1023]=value&255
            return
        raise ColecoCPUError("native game wrote to BIOS ROM, cartridge or unpopulated Coleco memory")

    def read_port(self,port:int)->int:
        a=port&255
        if a==0xFC:
            if not self.pad_selected:
                raise ColecoCPUError("Coleco guest read player-one controller before joystick strobe")
            self.controller_reads+=1
            return self.pad
        if a==0xBF:
            self.ctrl_first=None
            self.vblank_acks+=1
            return 0x80
        raise ColecoCPUError("Coleco guest CPU unexpectedly read unknown port "+hex(a))

    def write_port(self,port:int,value:int)->None:
        a=port&255
        value&=255
        if a==0xC0:
            self.pad_selected=True
            return
        if a==0xFF:
            self.psg_writes+=1
            return
        if a==0xBF:
            if self.ctrl_first is None:
                self.ctrl_first=value
                return
            first=self.ctrl_first
            self.ctrl_first=None
            if value&0xC0==0x80:
                reg=value&7
                self.vdp_registers[reg]=first
                return
            self.vdp_addr=(((value&0x3F)<<8)|first)&0x3FFF
            self.vdp_write_enabled=value&0x40!=0
            return
        if a==0xBE:
            if self.ctrl_first is not None:
                raise ColecoCPUError("TMS9918 data written with half a control address")
            if not self.vdp_write_enabled:
                raise ColecoCPUError("TMS9918 guest wrote before selecting VRAM write mode")
            self.vram[self.vdp_addr]=value
            self.vdp_addr=(self.vdp_addr+1)&0x3FFF
            self.video_writes+=1
            return
        raise ColecoCPUError("Coleco guest wrote to unknown device port "+hex(a))

    def ram_state(self)->dict[str,int]:
        m=self.ram
        return {"level":m[0x300],"x":m[0x301],"y":m[0x302],
                "gems_remaining":m[0x305],"health":m[0x306],
                "won":m[0x307],"lost":m[0x308],
                "score":m[0x30D]|(m[0x30E]<<8)}

    def hero_address(self)->int:
        state=self.ram_state()
        return TMS_NAME+33+32*state["y"]+state["x"]

    def assert_screen(self)->None:
        if self.vdp_registers[1]!=0xE0:
            raise ColecoCPUError("actual Z80 did not rearm genuine TMS9918 vertical-NMI mode")
        addr=self.hero_address()
        if addr<TMS_NAME or addr>=TMS_NAME+768 or self.vram[addr]!=ord("@"):
            raise ColecoCPUError("real Coleco VRAM lacks the original hero at guest RAM position")
        if not self.pad_selected:
            raise ColecoCPUError("guest ROM never selected original controller mode")
        if self.video_writes<768:
            raise ColecoCPUError("guest ROM never actually rendered video name table")


def _reference(route:object,manifest:object)->dict[str,Any]:
    if not isinstance(route,dict) or not isinstance(manifest,dict):
        raise ColecoCPUError("typed original world and rights manifest required")
    if route.get("schema")!="skeleton.game_builder.game_boy_memory_replay.v1":
        raise ColecoCPUError("unrecognized original game route")
    if manifest.get("platform")!="colecovision" or manifest.get("world_digest")!=route.get("world_digest"):
        raise ColecoCPUError("native Coleco ROM and independently authored world provenance mismatch")
    if manifest.get("native_binary_compiled") is not False:
        raise ColecoCPUError("untrusted source manifest falsely certified native build")
    if not isinstance(manifest.get("author_evidence_sha256"),str) or len(manifest["author_evidence_sha256"])!=64:
        raise ColecoCPUError("Coleco source lacks author-owned rights evidence")
    for k in ("binary_compiled","emulator_executed","hardware_verified","release_approved"):
        if route.get(k) is not False:
            raise ColecoCPUError("reference trajectory falsely asserted hardware certification")
    raw={k:v for k,v in route.items() if k!="route_sha256"}
    digest=sha256(json.dumps(raw,sort_keys=True,separators=(",",":")).encode()).hexdigest()
    if route.get("route_sha256")!=digest:
        raise ColecoCPUError("modified independent source-game replay digest")
    moves=route.get("steps")
    if not isinstance(moves,list) or not 1<=len(moves)<=MAX_GAME_ACTIONS:
        raise ColecoCPUError("source gameplay moves empty or outside bounded CPU budget")
    if route.get("levels") not in range(1,9) or moves[-1].get("won")!=1:
        raise ColecoCPUError("source-game winning path or level budget invalid")
    for item in moves:
        if not isinstance(item,dict) or item.get("button") not in MOVES:
            raise ColecoCPUError("invalid Z80 hardware controller button")
        for k in ("level","x","y","gems_remaining","health","score","won","lost"):
            if type(item.get(k)) is not int or item[k]<0 or item[k]>65535:
                raise ColecoCPUError("untrusted Z80 physical-RAM state expectation")
    return route


def _wait_halt(cpu:Any)->int:
    instructions=0
    while not cpu.halted and instructions<FRAME_BUDGET:
        cpu.step()
        instructions+=1
    if not cpu.halted:
        raise ColecoCPUError("native Coleco Z80 did not return to frame HALT under bounded instruction budget")
    return instructions


def _frame(cpu:Any,machine:ColecoMachine,button:str|None)->int:
    if machine.vdp_registers[1]!=0xE0:
        raise ColecoCPUError("TMS9918A guest NMI was not rearmed at frame boundary")
    machine.pad=0xFF if button is None else 0xFF^(1<<MOVES[button])
    cpu.request_non_maskable_interrupt()
    cpu.step()
    return 1+_wait_halt(cpu)


def play(rom_path:Path,route_path:Path,manifest_path:Path)->dict[str,object]:
    if not rom_path.is_file() or not route_path.is_file() or not manifest_path.is_file():
        raise ColecoCPUError("compiled Coleco ROM, safe source route and author manifest required")
    if route_path.stat().st_size>8*1024*1024 or manifest_path.stat().st_size>256*1024:
        raise ColecoCPUError("unbounded external Coleco gameplay or rights input")
    rom=rom_path.read_bytes()
    proof=verify_col(rom)
    route=_reference(json.loads(route_path.read_text(encoding="utf-8")),
                     json.loads(manifest_path.read_text(encoding="utf-8")))
    from z80_python import Z80CPU
    machine=ColecoMachine(rom)
    cpu=Z80CPU(machine.read,machine.write,read_port=machine.read_port,
               write_port=machine.write_port)
    cpu.pc=machine.entry      # OS7 header-selected start, not a made-up PC.
    instructions=_wait_halt(cpu)
    if machine.bios_calls!={"MODE_1":1,"LOAD_ASCII":1}:
        raise ColecoCPUError("native program did not call the exact audited Coleco OS7 entry points")
    machine.assert_screen()
    if machine.ram_state()!=route["initial"]:
        raise ColecoCPUError("actual Coleco Z80 boot RAM differs from safe original-world reference")
    for i,step in enumerate(route["steps"]):
        instructions+=_frame(cpu,machine,step["button"])
        expected={k:step[k] for k in (
            "level","x","y","gems_remaining","health","won","lost",
        )}
        expected["score"]=step["score"]*10+(step["level"]+step["won"])*100
        actual=machine.ram_state()
        if expected!=actual:
            raise ColecoCPUError(
                f"native Coleco Z80 guest RAM diverged at move {i}: "
                f"actual={actual}; expected={expected}"
            )
        machine.assert_screen()
        if i+1<len(route["steps"]):
            for _ in range(7):
                instructions+=_frame(cpu,machine,None)
    final=machine.ram_state()
    if final["won"]!=1 or final["lost"] or final["level"]+1!=route["levels"]:
        raise ColecoCPUError("actual original Z80 game never won last authored Coleco level")
    if machine.video_writes<768 or machine.vblank_acks<len(route["steps"]):
        raise ColecoCPUError("native Coleco CPU did not perform actual video/interrupt workload")
    if machine.controller_reads<len(route["steps"]) or machine.psg_writes<4:
        raise ColecoCPUError("original Z80 console gameplay lacked controller and sound IO")
    return {
        "schema":"skeleton.game_builder.coleco_cpu_os7_bounded_replay.v1",
        "rom_sha256":proof["native_cartridge_sha256"],
        "original_world_digest":route["world_digest"],
        "safe_reference_digest":route["route_sha256"],
        "real_z80_cpu_instructions_executed":instructions,
        "controller_actions_verified":len(route["steps"]),
        "original_levels_completed":route["levels"],
        "final_1kb_mirrored_guest_ram":final,
        "original_tms9918_vram_name_writes":machine.video_writes,
        "real_z80_nmi_acknowledgements":machine.vblank_acks,
        "sn76489_write_count":machine.psg_writes,
        "coleco_bios_stub_calls":machine.bios_calls,
        "actual_colo_z80_cpu_gameplay_verified":True,
        "proprietary_coleco_bios_redistributed":False,
        "complete_colecovision_emulator_verified":False,
        "physical_hardware_verified":False,
        "independent_distribution_rights_verified":False,
    }


def main()->None:
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rom",type=Path,required=True)
    ap.add_argument("--reference",type=Path,required=True)
    ap.add_argument("--manifest",type=Path,required=True)
    ap.add_argument("--out",type=Path,required=True)
    args=ap.parse_args()
    if args.out.exists() or args.out.is_symlink():
        raise FileExistsError(str(args.out))
    receipt=play(args.rom,args.reference,args.manifest)
    with args.out.open("x",encoding="utf-8",newline="\n") as handle:
        json.dump(receipt,handle,sort_keys=True,indent=2)
        handle.write("\n")
    print(json.dumps({
        "actual_colo_z80_cpu_gameplay_verified":receipt["actual_colo_z80_cpu_gameplay_verified"],
        "controller_actions_verified":receipt["controller_actions_verified"],
        "original_levels_completed":receipt["original_levels_completed"],
    },sort_keys=True))

if __name__=="__main__":
    main()
