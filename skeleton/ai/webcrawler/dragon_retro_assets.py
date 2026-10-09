"""Small original sprite compiler for real 8-bit hardware tile encodings.

One pixel may only use palette index 0..3. GB stores interleaved bitplanes,
NES stores first plane for all eight rows followed by second plane. Tiles
are intentionally tiny and source-controlled; no copyrighted ROM pixels.
"""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import re

BITMAPS = {
    "dragon": (
        "00011000","00122200","01222220","12233221",
        "12233221","12222221","01222210","00122100"),
    "dragon_blink": (
        "00011000","00122200","01222220","12222221",
        "12233221","12222221","01222210","00122100"),
    "dragon_walk": (
        "00011000","00122200","01222220","12233221",
        "12233221","12222221","00122210","01100110"),
    "dragon_flap": (
        "11011011","12122121","12222221","12233221",
        "12233221","12222221","01222210","00122100"),
    "star": (
        "00011000","00122100","11222211","01233210",
        "00122100","01100110","10000001","00000000"),
    "enemy": (
        "01111110","12222221","12322321","12222221",
        "12333321","12211221","01011010","10000001"),
    "heart": (
        "00000000","01100110","12211221","12222221",
        "01222210","00122100","00011000","00000000"),
    "portal": (
        "00111100","01222210","12200221","12000021",
        "12000021","12200221","01222210","00111100"),
}
NAMES = tuple(BITMAPS)

@dataclass(frozen=True)
class RetroTile:
    name: str
    digest: str
    gb: bytes
    nes: bytes

def _validate(bitmap: tuple[str, ...]) -> None:
    if len(bitmap)!=8 or any(len(row)!=8 or set(row)-set("0123") for row in bitmap):
        raise ValueError("original tile must contain eight 2bpp rows")

def compile_tile(name: str, bitmap: tuple[str, ...]) -> RetroTile:
    if not isinstance(name,str) or not re.fullmatch("[a-z_]{2,64}",name):
        raise ValueError("invalid sprite name")
    _validate(bitmap)
    low,high=[],[]
    for row in bitmap:
        lo=hi=0
        for x,pixel in enumerate(row):
            n=int(pixel)
            lo|=(n&1) << (7-x)
            hi|=((n>>1)&1) << (7-x)
        low.append(lo);high.append(hi)
    gb=bytes(n for pair in zip(low,high) for n in pair)
    nes=bytes(low+high)
    return RetroTile(name,sha256("\n".join(bitmap).encode()).hexdigest(),gb,nes)

def decode_tile(data: bytes, *, target:str) -> tuple[str,...]:
    if len(data)!=16 or target not in ("gb","nes"):
        raise ValueError("2bpp tile is exactly 16 bytes")
    lo=data[0::2] if target=="gb" else data[:8]
    hi=data[1::2] if target=="gb" else data[8:]
    return tuple("".join(str((((hi[y]>>(7-x))&1)<<1)
                         |((lo[y]>>(7-x))&1)) for x in range(8))
                 for y in range(8))

def asset_tiles() -> tuple[RetroTile,...]:
    return tuple(compile_tile(name,BITMAPS[name]) for name in NAMES)

def gb_assembly() -> str:
    out=["Tiles:"]
    for tile in asset_tiles():
        out.append("    ; original "+tile.name)
        for i in range(0,16,8):
            out.append("    db "+",".join(f"${n:02X}" for n in tile.gb[i:i+8]))
    out.append("TilesEnd:")
    return "\n".join(out)

def nes_assembly() -> str:
    out=[]
    tiles=asset_tiles()
    for tile in tiles:
        out.append("; original "+tile.name)
        out.append("    .byte "+",".join(f"${n:02X}" for n in tile.nes[:8]))
        out.append("    .byte "+",".join(f"${n:02X}" for n in tile.nes[8:]))
    out.append(f"    .res $2000-{len(tiles)*16},0")
    return "\n".join(out)

def enrich_gb_asm(source:str) -> str:
    if not isinstance(source,str):raise ValueError("GB source required")
    source,n=re.subn(r"(?s)Tiles:\n.*?\nTilesEnd:",gb_assembly(),source)
    if n!=1:raise ValueError("GB tile section missing")
    # Blinking sprite indexes alternate idle/blink, under VBlank OAM refresh.
    before="""    xor a
    ld [OAM+2], a
    ld [OAM+3], a"""
    after="""    ld hl, AnimFrame
    inc [hl]
    ld a, [hl]
    and $3F
    jr nz, .idle
    ld a, 1
    jr .paint
.idle:
    xor a
.paint:
    ld [OAM+2], a
    xor a
    ld [OAM+3], a"""
    if before not in source:raise ValueError("GB sprite update anchor unavailable")
    source=source.replace(before,after)
    if "PlayerY: ds 1" not in source:raise ValueError("GB WRAM declaration missing")
    source=source.replace("PlayerY: ds 1","PlayerY: ds 1\nAnimFrame: ds 1")
    if "    ld a, 48\n    ld [PlayerX], a" not in source:
        raise ValueError("GB boot sequence missing")
    source=source.replace("    ld a, 48\n    ld [PlayerX], a",
                          "    xor a\n    ld [AnimFrame], a\n    ld a, 48\n    ld [PlayerX], a")
    # Star tile moved to index 4.
    if "    ld a, 1\n    ld [OAM+6], a" not in source:
        raise ValueError("GB collectible sprite declaration missing")
    return source.replace("    ld a, 1\n    ld [OAM+6], a",
                          "    ld a, 4\n    ld [OAM+6], a")

def enrich_nes_asm(source:str) -> str:
    if not isinstance(source,str):raise ValueError("NES source required")
    replace=".segment \"CHARS\"\n"+nes_assembly()+"\n"
    source,n=re.subn(r'(?s)\.segment "CHARS"\n.*\Z',lambda _:replace,source)
    if n!=1:raise ValueError("NES CHR section missing")
    # Star sprite moved to tile 4.
    if "    lda #1\n    sta $0205" not in source:
        raise ValueError("NES collectible tile anchor missing")
    return source.replace("    lda #1\n    sta $0205",
                          "    lda #4\n    sta $0205")
