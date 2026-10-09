"""Explicit per-console storage, video, sprite and source budget audit.

This auditor checks only source asset payload sizes/format against known
conservative development budgets; it is NOT actual linker allocation, OAM
scanline instrumentation, cycle count, VRAM capture, certification or proof
that the firmware has compiled. Real binary linker map + emulator trace must
still verify usage. Reject impossible declared asset bundles before export.
"""
from __future__ import annotations
from dataclasses import dataclass,asdict
from hashlib import sha256
import json

@dataclass(frozen=True)
class HardwareBudget:
    target:str
    console_family:str
    cpu:str
    graphics_ram_bytes:int
    tile_graphics_budget_bytes:int
    working_ram_bytes:int
    nominal_rom_bank_bytes:int
    max_visible_sprites:int
    max_sprites_per_scanline:int
    max_sprite_tiles:int
    max_source_bundle_bytes:int
    confidence:str="conservative_source_estimate_only"

@dataclass(frozen=True)
class HardwareAudit:
    target:str
    status:str
    source_bytes:int
    declared_asset_bytes:int
    claimed_tile_count:int
    tile_layout:str
    sprite_asset_ratio:float
    source_ratio:float
    warnings:tuple[str,...]
    budget:dict
    digest:str

# Values reflect conservative resource classes, not universal mapper/SDK limits.
LIMITS={
    "game_boy":("Nintendo","SM83",8192,8192,8192,16384,40,10,256),
    "game_boy_color":("Nintendo","SM83/CGB",16384,16384,32768,16384,40,10,512),
    "nes":("Nintendo","6502",8192,8192,2048,16384,64,8,512),
    "snes":("Nintendo","65816",65536,32768,131072,32768,128,32,1024),
    "master_system":("Sega","Z80",16384,16384,8192,16384,64,8,448),
    "game_gear":("Sega","Z80",16384,16384,8192,16384,64,8,448),
    "genesis":("Sega","68000",65536,32768,65536,32768,80,20,1024),
    "game_boy_advance":("Nintendo","ARM7TDMI",98304,32768,32768,16384,128,128,1024),
    "commodore_64":("Commodore","MOS6510",65536,16384,65536,16384,8,8,256),
    "dos_vga":("PC","x86",262144,262144,640000,65536,128,128,8192),
    "ps1":("Sony","MIPS R3000",1048576,131072,2097152,2048,256,256,8192),
    "xbox_original":("Microsoft","x86",67108864,16777216,67108864,65536,1024,1024,1048576),
    # Developer-facing source budgets, not physical linker map verification.
    "nintendo_64":("Nintendo","VR4300",4194304,262144,4194304,65536,128,128,8192),
    "gamecube":("Nintendo","PowerPC Gekko",25165824,8388608,25165824,65536,256,256,4096),
    "wii":("Nintendo","PowerPC Broadway",67108864,8388608,67108864,65536,256,256,8192),
    "nintendo_3ds":("Nintendo","ARM11",6291456,1048576,67108864,65536,256,256,8192),
    "atari_2600":("Atari","6507",128,128,128,4096,2,2,8),
    "apple_ii":("Apple","6502",49152,8192,49152,16384,1,1,512),
    "zx_spectrum":("Sinclair","Z80",6912,6144,49152,16384,8,8,768),
    "dos_8086":("IBM PC","8086",16384,16384,655360,65536,16,16,1024),
    "windows_95":("Microsoft","x86",4194304,4194304,16777216,65536,256,256,16384),
    "nintendo_ds":("Nintendo","ARM9/ARM7",656384,131072,4194304,16384,128,128,8192),
    "psp":("Sony","Allegrex",2097152,524288,33554432,65536,1024,1024,8192),
}
from .dragon_desktop_abi import DESKTOP_NATIVE
PC=DESKTOP_NATIVE
ATLAS_LAYOUT={
    "game_boy":"interleaved_2bpp",
    "game_boy_color":"interleaved_2bpp",
    "nes":"nes_planar_2bpp",
    "snes":"snes_planar4",
    "genesis":"genesis_nibbles",
    "game_boy_advance":"gba_nibbles",
    "master_system":"sega_vdp_planar4",
    "game_gear":"sega_vdp_planar4",
}

def budget_for(target:str)->HardwareBudget:
    if target in PC:
        return HardwareBudget(target,"PC","native x86/ARM",268435456,16777216,
            268435456,16777216,16384,16384,1048576,250000)
    if target not in LIMITS:
        raise ValueError("hardware budget missing for unsupported native target")
    a=LIMITS[target]
    return HardwareBudget(target,a[0],a[1],a[2],a[3],a[4],a[5],
                          a[6],a[7],a[8],250000)

def analyze_project_budget(target:str,files:dict[str,str])->HardwareAudit:
    b=budget_for(target)
    if not isinstance(files,dict) or not files:
        raise ValueError("native source bundle empty")
    if any(not isinstance(n,str) or not isinstance(v,str)
           or len(v.encode("utf-8"))>120000 for n,v in files.items()):
        raise ValueError("native resource source data malformed")
    size=sum(len(v.encode("utf-8")) for v in files.values())
    if size>b.max_source_bundle_bytes:
        raise ValueError("native project source ZIP exceeds bounded quota")
    kind=ATLAS_LAYOUT.get(target,"none")
    tiles=0
    tile_bytes=0
    if "dragon-hardware-art.json" in files:
        data=json.loads(files["dragon-hardware-art.json"])
        if not isinstance(data,dict) or data.get("layout")!=kind:
            raise ValueError("hardware sprite layout does not match target")
        tiles=data.get("tile_count")
        width=data.get("tile_bytes")
        if isinstance(tiles,bool) or not isinstance(tiles,int) or not 0<=tiles<=b.max_sprite_tiles:
            raise ValueError("native graphics exceed tile count capacity")
        if width not in (16,32):
            raise ValueError("unsupported hardware tile byte width")
        tile_bytes=tiles*width
        if tile_bytes>b.tile_graphics_budget_bytes:
            raise ValueError("native tiles exceed conservative graphics budget")
        from .dragon_hw_graphics import source_manifest
        expected=source_manifest(kind)
        if data!=expected:
            raise ValueError("native graphics manifest does not match canonical original sprites")
    if "dragon-pixel-art.json" in files:
        data=json.loads(files["dragon-pixel-art.json"])
        if kind!=data.get("encoding") or not isinstance(data.get("sprites"),list):
            raise ValueError("native 2bpp manifest incompatible with target")
        tiles=len(data["sprites"])
        tile_bytes=tiles*16
        if tiles>b.max_sprite_tiles or tile_bytes>b.tile_graphics_budget_bytes:
            raise ValueError("legacy handheld sprite budget exceeded")
    notes=[]
    if b.max_sprites_per_scanline<16:
        notes.append("scanline OAM limit needs emulator validation")
    if target in ("game_boy","game_boy_color"):
        notes.append("ROM banking and DMA timing not verified by source audit")
    if target in ("ps1","xbox_original"):
        notes.append("authorized native SDK compile and runtime required")
    if target in PC:
        notes.append("native GPU/audio dynamic allocations not verified")
    if "dragon-campaign.json" in files:
        campaign=json.loads(files["dragon-campaign.json"])
        if len(campaign.get("stages",[]))>8:
            raise ValueError("unbounded native campaign")
        notes.append("campaign path proof is static, not actual movement simulation")
    footprint=round(tile_bytes/max(1,b.tile_graphics_budget_bytes),6)
    load=round(size/max(1,b.max_source_bundle_bytes),6)
    report={
        "target":target,"source_bytes":size,"declared_asset_bytes":tile_bytes,
        "claimed_tile_count":tiles,"tile_layout":kind,"budget":asdict(b),
        "limitations":"source data budget only; no linker, scanline, hardware or gameplay proof",
    }
    digest=sha256(json.dumps(report,sort_keys=True,separators=(",",":")).encode()).hexdigest()
    return HardwareAudit(target,"source_budget_checked_only",size,tile_bytes,tiles,
                         kind,footprint,load,tuple(notes),asdict(b),digest)
