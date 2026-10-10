"""Deterministic original GB/NES artwork embedded into live cartridge ROM source.

Eight source-controlled, royalty-clean tile silhouettes have original variants
for hero, theme and tonal palette. Encoders produce native interleaved Game
Boy and planar NES 2bpp tiles, not image files disguised as ROM graphics.
"""
from __future__ import annotations
from dataclasses import asdict,dataclass
from hashlib import sha256
import json,re
from .dragon_retro_assets import BITMAPS,NAMES,compile_tile
from .dragon_game_design import HEROES,THEMES,PALETTES

SCHEMA="skeleton.ai.dragon.original_native_art.v1"
TARGETS=frozenset(("game_boy","game_boy_color","nes"))
FILENAME="dragon-native-art.json"

HEROES_8={
 "hatchling":BITMAPS["dragon"],
 "knight":("01111110","01333310","01222210","11233211","12222221","12122121","01222210","01100110"),
 "explorer":("00011000","01122110","11111111","01233210","12222221","12211221","01222210","00100100"),
 "pilot":("01111110","01222210","13333331","12322321","12222221","11222211","00122100","01100110"),
 "astronaut":("00111100","01222210","12333321","12322321","12222221","01222210","01122110","01100110"),
 "robot":("00011000","01111110","12222221","12322321","12333321","12211221","01222210","01011010"),
}
THEMES_8={
 "crystals":("00011000","00122100","01233210","12333321","01233210","00122100","00011000","00000000"),
 "ancient_ruins":("00111100","01122110","01233210","01233210","01233210","01122110","00111100","00000000"),
 "forest":("00011000","00122100","01233210","12233221","01122110","00122100","00011000","00011000"),
 "ice":("01011010","00122100","11233211","01233210","00122100","01011010","10000001","00000000"),
 "space":("00011000","00122100","11233211","12333321","01233210","00122100","00122100","00000000"),
 "volcano":("00022000","00122000","01233210","01233210","12233221","12333321","01122110","00011000"),
 "clockwork":("01011010","01122110","12333321","12211221","12211221","12333321","01122110","01011010"),
}
TONES={
 "dmg_green":"0123","handheld":"0213","vga_dusk":"0132",
 "cga":"0312","crt_arcade":"0231","modern_neon":"0321",
}

@dataclass(frozen=True)
class TileArt:
    schema:str
    hero:str
    quest_theme:str
    palette:str
    seed:int
    target:str
    tile_order:tuple[str,...]
    pixel_digests:tuple[str,...]
    gb_source_digest:str
    nes_source_digest:str
    runtime_applied:bool
    video_claim:str


def _paint(bitmap:tuple[str,...],palette:str)->tuple[str,...]:
    lut=dict(zip("0123",TONES[palette]))
    return tuple("".join(lut[x] for x in line) for line in bitmap)


def _blink(image:tuple[str,...])->tuple[str,...]:
    rows=[list(row) for row in image]
    for y in (3,4):
        for x in (2,5):
            if rows[y][x] in ("2","3"):rows[y][x]="1"
    return tuple("".join(row) for row in rows)


def _motion(image:tuple[str,...],seed:int)->tuple[str,...]:
    rows=[list(row) for row in image]
    rows[7]=["0"]*8
    for x in ((0,3,4,7) if seed&1 else (1,2,5,6)):
        rows[7][x]="1"
    return tuple("".join(row) for row in rows)


def _wings(image:tuple[str,...])->tuple[str,...]:
    rows=[list(row) for row in image]
    rows[4][0:2]=["1","2"]
    rows[4][6:8]=["2","1"]
    rows[5][0:2]=["1","1"]
    rows[5][6:8]=["1","1"]
    return tuple("".join(row) for row in rows)


def original_tiles(*,hero:str,theme:str,palette:str,seed:int)->dict[str,tuple[str,...]]:
    if hero not in HEROES or hero not in HEROES_8 or theme not in THEMES or palette not in PALETTES:
        raise ValueError("unapproved native homebrew art request")
    if type(seed) is not int or not 0<=seed<=0xffffffff:
        raise ValueError("original sprite art needs uint32 seed")
    base=HEROES_8[hero]
    enemy=[list(row) for row in BITMAPS["enemy"]]
    if (seed>>3)&1:
        enemy[2][2]=enemy[2][5]="1"
    source={
        "dragon":base,"dragon_blink":_blink(base),
        "dragon_walk":_motion(base,seed),"dragon_flap":_wings(base),
        "star":THEMES_8[theme],
        "enemy":tuple("".join(x) for x in enemy),
        "heart":BITMAPS["heart"],"portal":BITMAPS["portal"],
    }
    return {name:_paint(source[name],palette) for name in NAMES}


def raw_tile_data(tiles:dict[str,tuple[str,...]],platform:str)->bytes:
    if platform not in ("gb","nes") or tuple(tiles)!=NAMES:
        raise ValueError("invalid target tile layout or order")
    return b"".join(getattr(compile_tile(name,tiles[name]),platform) for name in NAMES)


def source_asm(tiles:dict[str,tuple[str,...]],style:str,target:str)->tuple[str,str,str]:
    if target=="game_boy" and style=="side_scrolling_platformer":
        original={name:compile_tile(name,tiles[name]).gb for name in NAMES}
        blank=bytes(16)
        brick=bytes([255,0]+[129,0]*6+[255,0])
        data=(blank,brick,original["dragon"],original["star"],original["dragon_blink"])
        lines=["PlatformTiles:"]
        for tile in data:
            for off in (0,8):
                lines.append("    db "+",".join("$"+format(x,"02X") for x in tile[off:off+8]))
        lines.append("PlatformTilesEnd:")
        return ("src/main.asm",r"(?s)PlatformTiles:\n.*?\nPlatformTilesEnd:","\n".join(lines))
    if target in ("game_boy","game_boy_color"):
        data=raw_tile_data(tiles,"gb")
        lines=["Tiles:"]
        for i,name in enumerate(NAMES):
            lines.append("    ; original "+name)
            for off in (0,8):
                part=data[i*16+off:i*16+off+8]
                lines.append("    db "+",".join("$"+format(x,"02X") for x in part))
        lines.append("TilesEnd:")
        return ("src/main.asm",r"(?s)Tiles:\n.*?\nTilesEnd:","\n".join(lines))
    if target=="nes":
        data=raw_tile_data(tiles,"nes")
        lines=['.segment "CHARS"']
        for i,name in enumerate(NAMES):
            lines.append("; original "+name)
            for off in (0,8):
                part=data[i*16+off:i*16+off+8]
                lines.append("    .byte "+",".join("$"+format(x,"02X") for x in part))
        lines.append("    .res $2000-"+str(len(NAMES)*16)+",0")
        return ("src/main.s",r'(?s)\.segment "CHARS"\n.*\Z',"\n".join(lines)+"\n")
    raise ValueError("requested cartridge art has no native video adapter")


def make_art(*,hero:str,theme:str,palette:str,seed:int,target:str):
    if target not in TARGETS:raise ValueError("no real cartridge art adapter")
    tiles=original_tiles(hero=hero,theme=theme,palette=palette,seed=seed)
    art=TileArt(
        SCHEMA,hero,theme,palette,seed,target,NAMES,
        tuple(sha256("\n".join(tiles[name]).encode()).hexdigest() for name in NAMES),
        sha256(raw_tile_data(tiles,"gb")).hexdigest(),
        sha256(raw_tile_data(tiles,"nes")).hexdigest(),
        True,"2bpp video tile source applied; not emulator or device certification",
    )
    return art,tiles


def apply_original_art(files:dict[str,str],*,art:TileArt,tiles:dict,style:str)->dict[str,str]:
    """Rewrite precisely the video tile section; retain game logic and tile IDs."""
    filename,pattern,replacement=source_asm(tiles,style,art.target)
    if filename not in files:
        raise ValueError("original native cartridge missing video source")
    updated=dict(files)
    updated[filename],matches=re.subn(pattern,lambda _:replacement,files[filename],count=1)
    if matches!=1:raise ValueError("native original-art video section absent")
    updated[FILENAME]=json.dumps(asdict(art),sort_keys=True,indent=2)+"\n"
    return updated


def verify_original_art(files:dict[str,str],port_plan:dict|None,style:str)->dict|None:
    if FILENAME not in files:
        if port_plan and port_plan.get("target") in TARGETS:
            raise ValueError("approved game port failed to embed original art")
        return None
    if not isinstance(port_plan,dict) or port_plan.get("target") not in TARGETS:
        raise ValueError("unapproved native cartridge art claim")
    try:
        profile=port_plan["portable_profile"]
        target=port_plan["target"]
        art,tiles=make_art(
            hero=profile["hero"],theme=profile["quest_theme"],
            palette=port_plan["target_palette"],
            seed=port_plan["production_seed"],target=target,
        )
        manifest=json.loads(files[FILENAME])
        if manifest!=json.loads(json.dumps(asdict(art))):
            raise ValueError("cartridge art contents do not match claimed design")
        source_file,pattern,replacement=source_asm(tiles,style,target)
        observed=re.search(pattern,files[source_file])
        if observed is None or observed.group() != replacement:
            raise ValueError("cartridge runtime tile bytes are not original artwork")
    except (KeyError,ValueError,TypeError) as exc:
        raise ValueError("native art source cannot be independently reconstructed") from exc
    return {"schema":SCHEMA,"target":target,"sprites_verified":len(NAMES),
            "scope":"original 2bpp cartridge bytes; no emulator certification"}
