"""Explicit 2026 Dragon hardware readiness and bounded per-platform backlog.

"Identified" != "source emitted" != "compiled" != "emulated" !=
"measured on device" != "distribution approved". This contract makes
the difference machine-readable, including unsupported/licensed systems.
"""
from __future__ import annotations
from dataclasses import asdict,dataclass
from hashlib import sha256
from typing import Literal
import json
from .dragon_native_targets import CATALOG,TARGETS,STYLES,target_catalog
from .dragon_native_projects import EMITTERS

Stage=Literal["catalog_only","native_source_generated","compiled_verified",
              "emulator_replay_verified","hardware_verified"]
SOURCE_RENDERERS={
  "game_boy":"SM83 OAM/PPU 2bpp",
  "game_boy_color":"SM83 CGB OAM/palettes",
  "nes":"6502 NES PPU sprite DMA",
  "master_system":"Z80 Sega VDP",
  "game_gear":"Z80 Game Gear VDP",
  "snes":"65816 Mode 1 framebuffer starter",
  "genesis":"68000 SGDK display",
  "commodore_64":"6502 VIC-II RAM",
  "game_boy_advance":"ARM7TDMI GBA Mode 3 framebuffer",
  "dos_vga":"x86 386 DOS VGA 13h",
  "ps1":"MIPS PSn00bSDK display",
  "xbox_original":"x86 nxdk display",
  "nintendo_64":"VR4300 libdragon surface",
  "nintendo_ds":"ARM9 bitmap and touch",
  "psp":"Allegrex PSPSDK debug display",
  "atari_2600":"6507 TIA 192-line NTSC",
  "apple_ii":"6502 ProDOS conio screen",
  "zx_spectrum":"Z80 z88dk conio",
  "dos_8086":"x86 real-mode 16-bit DOS console",
  "windows_95":"Win32 GDI 32-bit painting",
  "pc_linux":"C99/SDL2 native game",
  "pc_windows":"C99/SDL2 native game",
  "pc_macos":"C99/SDL2 native game",
  "steam_deck":"C99/SDL2 Linux native game",
}
from .dragon_desktop_abi import ABI_PROFILES
SOURCE_RENDERERS.update({key:"C99/SDL2 "+p.system+" "+p.arch for key,p in ABI_PROFILES.items()})
SOURCE_RENDERERS.update({
    "gamecube":"PowerPC libogc GameCube XFB console",
    "wii":"PowerPC libogc Wii XFB console and WPAD",
    "nintendo_3ds":"ARM11 libctru/citro2d hardware top display",
})
SOURCE_RENDERERS.update({
    "dreamcast":"KallistiOS SH-4 RGB565 VRAM / Maple controller",
    "ps2":"PS2SDK MIPS EE gsKit GS / PAD RPC",
})
SOURCE_RENDERERS.update({
    "commodore_vic20":"6502 VIC-I color/sound and conio text",
    "commodore_128":"8502 VIC-II/SID and native 40-column text",
    "atari_400_800":"6502 ANTIC/GTIA/POKEY conio",
    "msx1":"Z80 MSX1 BIOS and VDP conio",
    "amstrad_cpc":"Z80 CPC firmware text/ink",
})
SOURCE_RENDERERS.update({
    "playdate":"STM32F7 native Playdate C API 400x240 1bpp",
    "arduboy":"ATmega32u4 Arduboy2 OLED 128x64 1bpp",
})
from .dragon_compatible_revisions import REVISIONS
SOURCE_RENDERERS.update({
    r.target:"ABI-compatible original "+r.runtime_mode+
       " (native source inherited from "+r.parent+")"
    for r in REVISIONS
})
assert set(SOURCE_RENDERERS)==EMITTERS

@dataclass(frozen=True)
class TargetReadiness:
    schema:str
    target:str
    family:str
    era:str
    year:int
    cpu:str
    graphics_hardware:str
    native_renderer:str
    toolchain:str
    output_extension:str
    status:str
    source_emitter:bool
    supported_styles:tuple[str,...]
    claimed_stage:Stage
    compiler_verified:bool
    controller_replay_verified:bool
    physical_hardware_verified:bool
    distribution_approved:bool
    next_gate:str
    source_access:str
    limitations:tuple[str,...]

def readiness_for(target_id:str)->TargetReadiness:
    if not isinstance(target_id,str) or target_id not in CATALOG:
        raise ValueError("unknown hardware readiness target")
    target=CATALOG[target_id]
    source=target_id in EMITTERS
    if source!=(target.status=="native_source"):
        raise ValueError("hardware source and availability claims inconsistent")
    t=next(x for x in target_catalog() if x["id"]==target_id)
    if source:
        next_gate="Install exact target SDK/toolchain; compile emitted source on a controlled runner"
        scope="Original source; toolchain installation is external"
    elif target.status=="licensed_sdk":
        next_gate="Obtain lawful developer authorization and SDK before native port work"
        scope="Licensed SDK not bundled or available through this game forge"
    elif target.status=="historical_reference":
        next_gate="Document non-programmable hardware capabilities; no source cartridge exists"
        scope="Historical capability reference; cannot run arbitrary software"
    else:
        next_gate="Implement platform-specific native rendering, input and build adapter"
        scope="Catalogued target; no native source project implemented"
    limitations=(
        "No compiler success automatically inferred from a source template",
        "No emulator/controller/input or frame timing evidence for this platform",
        "No physical hardware validation or distribution license is inferred",
    )
    return TargetReadiness(
      "skeleton.ai.dragon.target_readiness.v1",
      target.id,target.family,target.generation,target.year,target.cpu,
      target.graphics,SOURCE_RENDERERS.get(target_id,"NOT IMPLEMENTED"),
      target.toolchain,target.output,target.status,source,
      tuple(t["supported_styles"]),"native_source_generated" if source else "catalog_only",
      False,False,False,False,next_gate,scope,limitations,
    )

def coverage_report()->dict:
    rows=tuple(readiness_for(t.id) for t in TARGETS)
    supported=[r for r in rows if r.source_emitter]
    licensed=[r for r in rows if r.status=="licensed_sdk"]
    unsupported=[r for r in rows if not r.source_emitter]
    by_era={}
    for r in rows:
        key=r.era
        current=by_era.setdefault(key,{"catalogued":0,"source_emitters":0})
        current["catalogued"]+=1
        current["source_emitters"]+=int(r.source_emitter)
    by_family={}
    for r in rows:
        item=by_family.setdefault(r.family,{"catalogued":0,"source_emitters":0})
        item["catalogued"]+=1
        item["source_emitters"]+=int(r.source_emitter)
    report={
        "schema":"skeleton.ai.dragon.platform_coverage.v1",
        "catalog_count":len(rows),
        "native_source_count":len(supported),
        "missing_native_source_count":len(unsupported),
        "licensed_count":len(licensed),
        "source_coverage_fraction":round(len(supported)/max(1,len(rows)),6),
        "compiler_verified_count":0,
        "emulator_verified_count":0,
        "physical_hardware_verified_count":0,
        "coverage_scope":"curated major legacy/modern device identities, not literally every SKU worldwide",
        "hardware_ids":[r.target for r in rows],
        "source_ids":[r.target for r in supported],
        "next_unimplemented":[{"target":r.target,"toolchain":r.toolchain,
                 "next_gate":r.next_gate,"status":r.status} for r in unsupported],
        "by_era":dict(sorted(by_era.items())),
        "by_family":dict(sorted(by_family.items())),
    }
    data=json.dumps(report,sort_keys=True,separators=(",",":"),ensure_ascii=True)
    report["digest"]=sha256(data.encode()).hexdigest()
    return report

def readiness_json()->str:
    return json.dumps({
        "coverage":coverage_report(),
        "targets":[asdict(readiness_for(x.id)) for x in TARGETS],
    },sort_keys=True,ensure_ascii=True,indent=2)+"\n"
