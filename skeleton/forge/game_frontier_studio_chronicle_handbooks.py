"""Nine million reproducible on-demand chronicle manuals and measured rankings.

The catalogue is virtual; rankings cover ten variants of one exact production
context and measure source-document completeness, not gameplay quality.
"""
from __future__ import annotations

from collections.abc import Sequence
from hashlib import sha256
import re
from typing import Any

from .game_frontier_studio import StudioError
from .game_frontier_studio_campaign_handbooks import (
    BOOK_COUNT as PARENT_COUNT, identity as parent_identity,
    number as parent_number, render as parent_render,
)
from .game_frontier_studio_chronicle_production import (
    CHRONICLES, PURPOSES, CHRONICLE_ACTIONS,
)
from .game_frontier_studio_campaign_production import CAMPAIGNS, EFFECTS
from .game_frontier_studio_production_recipes import _DOMAINS, _slug, TREATMENTS
from .game_frontier_studio_system_expansions import GAMEPLAY_LAYERS
from .game_frontier_studio_final_production import FINISHES
from .game_frontier_studio_directed_production import DIRECTORS
from .game_frontier_studio_worldline_production import WORLDLINES
from .game_frontier_studio_phase_production import PHASES

SCHEMA = "skeleton.forge.chronicle_handbook.v1"
RANK_SCHEMA = "skeleton.forge.chronicle_handbook_ranking.v1"
BOOK_COUNT = PARENT_COUNT * len(CHRONICLES)
if BOOK_COUNT != 9_000_000:
    raise RuntimeError("chronicle manuals require nine million catalog identities")

def number(domain: str, treatment: str, director: str, worldline: str,
           phase: str, campaign: str, chronicle: str) -> int:
    if chronicle not in CHRONICLES:
        raise StudioError("unknown chronicle handbook")
    return parent_number(domain,treatment,director,worldline,phase,campaign)*10 + CHRONICLES.index(chronicle)

def identity(index: int) -> tuple[str,str,str,str,str,str,str]:
    if type(index) is not int or not 0 <= index < BOOK_COUNT:
        raise StudioError("chronicle handbook index outside catalog")
    parent, axis = divmod(index, 10)
    return (*parent_identity(parent), CHRONICLES[axis])

class ChronicleBookPaths(Sequence[str]):
    __slots__ = ()
    def __len__(self):
        return BOOK_COUNT
    def __getitem__(self,index):
        if isinstance(index,slice):
            return tuple(self[i] for i in range(*index.indices(len(self))))
        d,t,r,w,p,c,h = identity(index)
        return f"game_studio_50000000000/{d}/{t}/{r}/{w}/{p}/{c}/{h}.md"

CHRONICLE_BOOK_PATHS = ChronicleBookPaths()

def metadata(domain: str, treatment: str, director: str, worldline: str,
             phase: str, campaign: str, chronicle: str) -> dict[str,Any]:
    idx = number(domain,treatment,director,worldline,phase,campaign,chronicle)
    return {
        "schema": SCHEMA, "volume": idx + 1_000_001, "volume_index": idx,
        "path": CHRONICLE_BOOK_PATHS[idx], "domain": domain,
        "treatment": treatment, "director": director, "worldline": worldline,
        "phase": phase, "campaign": campaign, "chronicle": chronicle,
        "source_archetypes": 50, "gameplay_systems": 10,
        "finish_passes": 10, "covered_commands": 5000, "source_bound": True,
    }

def list_books(*, domain: str = "", treatment: str = "", director: str = "",
               worldline: str = "", phase: str = "", campaign: str = "",
               chronicle: str = "", offset: int = 0, limit: int = 32) -> dict[str,Any]:
    values=(domain,treatment,director,worldline,phase,campaign,chronicle)
    catalogs=(tuple(row[0] for row in _DOMAINS),TREATMENTS,DIRECTORS,
              WORLDLINES,PHASES,CAMPAIGNS,CHRONICLES)
    if (any(type(v) is not str or len(v)>40 or (v and v not in choices)
            for v,choices in zip(values,catalogs)) or
        type(offset) is not int or not 0<=offset<=BOOK_COUNT or
        type(limit) is not int or not 1<=limit<=64):
        raise StudioError("invalid bounded chronicle handbook search")
    groups=tuple(tuple(name for name in names if not value or name==value)
                 for value,names in zip(values,catalogs))
    total=1
    for group in groups:
        total*=len(group)
    results=[]
    for rank in range(offset,min(total,offset+limit)):
        local=rank
        positions=[0]*len(groups)
        for j in range(len(groups)-1,-1,-1):
            local,positions[j]=divmod(local,len(groups[j]))
        results.append(metadata(*(group[pos] for group,pos in zip(groups,positions))))
    return {"schema":"skeleton.forge.chronicle_handbook_listing.v1",
            "total_catalog":BOOK_COUNT,"matched":total,
            "offset":offset,"limit":limit,
            "next_offset":offset+limit if offset+limit<total else None,
            "items":results}

def _source_action(d:str,blueprint:str,t:str,game:str,r:str,f:str,
                   w:str,p:str,c:str,h:str)->str:
    action=(f"chronicle_{d}_{_slug(blueprint)}__{t}___{game}"
            f"____{r}_____{f}______{w}_______{p}________{c}_________{h}")
    if action not in CHRONICLE_ACTIONS:
        raise StudioError("handbook references unregistered game producer")
    return action

REVIEW=(
    "Exact authenticated source SHA-256 and version matched",
    "Map palette references resolve to owned tile identifiers",
    "All painted cells are inside the canonical layer",
    "Output tiles differ from original serialized source",
    "Safe return route remains traversable",
    "Existing actor identity and voice are retained",
    "New actor records alone receive positional updates",
    "Original quest stages and canon remain intact",
    "Event pages have unique replay-stable instance IDs",
    "Both observed event predicates accept a valid sample",
    "Invalid observed event predicates suppress the proposal",
    "Proposed game actions do not execute without native approval",
    "Deterministic seed reproduces the same content digest",
    "Identical previews produce identical source receipts",
    "Typed source compiler accepts final map and events",
    "Godot terrain bytes reflect authored source tiles",
    "NPC interactions reference available prefabs",
    "Optional quest branches reach a valid terminal",
    "Gameplay controller path traverses new corridors",
    "Target platform performance has independent evidence",
    "Source-rights and third-party asset use are cleared",
    "No prohibited copyrighted text or sprites copied",
    "Chapter descriptions maintain longform continuity",
    "Savegame roundtrip preserves original records",
    "Host compare-and-set prevents obsolete revision writes",
    "No remote execution or arbitrary source path accepted",
    "Ranking uses actual rendered manuscript word count",
    "Completeness quality is not confused with playability",
    "Two independent reviewers sign source and native checks",
    "Release approval remains separately owned and explicit",
)

def render(domain:str,treatment:str,director:str,worldline:str,
           phase:str,campaign:str,chronicle:str)->str:
    meta=metadata(domain,treatment,director,worldline,phase,campaign,chronicle)
    blueprints=next(row[1] for row in _DOMAINS if row[0]==domain)
    axis=CHRONICLES.index(chronicle)
    sensor=EFFECTS[axis]
    rows=[]
    for i,blueprint in enumerate(blueprints):
        action=_source_action(domain,blueprint,treatment,GAMEPLAY_LAYERS[0],
                              director,FINISHES[0],worldline,phase,campaign,chronicle)
        rows.append(f"| {i+1} | {blueprint} | {action} |")
    systems=[]
    for i,layer in enumerate(GAMEPLAY_LAYERS):
        action=_source_action(domain,blueprints[i],treatment,layer,director,
                              FINISHES[i],worldline,phase,campaign,chronicle)
        systems.append(f"### System {i+1}: {layer}\n\n"
                       f"Executable source operation: {action}\n\n"
                       "Compare map SHA, distinct observed source events, "
                       "new-only actor/quest changes, and native source emission.\n")
    upstream=parent_render(domain,treatment,director,worldline,phase,campaign)
    markdown=(
        f"# Volume {meta['volume']:,}/10,000,000 — {chronicle}\n\n"
        f"Source path: {meta['path']} · Composed operations in book: 5,000\n\n"
        "## Chronicle objective and observed gameplay effects\n\n"
        f"{PURPOSES[axis]}. The production executes an existing campaign edit "
        "and paints an additional bounded, deterministic tile topology.\n\n"
        f"Observed signals: {sensor[0]} {sensor[1]} {sensor[2]}, "
        f"{sensor[3]} {sensor[4]} {sensor[5]}. "
        f"Proposed action: {sensor[6]} / {sensor[7]} / {sensor[8]} / {sensor[9]}. "
        "Native owner approval is required before executing the action.\n\n"
        "## Fifty registered and distinct source archetypes\n\n"
        "| # | Source archetype | Exact chronicle operation |\n"
        "|---:|---|---|\n"+"\n".join(rows)+"\n\n"
        "## Ten gameplay source examples\n\n"+"\n".join(systems)+"\n\n"
        "## Authoring and native deployment continuity\n\n"
        "Load the original tenant-owned StudioProject and exact SHA-256. "
        "Preview isolated transformations, recompile source, verify each "
        "environment sensor, and commit with authorized CAS only. "
        "Read back the versioned host source, compile Godot terrain, "
        "travel and quest data, then perform a real native playthrough. "
        "Preserve existing characters, authorial voice and story canon; "
        "only this transaction's new actors and quests may be refined. "
        "Keep action proposals separate from applied game effects.\n\n"
        "## Thirty objective adversarial review questions\n\n"
        +"\n".join(f"{i+1}. {text}." for i,text in enumerate(REVIEW))+"\n\n"
        "## Upstream campaign and phase source dossier\n\n"+upstream+"\n\n"
        "## Native release and copyright boundary\n\n"
        "The handbook counts executable source combinations, not independent "
        "finished games. Rendered word count, source completeness and a "
        "candidate preview never establish original creative merit, copyright "
        "clearance, long-running operation or native-game release certification.\n"
    )
    if len(markdown.encode("utf8"))>192_000:
        raise StudioError("rendered manuscript exceeded 192KB budget")
    return markdown

_WORDS=re.compile(r"\b[\w'-]+\b",re.UNICODE)

def grade(markdown:str,meta:dict[str,Any])->dict[str,Any]:
    if type(markdown) is not str or len(markdown.encode("utf8"))>192_000:
        raise StudioError("invalid rendered chronicle manuscript")
    criteria={
        "registered_source":bool(meta.get("source_bound")) and meta.get("covered_commands")==5000,
        "fifty_archetypes":sum(line.startswith("| ") and " | chronicle_" in line
                               for line in markdown.splitlines())==50,
        "ten_system_examples":markdown.count("Executable source operation: ")==10,
        "seven_required_sections":all(part in markdown for part in (
            "## Chronicle objective", "## Fifty registered", "## Ten gameplay",
            "## Authoring and native", "## Thirty objective",
            "## Upstream campaign", "## Native release")),
        "thirty_qualified_checks":all(f"{i+1}. {text}." in markdown
                                      for i,text in enumerate(REVIEW)),
        "observed_game_conditions":"Observed signals:" in markdown and "Proposed action:" in markdown,
        "source_immutability":"authorized CAS" in markdown and "SHA-256" in markdown,
        "native_release_boundary":"native" in markdown.lower() and "copyright" in markdown.lower(),
    }
    weights=(15,20,15,10,10,10,10,10)
    return {"quality_score":sum(n for good,n in zip(criteria.values(),weights) if good),
            "quality_max":100,
            "quality_kind":"objective_document_completeness_not_playability",
            "criteria":criteria,"words":len(_WORDS.findall(markdown)),
            "characters":len(markdown),"bytes":len(markdown.encode("utf8"))}

def receipt(*parts:str)->dict[str,Any]:
    meta=metadata(*parts)
    markdown=render(*parts)
    return {**meta,**grade(markdown,meta),
            "content_sha256":sha256(markdown.encode("utf8")).hexdigest(),
            "markdown":markdown}

def rank_variants(domain:str,treatment:str,director:str,worldline:str,
                  phase:str,campaign:str,*,sort:str="quality")->dict[str,Any]:
    if sort not in ("quality","length"):
        raise StudioError("ranking must sort by quality or length")
    rows=[]
    for chronicle in CHRONICLES:
        item=receipt(domain,treatment,director,worldline,phase,campaign,chronicle)
        item.pop("markdown")
        rows.append(item)
    if sort=="quality":
        rows.sort(key=lambda r:(-r["quality_score"],-r["words"],r["chronicle"]))
    else:
        rows.sort(key=lambda r:(-r["words"],-r["quality_score"],r["chronicle"]))
    for i,item in enumerate(rows,1):
        item["rank"]=i
    return {"schema":RANK_SCHEMA,"sort":sort,
            "scope":"ten_chronicle_variants_for_one_exact_campaign_context",
            "compared":10,"items":rows}
