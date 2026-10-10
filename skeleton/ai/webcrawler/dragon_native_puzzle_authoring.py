"""Original authored Sokoban level packs for native executable game production.

No raw source code or executable behavior may enter this plane. Users create
exact 12x10 ASCII-grid puzzles with 1..3 crates, matching goals, one avatar,
walls and floor. The canonical bounded BFS solver proves each level playable
before *any* target source files are generated.

These layouts are originals attested by their authors, not copied commercial
maps, emulator screenshots, Nintendo ROM levels or third-party assets.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import json

SCHEMA="skeleton.ai.dragon.original_puzzle_level_pack.v1"
MAX_LEVELS=8
WIDTH=12
HEIGHT=10
MAX_FILE_BYTES=8192
MAX_SOLVER_STATES=120000
ALLOWED=frozenset("#.@$o")


@dataclass(frozen=True)
class AuthoredLevel:
    order:int
    rows:tuple[str,...]
    layout_sha256:str
    shortest_solution:str
    shortest_moves:int
    explored_states:int
    crate_count:int


@dataclass(frozen=True)
class AuthoredCampaign:
    schema:str
    levels:tuple[AuthoredLevel,...]
    digest:str

    @property
    def rows(self)->tuple[tuple[str,...],...]:
        return tuple(x.rows for x in self.levels)


def level_digest(rows:tuple[str,...])->str:
    return sha256("\n".join(rows).encode("ascii")).hexdigest()


def validate_authored_levels(levels:tuple[tuple[str,...],...])->AuthoredCampaign:
    from .dragon_native_puzzle import solve_grid,_parse
    if not isinstance(levels,tuple) or not 1<=len(levels)<=MAX_LEVELS:
        raise ValueError("author must supply one to eight canonical original stages")
    built=[]
    used=set()
    for order,rows in enumerate(levels):
        if not isinstance(rows,tuple) or len(rows)!=HEIGHT or any(
            not isinstance(line,str) or len(line)!=WIDTH or
            set(line)-ALLOWED for line in rows
        ):
            raise ValueError("authored native stage is not a bounded 12x10 ASCII grid")
        identity=level_digest(rows)
        if identity in used:
            raise ValueError("repeated native stage is not an original campaign progression")
        used.add(identity)
        _,crates,_,_=_parse(rows)
        path,states=solve_grid(rows)
        if not 1<=len(path)<=400 or not 1<=states<=MAX_SOLVER_STATES:
            raise ValueError("original authored stage exceeds solver/replay budget")
        built.append(AuthoredLevel(
            order,rows,identity,path,len(path),states,len(crates),
        ))
    material=json.dumps(
        [{"stage":x.order,"sha256":x.layout_sha256,"path":x.shortest_solution}
         for x in built],
        sort_keys=True,separators=(",",":"),ensure_ascii=True,
    ).encode("ascii")
    return AuthoredCampaign(SCHEMA,tuple(built),sha256(material).hexdigest())


def authored_document(levels:tuple[tuple[str,...],...])->dict:
    campaign=validate_authored_levels(levels)
    return {
        "schema":SCHEMA,
        "level_count":len(campaign.levels),
        "levels":[list(level.rows) for level in campaign.levels],
        "digest":campaign.digest,
        "claim":"source-only original authored grids, proved solvable, not legally cleared",
    }


def parse_authored_document(data:object)->AuthoredCampaign:
    if not isinstance(data,dict) or set(data)!={
        "schema","level_count","levels","digest","claim",
    }:
        raise ValueError("original level pack must use exact canonical fields")
    if data["schema"]!=SCHEMA or data["claim"]!=(
        "source-only original authored grids, proved solvable, not legally cleared"
    ):
        raise ValueError("unknown or elevated original game authorship claim")
    raw=data["levels"]
    if not isinstance(raw,list) or not 1<=len(raw)<=MAX_LEVELS or (
        type(data["level_count"]) is not int or data["level_count"]!=len(raw)
    ):
        raise ValueError("invalid original level pack size")
    if any(not isinstance(grid,list) for grid in raw):
        raise ValueError("authored levels must be arrays of ASCII rows")
    levels=tuple(tuple(row for row in grid) for grid in raw)
    result=validate_authored_levels(levels)
    if data["digest"]!=result.digest:
        raise ValueError("signed-scope original level pack digest changed")
    return result


def load_authored_level_pack(path:Path)->AuthoredCampaign:
    location=Path(path).expanduser().absolute()
    if any(part.is_symlink() for part in (location,*location.parents)):
        raise ValueError("symlinked custom level packs are not accepted")
    if not location.is_file() or location.stat().st_size>MAX_FILE_BYTES:
        raise ValueError("authored level pack file missing or over budget")
    binary=location.read_bytes()
    if len(binary)>MAX_FILE_BYTES:
        raise ValueError("authored level pack content over budget")
    def unique(pairs):
        result={}
        for name,value in pairs:
            if name in result:
                raise ValueError("duplicate original authored level pack field")
            result[name]=value
        return result
    data=json.loads(binary.decode("utf-8"),object_pairs_hook=unique)
    return parse_authored_document(data)


def starter_authored_levels(stages:int=1)->dict:
    from .dragon_native_puzzle import transformed_level
    if type(stages) is not int or not 1<=stages<=MAX_LEVELS:
        raise ValueError("invalid original puzzle starter level count")
    generated=tuple(transformed_level(i,1977,difficulty=4) for i in range(stages))
    return authored_document(generated)


def preview_authored_levels(levels:tuple[tuple[str,...],...])->dict:
    """Pure input validation. Never emits source, calls toolchains or writes files."""
    campaign=validate_authored_levels(levels)
    return {
        "ok":True,
        "schema":SCHEMA,
        "digest":campaign.digest,
        "total_stages":len(campaign.levels),
        "stages":[{
            "stage":x.order+1,"layout_sha256":x.layout_sha256,
            "shortest_moves":x.shortest_moves,
            "solver_states":x.explored_states,
            "crates":x.crate_count,
        } for x in campaign.levels],
        "scope":"exact bounded Sokoban solver, not compiled game or legal approval",
    }
