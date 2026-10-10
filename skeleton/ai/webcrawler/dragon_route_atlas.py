"""Hierarchical original maze atlas: 12 certified worlds, player-chosen routes.

Each region is an independently playable, source-replayable original maze.
Region exits form a forward-only branching graph with both a fast skip route
and a scenic visit-all route to the *same reachable final goal*. A portal
cannot fire before the source region's real objective has been reached.

Scale is compositional (up to 576 certified rooms per atlas), not a claim
that all those rooms fit into the existing 48-node C99 runtime. The
cross-region state machine is implemented in Python; each region may be
emitted as a separate native C99 game with its own proof.
"""
from __future__ import annotations
from dataclasses import asdict,dataclass,replace
from functools import lru_cache
from hashlib import sha256
import json

from .dragon_route_maze import MazeRequest,MazeCreation,build_maze,verify_maze
from .dragon_route_world import replay,experience,MAX_HOPS

SCHEMA="skeleton.ai.dragon.certified_route_atlas.v1"
MAX_REGIONS=12
MAX_ATLAS_ACTIONS=512
MAX_TOTAL_ROOMS=576


@dataclass(frozen=True)
class AtlasRequest:
    seed:int=1977
    regions:int=4
    width:int=6
    height:int=6
    climate:str="clear"
    challenge:str="balanced"
    scenic_density:int=60
    detour_density:int=70
    secret_count:int=2


@dataclass(frozen=True)
class AtlasProof:
    schema:str
    regions:int
    rooms:int
    world_sha256:tuple[str,...]
    regional_certificate_digests:tuple[str,...]
    progression:tuple[tuple[int,...],...]
    fast_regional_route:tuple[int,...]
    scenic_regional_route:tuple[int,...]
    fast_replay_commands:tuple[str,...]
    scenic_replay_commands:tuple[str,...]
    distinct_regional_goal_paths:int
    reachable_regions:tuple[int,...]
    overall_goal_verified:bool
    all_room_proofs_available:bool
    regional_climates_verified:bool
    guarantee_scope:str
    digest:str


@dataclass(frozen=True)
class Atlas:
    request:AtlasRequest
    worlds:tuple[MazeCreation,...]
    proof:AtlasProof


def _canonical(obj)->bytes:
    return json.dumps(obj,sort_keys=True,separators=(",",":"),
                      ensure_ascii=True).encode("ascii")


def _validate_request(req:AtlasRequest):
    if not isinstance(req,AtlasRequest):
        raise ValueError("route atlas requires typed original world intent")
    if type(req.regions) is not int or not 2<=req.regions<=MAX_REGIONS:
        raise ValueError("original atlas must have 2..12 actual maze regions")
    if type(req.seed) is not int or not 0<=req.seed<2**32:
        raise ValueError("original atlas source seed must be uint32")
    if type(req.width) is not int or not 4<=req.width<=8 or (
            type(req.height) is not int or not 4<=req.height<=6):
        raise ValueError("atlas rooms exceed maze width and height bounds")
    if type(req.scenic_density) is not int or not 0<=req.scenic_density<=100 or (
        type(req.detour_density) is not int or not 0<=req.detour_density<=100 or
        type(req.secret_count) is not int or not 0<=req.secret_count<=4
    ):
        raise ValueError("atlas scenic/secret density outside native limits")
    if req.width*req.height*req.regions>MAX_TOTAL_ROOMS:
        raise ValueError("composed original atlas exceeds 576 playable rooms")
    if req.climate not in ("clear","rain","windy","storm","snow","high_tide"):
        raise ValueError("atlas climate not implemented by maze physics")
    if req.challenge not in ("gentle","balanced","challenging","spicy"):
        raise ValueError("atlas difficulty is not an implemented game intent")


def _progression(regions:int)->tuple[tuple[int,...],...]:
    return tuple(
        tuple(v for v in (index+1,index+2) if v<regions)
        if index<regions-1 else ()
        for index in range(regions)
    )


def _route_regions(exits:tuple[tuple[int,...],...],*,fast:bool)->tuple[int,...]:
    path=[0]
    while exits[path[-1]]:
        path.append(exits[path[-1]][-1 if fast else 0])
        if len(path)>len(exits):
            raise ValueError("regional maze world progression contains an impossible loop")
    if path[-1]!=len(exits)-1:
        raise ValueError("regional route never reaches final world goal")
    return tuple(path)


def _actions(worlds:tuple[MazeCreation,...],route:tuple[int,...])->tuple[str,...]:
    moves=[]
    for step,index in enumerate(route):
        moves.extend(worlds[index].certificate.backbone)
        if step<len(route)-1:
            moves.append(f"portal_{route[step+1]}")
    if len(moves)>MAX_ATLAS_ACTIONS:
        raise ValueError("composed original game journey exceeds bounded action history")
    return tuple(moves)


def play_atlas(atlas:Atlas,commands:tuple[str,...]=())->dict:
    """Verify *real* room actions before allowing region portal selection."""
    if not isinstance(atlas,Atlas):
        raise ValueError("original route atlas identity unavailable")
    if (not isinstance(commands,tuple) or len(commands)>MAX_ATLAS_ACTIONS or
            any(type(command) is not str or not 1<=len(command)<=48
                for command in commands)):
        raise ValueError("world-scale route history is invalid or too large")
    worlds=atlas.worlds
    index=0
    local=[]
    stages=[0]
    choices=atlas.proof.progression
    for action in commands:
        if action.startswith("portal_"):
            text=action.removeprefix("portal_")
            if not text.isdecimal() or not text or len(text)>3:
                raise ValueError("original region portal target is malformed")
            target=int(text)
            played=experience(
                worlds[index].world,worlds[index].traveller,
                path=tuple(local),
            )
            if not played["completed"] or target not in choices[index]:
                raise ValueError("cannot skip uncleared original region or invent portal")
            index=target
            local=[]
            stages.append(target)
        else:
            if len(local)>=MAX_HOPS:
                raise ValueError("one original region exceeds playable action budget")
            local.append(action)
    current=experience(
        worlds[index].world,worlds[index].traveller,path=tuple(local),
    )
    done=(index==len(worlds)-1 and current["completed"])
    options=[{
        "destination":next_index,
        "command":f"portal_{next_index}",
        "route_type":"shortcut" if next_index>index+1 else "exploration",
        "available":current["completed"],
    } for next_index in choices[index]]
    return {
        "schema":SCHEMA,"region":index,
        "total_regions":len(worlds),"visited_regions":stages,
        "played_commands":list(commands),
        "regional_play":current,
        "portal_choices":options,
        "completed_world":done,
        "guarantee":"composable native region completion with runtime-verified portals",
    }


def _digest_without_signature(proof:dict)->str:
    return sha256(_canonical(proof)).hexdigest()


@lru_cache(maxsize=4)
def build_atlas(req:AtlasRequest=AtlasRequest())->Atlas:
    _validate_request(req)
    sectors=[]
    for index in range(req.regions):
        level_seed=(req.seed+index*0x9e3779b9)&0xffffffff
        sector=build_maze(MazeRequest(
            seed=level_seed,width=req.width,height=req.height,
            scenic_density=req.scenic_density,
            detour_density=req.detour_density,
            secret_count=req.secret_count,
            weather=req.climate,challenge=req.challenge,
        ))
        sectors.append(sector)
    worlds=tuple(sectors)
    exits=_progression(req.regions)
    fast=_route_regions(exits,fast=True)
    scenic=_route_regions(exits,fast=False)
    quick_moves=_actions(worlds,fast)
    scenic_moves=_actions(worlds,scenic)
    # Count exact different topological final-goal paths without exhausting
    # combinatorial variants or claiming playtime observations.
    counts=[0]*req.regions
    counts[-1]=1
    for index in range(req.regions-2,-1,-1):
        counts[index]=sum(counts[next_index] for next_index in exits[index])
    fingerprint={
        "schema":SCHEMA,"regions":req.regions,
        "rooms":req.regions*req.width*req.height,
        "world_sha256":tuple(x.certificate.world_digest for x in worlds),
        "regional_certificate_digests":tuple(
            x.certificate.certificate_digest for x in worlds),
        "progression":exits,
        "fast_regional_route":fast,"scenic_regional_route":scenic,
        "fast_replay_commands":quick_moves,
        "scenic_replay_commands":scenic_moves,
        "distinct_regional_goal_paths":counts[0],
        "reachable_regions":tuple(range(req.regions)),
        "overall_goal_verified":True,
        "all_room_proofs_available":all(
            x.certificate.location_recovery_count==len(x.world.places)
            for x in worlds),
        "regional_climates_verified":all(
            len(x.certificate.all_climates_backbone_verified)==6
            for x in worlds),
        "guarantee_scope":(
            "Every sub-maze has independent room/climate completion; multiple "
            "actual region choice routes finish via replayed original mechanics. "
            "Regions are composed by the Python portal runtime; a single huge "
            "native C99 executable and arbitrary exhausted-state solvability "
            "are not yet certified."),
    }
    proof=AtlasProof(**fingerprint,digest=_digest_without_signature(fingerprint))
    atlas=Atlas(req,worlds,proof)
    if not play_atlas(atlas,quick_moves)["completed_world"] or (
        not play_atlas(atlas,scenic_moves)["completed_world"]
    ):
        raise ValueError("constructive world-scale route failed actual portal replay")
    return atlas


def verify_atlas(atlas:Atlas)->dict:
    """Reject changed regional geometry, progression, weather and witnesses."""
    if not isinstance(atlas,Atlas) or atlas.proof.schema!=SCHEMA:
        raise ValueError("unknown world-scale route atlas certificate")
    original=build_atlas(atlas.request)
    if (asdict(original.proof)!=asdict(atlas.proof) or
            len(original.worlds)!=len(atlas.worlds)):
        raise ValueError("world-scale route progression proof changed")
    for source,fresh in zip(atlas.worlds,original.worlds):
        if (asdict(source)!=asdict(fresh) or
                verify_maze(source)["status"]!="constructively_complete"):
            raise ValueError("one region of the original world failed independent proof")
    return {
        "schema":SCHEMA,"status":"hierarchical_completion_verified",
        "rooms":atlas.proof.rooms,"regions":atlas.proof.regions,
        "regional_routes":atlas.proof.distinct_regional_goal_paths,
        "climate_completion":atlas.proof.regional_climates_verified,
        "claim":atlas.proof.guarantee_scope,
    }


def atlas_report(atlas:Atlas)->dict:
    """Lightweight UI projection: don't dump 576 rooms' complete source in API."""
    return {"schema":SCHEMA,"proof":asdict(atlas.proof),
            "regional":tuple({
                "index":number,
                "rooms":len(item.world.places),
                "deadends":len(item.certificate.real_dead_ends),
                "secrets":len(item.certificate.secret_witnesses),
                "scenic_tours":len(item.certificate.scenic_witnesses),
                "maze_digest":item.certificate.world_digest,
            } for number,item in enumerate(atlas.worlds))}
