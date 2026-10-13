"""Typed, versioned game designs: user-editable input, bounded native compiler.

A game design is deliberately data, not executable code, shell commands,
asset imports or runtime permissions. Strict schema; unknown fields fail
closed. Approved practice is still controlled by its separate owner ledger.
"""
from __future__ import annotations
from dataclasses import dataclass,asdict
from hashlib import sha256
import json,re
from pathlib import Path
from .dragon_native_targets import STYLES,CATALOG
from .dragon_desktop_abi import DESKTOP_NATIVE

FIELDS=frozenset({
  "schema","title","target","genre","palette","stages","candidates",
  "seed","difficulty","hero","quest_theme","project_notes"
})
PALETTES=frozenset(("dmg_green","cga","vga_dusk","crt_arcade","handheld","modern_neon"))
HEROES=frozenset(("hatchling","knight","explorer","pilot","astronaut","robot"))
THEMES=frozenset(("crystals","ancient_ruins","forest","ice","space","volcano","clockwork"))

@dataclass(frozen=True)
class GameDesign:
    schema:str
    title:str
    target:str
    genre:str
    palette:str
    stages:int
    candidates:int
    seed:int
    difficulty:int
    hero:str
    quest_theme:str
    project_notes:str
    digest:str

def parse_design(data:object)->GameDesign:
    if not isinstance(data,dict):
        raise ValueError("game design must be a JSON object")
    if set(data)!=FIELDS:
        raise ValueError("game design has missing or unknown keys")
    def _text(k,pattern,maxlen):
        x=data[k]
        if not isinstance(x,str) or len(x)>maxlen or not re.fullmatch(pattern,x):
            raise ValueError("invalid game design field: "+k)
        return x
    schema=_text("schema",r"skeleton\.ai\.dragon\.game_design\.v1",64)
    title=_text("title",r"[A-Za-z][A-Za-z0-9 ._'!-]{2,79}",80)
    target=_text("target",r"[a-z0-9_]{2,64}",64)
    genre=_text("genre",r"[a-z_]{3,64}",64)
    palette=_text("palette",r"[a-z_]{3,30}",30)
    hero=_text("hero",r"[a-z_]{2,32}",32)
    theme=_text("quest_theme",r"[a-z_]{2,32}",32)
    notes=_text("project_notes",r"[A-Za-z0-9 .,!?_:;'()+-]{0,200}",200)
    for k,low,high in (("stages",1,8),("candidates",1,24),
                       ("seed",0,2**32-1),("difficulty",1,10)):
        val=data[k]
        if isinstance(val,bool) or not isinstance(val,int) or not low<=val<=high:
            raise ValueError("invalid game design integer: "+k)
    if target not in CATALOG:
        raise ValueError("unknown hardware target")
    if genre not in STYLES:
        raise ValueError("unsupported genre identifier")
    if palette not in PALETTES or hero not in HEROES or theme not in THEMES:
        raise ValueError("unknown game art or thematic controls")
    if target not in DESKTOP_NATIVE:
        if data["stages"]!=1 or data["candidates"]!=1:
            raise ValueError("cartridge generator has one stage/seed per design")
        if palette not in ("dmg_green","handheld","vga_dusk"):
            raise ValueError("cartridge palette design not supported by target")
    values={k:data[k] for k in sorted(FIELDS)}
    canonical=json.dumps(values,sort_keys=True,separators=(",",":"),ensure_ascii=True)
    return GameDesign(schema,title,target,genre,palette,data["stages"],
        data["candidates"],data["seed"],data["difficulty"],hero,theme,notes,
        sha256(canonical.encode()).hexdigest())

def load_design(path:Path)->GameDesign:
    path=Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size>16384:
        raise ValueError("game design must be a small regular JSON file")
    raw=path.read_text(encoding="utf-8")
    if len(raw.encode())>16384:
        raise ValueError("game design too large")
    def no_duplicate(pairs):
        result={}
        for k,v in pairs:
            if k in result:raise ValueError("duplicate game design field")
            result[k]=v
        return result
    return parse_design(json.loads(raw,object_pairs_hook=no_duplicate))

def starter_design(*,title="Dragon Deep Quest",target="pc_linux",
                   genre="roguelike",seed=1)->dict:
    return {
        "schema":"skeleton.ai.dragon.game_design.v1",
        "title":title,"target":target,"genre":genre,
        "palette":"vga_dusk","stages":4,"candidates":8,
        "seed":seed,"difficulty":4,"hero":"hatchling",
        "quest_theme":"ancient_ruins",
        "project_notes":"Original local native game; source only",
    }

def design_manifest(design:GameDesign)->dict:
    return asdict(design)
