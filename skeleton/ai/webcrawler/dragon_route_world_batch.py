"""Deterministic production-scale ORIGINAL game-world route candidate ledger.

Bounded resumable batches make procedural search operable across millions of
distinct possible seeds without claiming a seed is a finished game, unique
creative work or legally cleared publication. Full game approval remains a
separate art/story/physics/player-testing/licensing and native-build gate.
"""
from __future__ import annotations
from dataclasses import dataclass,asdict
from hashlib import sha256
from pathlib import Path
import json,os

from .dragon_route_world_factory import make_frontier,scenario_digest
from .dragon_route_world_assurance import audit_world
from .dragon_route_world import plan,SCHEMA as WORLD_SCHEMA
from .dragon_route_taxonomy import MODES

SCHEMA="skeleton.ai.dragon.route_candidate_ledger.v1"
MAX_BATCH=32
LEGAL_HOLDS=(
    "original_expression_similarity_review",
    "copyright_and_derivative_rights_review",
    "trademarks_and_trade_dress_review",
    "patent_and_platform_license_review",
    "art_music_story_and_character_origination",
    "actual_native_binary_and_device_validation",
    "representative_player_playtests",
)

@dataclass(frozen=True)
class WorldCandidate:
    seed:int
    weather:str
    start_hour:int
    digest:str
    graph_fingerprint:str
    places:int
    transitions:int
    travel_families:tuple[str,...]
    shortest_minutes:int
    shortest_segments:int
    secret_connections:int
    true_loops:int
    structural_warnings:tuple[str,...]
    status:str
    external_content_imported:bool
    shipped_full_game:bool

@dataclass(frozen=True)
class WorldBatch:
    schema:str
    start_seed:int
    next_seed:int
    attempted:int
    admitted:int
    rejected:int
    candidates:tuple[WorldCandidate,...]
    rejected_reasons:tuple[str,...]
    unique_content_digests:int
    produced_finished_games:int
    legal_holds:tuple[str,...]
    claim:str


def _quantized_structure(world)->str:
    """Coarse variety bucket, not a legally definitive similarity fingerprint."""
    edges=sorted((
        edge.id,edge.mode,edge.origin,edge.destination,
        *sorted(edge.shapes),
    ) for edge in world.connections)
    material=json.dumps(edges,sort_keys=True,separators=(",",":"))
    return sha256(material.encode("utf-8")).hexdigest()

def create_candidate_batch(*,start_seed:int,count:int,weather:str="clear",
                           hour:int=8,examined_digests:frozenset[str]=frozenset(),
                           audit_budget:int=1200)->WorldBatch:
    if type(start_seed) is not int or not 0<=start_seed<2**32:
        raise ValueError("original world batch seed outside uint32")
    if type(count) is not int or not 1<=count<=MAX_BATCH or (
            start_seed+count>2**32):
        raise ValueError("original candidate batch beyond seed or resource budget")
    if (not isinstance(examined_digests,frozenset) or
            len(examined_digests)>10000 or
            any(type(x) is not str or len(x)!=64 or
                any(ch not in "0123456789abcdef" for ch in x)
                for x in examined_digests)):
        raise ValueError("previous route-content digest cursor malformed")
    if type(audit_budget) is not int or not 200<=audit_budget<=6000:
        raise ValueError("world candidate search budget outside bounded range")
    candidates=[];denials=[]
    observed=set(examined_digests)
    for seed in range(start_seed,start_seed+count):
        world,traveller=make_frontier(seed=seed,weather=weather,hour=hour)
        identity=scenario_digest(world)
        if identity in observed:
            denials.append(f"{seed}:duplicate_original_content_digest")
            continue
        observed.add(identity)
        audit=audit_world(world,traveller,max_search=audit_budget)
        if (audit.unreachable_places or audit.no_topological_goal_escape or
                audit.unrewarded_dead_ends or audit.initial_visible_secrets or
                not audit.fully_executable_original_goal_route):
            denials.append(f"{seed}:world_playability_not_proven")
            continue
        journey,_,limited=plan(
            world,traveller,objective="fastest",
            expansion_cap=audit_budget,
        )
        if journey is None or limited:
            denials.append(f"{seed}:bounded_optimal_route_unproven")
            continue
        families=tuple(sorted({MODES[x.mode] for x in world.connections}))
        candidates.append(WorldCandidate(
            seed,weather,hour,identity,_quantized_structure(world),
            len(world.places),len(world.connections),families,
            journey.elapsed_minutes,journey.length,
            len(audit.hidden_secrets_initially),audit.loops,
            audit.stress_warnings,
            "accepted_original_world_candidate_pending_all_release_reviews",
            False,False,
        ))
    return WorldBatch(
        SCHEMA,start_seed,start_seed+count,count,
        len(candidates),len(denials),tuple(candidates),tuple(denials),
        len({x.digest for x in candidates}),
        0,LEGAL_HOLDS,
        "Only original graph candidates sampled. No built, shipped, enjoyable "
        "or independently IP-cleared complete games are certified.",
    )

def batch_dict(batch:WorldBatch)->dict:
    return asdict(batch)

def verify_batch(data:dict)->WorldBatch:
    if not isinstance(data,dict) or data.get("schema")!=SCHEMA:
        raise ValueError("unknown original route candidate ledger")
    start=data.get("start_seed")
    count=data.get("attempted")
    weather="clear"
    hour=8
    entries=data.get("candidates")
    if not isinstance(entries,list):
        raise ValueError("original game candidate entries not a sequence")
    if entries:
        first=entries[0]
        weather=first.get("weather")
        hour=first.get("start_hour")
    # Verify immutable version-1 ledger deterministically from actual seed
    # range, not self-asserted candidate statistics. The external cumulative
    # duplicate exclusion set belongs to a separate future signed batch
    # history, so foreign exclusions cannot be silently invented here.
    expected=create_candidate_batch(start_seed=start,count=count,
                                    weather=weather,hour=hour,
                                    audit_budget=1200)
    if json.loads(json.dumps(batch_dict(expected)))!=data:
        raise ValueError("original world candidate ledger differs from canonical recomputation")
    return expected

def publish_candidate_batch(batch:WorldBatch,destination:Path,*,authorized:bool)->dict:
    if authorized is not True:
        raise PermissionError("cannot publish original route manifests without operator authorization")
    if not isinstance(batch,WorldBatch) or batch.schema!=SCHEMA:
        raise ValueError("invalid bounded original world candidate batch")
    folder=Path(destination).expanduser().absolute()
    if any(path.is_symlink() for path in (folder,*folder.parents)):
        raise ValueError("cannot publish candidate evidence through symlink destinations")
    if folder.exists() and not folder.is_dir():
        raise ValueError("candidate release destination must be a directory")
    output=json.dumps(batch_dict(batch),sort_keys=True,separators=(",",":"),
                      ensure_ascii=True).encode("utf-8")+b"\n"
    if len(output)>200000:
        raise ValueError("route candidate metadata exceeds safe publication budget")
    folder.mkdir(parents=True,exist_ok=True)
    digest=sha256(output).hexdigest()
    target=folder/("dragon-original-route-candidates-"+digest[:20]+".json")
    with target.open("xb") as file:
        file.write(output)
        file.flush()
        os.fsync(file.fileno())
    return {"schema":SCHEMA,"status":"original_candidate_manifest_not_finished_games",
            "filename":target.name,"sha256":digest,
            "attempted":batch.attempted,"admitted":batch.admitted,
            "finished_games":0}
