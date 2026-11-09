"""Original hardware tile art compiler: four genuinely different 4bpp layouts.

Same authored pixels, four layouts:
- SNES Mode 1: 2 interleaved bitplanes x8 rows, then planes 2/3.
- GBA: packed 4-bit nibble low first, row-major.
- Sega Genesis: packed 4-bit nibble high first, row-major.
- SMS/Game Gear: 4 interleaved planar bytes for each of 8 scanlines.

Target palettes are explicit BGR555/CGB or SMS/GG values and every packed
tile round-trips. This creates original assets; no commercial sprites copied.
"""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import re
from .dragon_retro_assets import BITMAPS

LAYOUTS=("snes_planar4","gba_nibbles","genesis_nibbles","sega_vdp_planar4")
MAX_TILES=64

@dataclass(frozen=True)
class TileArtifact:
    name:str
    target_layout:str
    raw_hex:str
    bytes_count:int
    digest:str

def _pixels(pixels:tuple[str,...])->tuple[tuple[int,...],...]:
    if not isinstance(pixels,(tuple,list)) or len(pixels)!=8:
        raise ValueError("hardware tile must be 8x8")
    out=[]
    for row in pixels:
        if not isinstance(row,str) or not re.fullmatch("[0-9a-fA-F]{8}",row):
            raise ValueError("4bpp hardware tile pixels must be 0..15")
        out.append(tuple(int(c,16) for c in row))
    return tuple(out)

def encode_tile(pixels:tuple[str,...],layout:str)->bytes:
    plane=_pixels(pixels)
    if layout not in LAYOUTS:
        raise ValueError("unknown 4bpp layout")
    if layout in ("gba_nibbles","genesis_nibbles"):
        low=layout=="gba_nibbles"
        result=bytes(((row[x] if low else row[x+1])|
                 ((row[x+1] if low else row[x])<<4))
                 for row in plane for x in range(0,8,2))
    else:
        result=[]
        groups=((0,1),(2,3)) if layout=="snes_planar4" else ((0,1,2,3),)
        for group in groups:
            for row in plane:
                for bitplane in group:
                    result.append(sum(((p>>bitplane)&1)<<(7-i)
                                      for i,p in enumerate(row)))
        result=bytes(result)
    if len(result)!=32:
        raise RuntimeError("hardware tile packing length violation")
    return result

def decode_tile(binary:bytes,layout:str)->tuple[str,...]:
    if layout not in LAYOUTS or not isinstance(binary,bytes) or len(binary)!=32:
        raise ValueError("expected 32-byte 4bpp native tile")
    if layout in ("gba_nibbles","genesis_nibbles"):
        low=layout=="gba_nibbles"
        pixels=[]
        for b in binary:
            pixels.extend((b&15,b>>4) if low else (b>>4,b&15))
        return tuple("".join(format(n,"x") for n in pixels[y*8:y*8+8])
                     for y in range(8))
    rows=[[0]*8 for _ in range(8)]
    for y in range(8):
        for k in range(4):
            if layout=="snes_planar4":
                index=(k//2)*16+y*2+(k%2)
            else:index=y*4+k
            byte=binary[index]
            for x in range(8):
                rows[y][x]|=((byte>>(7-x))&1)<<k
    return tuple("".join(format(n,"x") for n in row) for row in rows)

def encode_assets(layout:str,*,extras:dict[str,tuple[str,...]]|None=None
                 )->tuple[TileArtifact,...]:
    if layout not in LAYOUTS:
        raise ValueError("invalid atlas hardware")
    candidates=dict(BITMAPS)
    if extras:
        if not isinstance(extras,dict) or len(extras)>MAX_TILES-len(candidates):
            raise ValueError("asset atlas tile capacity exceeded")
        for name,bitmap in extras.items():
            if not isinstance(name,str) or not re.fullmatch("[a-z][a-z0-9_]{1,31}",name):
                raise ValueError("invalid original tile id")
            if name in candidates:
                raise ValueError("duplicate tile id")
            candidates[name]=bitmap
    artifacts=[]
    for name,bitmap in sorted(candidates.items()):
        content=encode_tile(bitmap,layout)
        if decode_tile(content,layout)!=tuple(row.lower() for row in bitmap):
            raise RuntimeError("hardware tile roundtrip mismatch")
        artifacts.append(TileArtifact(name,layout,content.hex(),32,
                                      sha256(content).hexdigest()))
    return tuple(artifacts)

def atlas_data(layout:str,*,extras=None)->bytes:
    sprites=encode_assets(layout,extras=extras)
    combined=b"".join(bytes.fromhex(tile.raw_hex) for tile in sprites)
    if len(combined)>MAX_TILES*32:
        raise ValueError("native tile atlas exceeds per-bank cap")
    return combined

def atlas_header(layout:str,*,name:str="dragon_native_tiles")->str:
    if not re.fullmatch("[a-z][a-z0-9_]{2,48}",name):
        raise ValueError("native atlas C identifier invalid")
    raw=atlas_data(layout)
    values=", ".join(str(b) for b in raw)
    return (
      "#ifndef DRAGON_ORIGINAL_TILES_H\n#define DRAGON_ORIGINAL_TILES_H\n"
      f"#define DRAGON_TILE_COUNT {len(raw)//32}\n"
      f"#define DRAGON_TILE_BYTES {len(raw)}\n"
      f"static const unsigned char {name}[{len(raw)}]={{"+values+"};\n"
      "#endif\n"
    )

def source_manifest(layout:str)->dict:
    atlas=encode_assets(layout)
    return {"schema":"skeleton.ai.dragon.hw_tiles.v1",
            "layout":layout,"tile_bytes":32,"tile_count":len(atlas),
            "atlas_sha256":sha256(atlas_data(layout)).hexdigest(),
            "assets":[{"name":x.name,"digest":x.digest} for x in atlas],
            "original_only":True,"compiled_hardware_rom":False}
