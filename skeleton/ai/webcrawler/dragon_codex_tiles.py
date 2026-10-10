"""Original hardware-profiled Codex tile atlas, actual encoded game graphics.

Generate 12 independent original 8x8 world/sprite tiles from the source
geology, climate, ecology, human settlements, secret/travel gate traits.
Game Boy/NES tiles are real 2bpp arrangements; SNES tiles use actual 4bpp
planar arrangement. Other targets receive unclaimed indexed reference art,
not a fictional native VRAM layout. All inputs are source-generated original
geometry, with no scraped sprites, proprietary palettes or ROM data.
"""
from __future__ import annotations

from dataclasses import asdict,dataclass
from hashlib import sha256
from .dragon_native_targets import CATALOG
from .dragon_world_codex import CodexAddress,validate
from .dragon_living_world import _sha
from .dragon_codex_platforms import compile_content

SCHEMA="skeleton.ai.dragon.codex_native_tile_atlas.v1"
TILE_SIZE=8
TILES=(
 "ground","rock","water","highland","city","forest",
 "historic_ruin","portal","secret_gate","storm","skybridge","hero",
)
SUPPORTED_NATIVE_LAYOUTS={
 "game_boy":"gb_interleaved_2bpp",
 "game_boy_color":"gb_interleaved_2bpp",
 "nes":"nes_planar_2bpp",
 "snes":"snes_planar_4bpp",
}
REFERENCE_FORMAT="unverified_indexed_tile_reference"
PALETTE_4=("#122017","#446345","#8fa984","#e6f1ce")
PALETTE_16=(
 "#172332","#455e76","#738da8","#bdd6ed",
 "#263d37","#4b8262","#83bc89","#dceec5",
 "#4b3266","#8650a0","#c68abd","#e1cee8",
 "#6b432b","#b07645","#e5b569","#f8dfbd",
)


def _bitmap(address:CodexAddress,name:str,colors:int)->tuple[tuple[int,...],...]:
    _,genes=validate(address)
    if name not in TILES or colors not in (4,16):
        raise ValueError("original game art requires a supported tile archetype")
    c=genes.level
    influence={
        "ground":("substrate_stability","erosion_clock"),
        "rock":("elevation_tectonics","mineral_layers"),
        "water":("ocean_depth","tide_clock"),
        "highland":("sky_islands","prevailing_wind"),
        "city":("urban_density","reconstruction_rate"),
        "forest":("flora_succession","resource_regrowth"),
        "historic_ruin":("unreliable_history","settlement_decay"),
        "portal":("portal_alignment","dimensional_stability"),
        "secret_gate":("secret_density","knowledge_gate_depth"),
        "storm":("storm_fronts","rain_seasons"),
        "skybridge":("aerial_visibility","shortcut_stability"),
        "hero":("story_branching","companion_loyalty"),
    }[name]
    a,b=map(c,influence)
    source=int(_sha([SCHEMA,address.codex_digest,name])[:12],16)
    result=[]
    for y in range(8):
        row=[]
        for x in range(8):
            seed=(source>>(x%6*6))+x*17+y*23+(a*7)+(b*11)
            base=(seed//(1+(a%5)))%colors
            if name in ("water","storm"):
                wave=((x+y//2+(b//16))%4)
                value=(base+wave) %colors
            elif name=="portal":
                ring=(min(x,7-x,y,7-y) in (1,2))
                value=((a//16+3) if ring else base//4)%colors
            elif name=="hero":
                # Original symmetrical face/profile, never borrowed pixels.
                structure=(
                    min(x,7-x)>=1 and 1<=y<=6 and
                    not(y==2 and x in (2,5))
                )
                value=((a//16+6) if structure else base//8)%colors
            elif name=="city":
                structure=(y>=2 and x in (1,2,4,5,6))
                value=((b//16+5) if structure else base)%colors
            elif name=="secret_gate":
                glyph=((x==3 or x==4) and y in (1,2,3,5,6))
                value=((a//16+4) if glyph else base//2)%colors
            elif name=="forest":
                canopy=(x+y)%3==0 or (x in (3,4) and y<6)
                value=((a//16+2) if canopy else base)%colors
            else:value=base
            row.append(value)
        result.append(tuple(row))
    return tuple(result)


def encode_tile(bitmap:tuple[tuple[int,...],...],format:str)->bytes:
    if len(bitmap)!=8 or any(len(row)!=8 for row in bitmap):
        raise ValueError("hardware graphics source must be exact 8x8 tile")
    if format not in (*SUPPORTED_NATIVE_LAYOUTS.values(),REFERENCE_FORMAT):
        raise ValueError("unimplemented native tile byte ordering")
    maximum=15 if format=="snes_planar_4bpp" else (
        3 if format.endswith("2bpp") else 255)
    if any(type(p) is not int or not 0<=p<=maximum
           for row in bitmap for p in row):
        raise ValueError("hardware palette index outside actual bitplane range")
    if format==REFERENCE_FORMAT:
        return bytes(p for row in bitmap for p in row)
    low=[];high=[]
    for row in bitmap:
        plane=[]
        for shift in range(4):
            value=0
            for x,p in enumerate(row):
                value|=((p>>shift)&1)<<(7-x)
            plane.append(value)
        low.extend(plane[:2])
        if format=="snes_planar_4bpp":high.extend(plane[2:])
    if format=="gb_interleaved_2bpp":return bytes(low)
    if format=="nes_planar_2bpp":
        return bytes(low[::2]+low[1::2])
    return bytes(low+high)


def decode_tile(encoded:bytes,format:str)->tuple[tuple[int,...],...]:
    if not isinstance(encoded,bytes):
        raise ValueError("hardware tile decoder expects immutable bytes")
    if format==REFERENCE_FORMAT and len(encoded)==64:
        return tuple(tuple(encoded[y*8:y*8+8]) for y in range(8))
    if format=="snes_planar_4bpp" and len(encoded)==32:
        lo=encoded[:16];hi=encoded[16:]
        planes=[(lo[y*2],lo[y*2+1],hi[y*2],hi[y*2+1]) for y in range(8)]
    elif format=="gb_interleaved_2bpp" and len(encoded)==16:
        planes=[(encoded[y*2],encoded[y*2+1]) for y in range(8)]
    elif format=="nes_planar_2bpp" and len(encoded)==16:
        planes=[(encoded[y],encoded[y+8]) for y in range(8)]
    else:raise ValueError("unrecognized tile format or invalid byte count")
    return tuple(tuple(
        sum(((plane>> (7-x))&1)<<bit
            for bit,plane in enumerate(planes[y]))
        for x in range(8)
    ) for y in range(8))


@dataclass(frozen=True)
class TilePack:
    schema:str
    target_id:str
    native_layout:str
    original_world_digest:str
    named_tiles:tuple[str,...]
    indexed_colors:int
    palette:tuple[str,...]
    tile_hex:tuple[str,...]
    artwork_hashes:tuple[str,...]
    tile_pixels:tuple[tuple[tuple[int,...],...],...]
    all_tile_roundtrips_verified:bool
    compatible_format_encoder:bool
    emitted_into_final_rom:bool
    hardware_verified:bool
    digest:str


def tile_pack(address:CodexAddress,target_id:str)->TilePack:
    validate(address)
    plan=compile_content(address,target_id)
    fmt=SUPPORTED_NATIVE_LAYOUTS.get(target_id,REFERENCE_FORMAT)
    colors=(4 if fmt in ("gb_interleaved_2bpp",
                        "nes_planar_2bpp") else 16)
    # These palettes are authored original reference colors; game-specific
    # palette register handling remains a separate native integration step.
    palette=PALETTE_4 if colors==4 else PALETTE_16
    tiles=tuple(_bitmap(address,name,colors) for name in TILES)
    byteset=tuple(encode_tile(tile,fmt) for tile in tiles)
    if any(decode_tile(raw,fmt)!=pixels for raw,pixels in zip(byteset,tiles)):
        raise ValueError("original tile source did not survive genuine bitplane encoding")
    content={
        "schema":SCHEMA,"target_id":target_id,
        "native_layout":fmt,
        "original_world_digest":address.codex_digest,
        "named_tiles":TILES,"indexed_colors":colors,
        "palette":palette,
        "tile_hex":tuple(data.hex() for data in byteset),
        "artwork_hashes":tuple(sha256(data).hexdigest() for data in byteset),
        "tile_pixels":tiles,
        "all_tile_roundtrips_verified":True,
        "compatible_format_encoder":fmt!=REFERENCE_FORMAT,
        "emitted_into_final_rom":False,
        "hardware_verified":False,
    }
    return TilePack(**content,digest=_sha(content))


def verify_tile_pack(address:CodexAddress,pack:TilePack)->dict:
    if not isinstance(pack,TilePack) or pack.schema!=SCHEMA:
        raise ValueError("Codex original tile pack identity absent")
    actual=tile_pack(address,pack.target_id)
    if actual!=pack:
        raise ValueError("Codex original visual game data changed after encoding")
    return {
        "verified":True,"tiles":len(pack.named_tiles),
        "target":pack.target_id,
        "format":pack.native_layout,
        "binary_game_claim":False,
        "artwork_sha256":pack.digest,
        "original_game_geometry":True,
    }
