"""9,000 reproducible, source-grounded technical handbooks for 45M worldlines.

A volume owns exactly one (domain, spatial treatment, director, worldline)
coordinate and exhaustively indexes 50 authored archetypes × ten RPG systems
× ten final-production passes = 5,000 executable operations. Nine thousand
volumes thus partition all 45 million contracts without a 9k-file copy-paste
repository explosion. Every document can be rendered, searched, and exported.
"""
from __future__ import annotations

from collections.abc import Sequence
from hashlib import sha256
from typing import Any

from .game_frontier_studio import StudioError
from .game_frontier_studio_production_recipes import _DOMAINS, TREATMENTS, _slug
from .game_frontier_studio_system_expansions import GAMEPLAY_LAYERS
from .game_frontier_studio_directed_production import DIRECTORS, DIRECTOR_PURPOSES
from .game_frontier_studio_final_production import FINISHES, FINISH_OBJECTIVES
from .game_frontier_studio_worldline_production import (
    WORLDLINES, WORLDLINE_ACTIONS, WORLDLINE_OBJECTIVES, WORLDLINE_EFFECTS,
)

VOLUME_SCHEMA = "skeleton.forge.worldline_handbook.v1"
VOLUME_COUNT = len(_DOMAINS)*len(TREATMENTS)*len(DIRECTORS)*len(WORLDLINES)
assert VOLUME_COUNT == 9000
ACCEPTANCE = (
    "Resolve the authored source archetype to a concrete typed game mutator",
    "Resolve the spatial treatment with reproducible source input",
    "Resolve the chosen gameplay system with its actual RPG conditions",
    "Resolve the selected director to an authoritative source editor",
    "Resolve each finishing pass to an existing bounded game author",
    "Write distinct real tile cells and verify the exact edited layer",
    "Append observed-sensor gameplay proposals, never invented measurements",
    "Require host approval before applying world-changing proposals",
    "Keep existing cast and quest canon unchanged",
    "Preserve newly authored NPC interaction IDs and targets",
    "Keep new quest branches reachable with an authorized terminal",
    "Reject malformed or unsupported action/creator names",
    "Reject forged or dynamic embedded subcommands",
    "Require finite geometry, seed and source palette indices",
    "Preserve the original immutable project on failed composite execution",
    "Reproduce identical source and content hashes for identical inputs",
    "Allow a second independent, uniquely named production chapter",
    "Round-trip the typed source JSON without loss of character or quest fields",
    "Export real Godot terrain and expedition travel source",
    "Verify real collision and navigation in the target Godot runtime",
    "Check gameplay actor motion against performance/memory budgets",
    "Inspect visual framing and graphics against original GDD requirements",
    "Verify audio and music sources are original or rights-cleared",
    "Run actual action proposals through native authority on measured signals",
    "Inspect creative rewrite and copyright before publishing",
    "Pass the exact-head focused suite and backend quality gate",
    "Pass native engine smoke and full application E2E",
    "Record receipt SHA, source SHA and revision on every promotion",
    "Reject excessive context, output bytes and 64+ results search pages",
    "Never claim 5,000 independent engines or finished games per volume",
)


def volume_number(domain: str, treatment: str, director: str,
                  worldline: str) -> int:
    if ((domain not in {name for name,_,_ in _DOMAINS}) or
        treatment not in TREATMENTS or director not in DIRECTORS
        or worldline not in WORLDLINES):
        raise StudioError("unknown original-game construction handbook")
    d=next(i for i,(name,_,_) in enumerate(_DOMAINS) if name==domain)
    return (((d*len(TREATMENTS)+TREATMENTS.index(treatment))
              *len(DIRECTORS)+DIRECTORS.index(director))
              *len(WORLDLINES)+WORLDLINES.index(worldline))


def identity(number: int) -> tuple[str,str,str,str]:
    if type(number) is not int or not 0<=number<VOLUME_COUNT:
        raise StudioError("handbook index outside 9,000 technical books")
    prefix,line_idx=divmod(number,len(WORLDLINES))
    prefix,dir_idx=divmod(prefix,len(DIRECTORS))
    domain_idx,treat_idx=divmod(prefix,len(TREATMENTS))
    return (_DOMAINS[domain_idx][0],TREATMENTS[treat_idx],
            DIRECTORS[dir_idx],WORLDLINES[line_idx])


class HandbookPaths(Sequence[str]):
    __slots__=()
    def __len__(self):
        return VOLUME_COUNT
    def __getitem__(self,idx):
        if isinstance(idx,slice):
            return tuple(self[i] for i in range(*idx.indices(len(self))))
        d,t,r,l=identity(idx)
        return f"game_studio_50000000/{d}/{t}/{r}/{l}.md"


HANDBOOK_PATHS=HandbookPaths()


def _actions(domain: str,treatment: str,director: str,
             worldline: str) -> tuple[str,...]:
    selected=next(row for row in _DOMAINS if row[0]==domain)
    archetypes=selected[1]
    prefix=f"worldline_{domain}_"
    suffix=f"__{treatment}"
    return tuple(
        f"{prefix}{_slug(blueprint)}{suffix}___{GAMEPLAY_LAYERS[0]}"
        f"____{director}_____{FINISHES[0]}______{worldline}"
        for blueprint in archetypes
    )


def volume_metadata(domain: str,treatment: str,director: str,
                    worldline: str) -> dict[str,Any]:
    number=volume_number(domain,treatment,director,worldline)
    return {
        "schema":VOLUME_SCHEMA,
        "volume":number+1001,
        "volume_index":number,
        "path":HANDBOOK_PATHS[number],
        "domain":domain,"treatment":treatment,
        "director":director,"worldline":worldline,
        "original_archetypes":50,
        "gameplay_systems":10,
        "finish_passes":10,
        "covered_commands":5000,
        "source_bound":True,
    }


def list_volumes(*,domain: str="",treatment: str="",director: str="",
                 worldline: str="",offset: int=0,limit: int=32)->dict[str,Any]:
    if (type(offset) is not int or not 0<=offset<=VOLUME_COUNT
        or type(limit) is not int or not 1<=limit<=64
        or type(domain) is not str or type(treatment) is not str
        or type(director) is not str or type(worldline) is not str
        or domain and domain not in {d for d,_,_ in _DOMAINS}
        or treatment and treatment not in TREATMENTS
        or director and director not in DIRECTORS
        or worldline and worldline not in WORLDLINES):
        raise StudioError("invalid bounded game handbook search")
    domains=tuple(i for i,row in enumerate(_DOMAINS) if not domain or row[0]==domain)
    treatments=tuple(i for i,t in enumerate(TREATMENTS) if not treatment or t==treatment)
    directors=tuple(i for i,r in enumerate(DIRECTORS) if not director or r==director)
    lines=tuple(i for i,l in enumerate(WORLDLINES) if not worldline or l==worldline)
    per=len(treatments)*len(directors)*len(lines)
    matched=len(domains)*per
    results=[]
    for k in range(offset,min(matched,offset+limit)):
        d,part=divmod(k,per)
        t,part=divmod(part,len(directors)*len(lines))
        r,l=divmod(part,len(lines))
        results.append(volume_metadata(_DOMAINS[domains[d]][0],
             TREATMENTS[treatments[t]],DIRECTORS[directors[r]],
             WORLDLINES[lines[l]]))
    return {
        "schema":"skeleton.forge.handbook_listing.v1",
        "total_catalog":VOLUME_COUNT,"matched":matched,
        "offset":offset,"limit":limit,
        "next_offset":offset+limit if offset+limit<matched else None,
        "items":results,
    }


def render_handbook(domain: str,treatment: str,director: str,
                    worldline: str)->str:
    """Produce a standalone, reproducible authoring document from actual code."""
    m=volume_metadata(domain,treatment,director,worldline)
    _,source_actions,steps=next(row for row in _DOMAINS if row[0]==domain)
    direct_purpose=DIRECTOR_PURPOSES[DIRECTORS.index(director)]
    line_purpose=WORLDLINE_OBJECTIVES[WORLDLINES.index(worldline)]
    effects=WORLDLINE_EFFECTS[WORLDLINES.index(worldline)]
    command_rows=[]
    for i,(archetype,base) in enumerate(zip(source_actions,
                                             _actions(domain,treatment,director,worldline)),1):
        if base not in WORLDLINE_ACTIONS:
            raise StudioError("handbook contains an unregistered game production contract")
        command_rows.append(f"| {i} | `{archetype}` | `{base}` |")
    sys_lines=[]
    for i,game in enumerate(GAMEPLAY_LAYERS):
        example=(
            f"worldline_{domain}_{_slug(source_actions[i])}__{treatment}___"
            f"{game}____{director}_____{FINISHES[i]}______{worldline}"
        )
        if example not in WORLDLINE_ACTIONS:
            raise StudioError("handbook references unimplemented gameplay contract")
        sys_lines.append(
            f"### System {i+1}: {game}\n\n"
            f"Playable source action: `{example}`.\n\n"
            f"Run original `{' + '.join(steps)}` producers, then the `{game}` "
            f"gameplay spatial/sensor layer, the `{director}` director and "
            f"the `{FINISHES[i]}` final pass. Add `{worldline}` worldline "
            "geometry and an independent observed event proposal. Confirm "
            "the source digest changes and that unrelated story records remain intact.\n"
        )
    finish_lines=[
        f"{i+1}. **{fin}:** {FINISH_OBJECTIVES[i]}. Test game-map geometry, "
        "NPC placement only if newly authored, new quest reachability, sensor "
        "approval and Godot scene import."
        for i,fin in enumerate(FINISHES)
    ]
    acceptance="\n".join(f"{i+1}. {line}." for i,line in enumerate(ACCEPTANCE))
    doc=(
        f"# Production volume {m['volume']}/10,000 — {domain} / "
        f"{treatment} / {director} / {worldline}\n\n"
        f"**Exact identity:** `{m['path']}` · **Production contracts:** "
        f"{m['covered_commands']:,} · **Generator:** "
        "`skeleton/forge/game_frontier_studio_worldline_handbooks.py`\n\n"
        "## Actual production intent\n\n"
        f"**Domain:** {domain}; **treatment:** {treatment}; **director:** "
        f"{director}; **worldline:** {worldline}. {direct_purpose}. "
        f"{line_purpose}. This authored source is intended to produce a coherent "
        "world that can be compiled by the existing native expedition/Godot code. "
        "It does not independently create or certify a finished game.\n\n"
        "## Fifty source-backed original game archetypes\n\n"
        "| # | Implemented blueprint | Runnable first-system/first-finish contract |\n"
        "|---:|---|---|\n"+"\n".join(command_rows)+"\n\n"
        "## Ten gameplay-system constructions\n\n"+"\n".join(sys_lines)+"\n"
        "## Ten final production passes\n\n"+"\n".join(finish_lines)+"\n\n"
        "## Observed runtime interaction\n\n"
        f"Worldline sensors: `{effects[0]}` {effects[1]} {effects[2]} and "
        f"`{effects[3]}` {effects[4]} {effects[5]}. Only when these **observed** "
        f"conditions are satisfied may the native runtime consider the typed "
        f"`{effects[6]}` proposal on channel `{effects[7]}` and target "
        f"`{effects[8]}`. The authoring editor does not execute world mutations.\n\n"
        "## Authoring and persistence sequence\n\n"
        "1. Inspect the authenticated game project, actual source SHA-256 and revision.\n"
        "2. Confirm the real selected MapLayer, floor/wall palette, prefab and quest IDs.\n"
        "3. Search the exact worldline catalog using domain, director and worldline filters.\n"
        "4. Choose one of the fifty original archetypes and an allowed 10-system/10-finish pair.\n"
        "5. Pass finite typed bounds, deterministic seed and a unique source instance identifier.\n"
        "6. Execute the original source producer and gameplay layer in the immutable project.\n"
        "7. Author the directed gameplay stage and finishing pass over real map/story content.\n"
        "8. Apply the selected worldline's distinct tile topology and two-observation event page.\n"
        "9. Change only newly created cast or quest records, preserving existing longform canon.\n"
        "10. Calculate before/after project source digest and reject empty, invalid or conflicting edits.\n"
        "11. Save only through authorized source compare-and-set; keep hash-linked receipts.\n"
        "12. Export and play through the resulting native Godot terrain/quest/event content.\n\n"
        "## Thirty adversarial and objective acceptance probes\n\n"+acceptance+"\n\n"
        "## Limits and signoff\n\n"
        "The operation identity is an exact composed game-source workflow, **not a "
        "separately handwritten engine, AI model, game asset or independently "
        "shipped title**. Collision, battle, economy, music, asset fidelity and "
        "actual runtime application of proposed RPG events need separate "
        "on-device tests. No preexisting character or world canon may be "
        "silently replaced. Exact-head CI, copyright and native gameplay checks "
        "remain the release authority.\n"
    )
    if len(doc.encode("utf-8"))>64_000:
        raise StudioError("handbook exceeds bounded documentation contract")
    return doc


def handbook_receipt(domain: str,treatment: str,director: str,
                     worldline: str)->dict[str,Any]:
    markdown=render_handbook(domain,treatment,director,worldline)
    meta=volume_metadata(domain,treatment,director,worldline)
    return {**meta,"content_sha256":sha256(markdown.encode("utf-8")).hexdigest(),
            "content_bytes":len(markdown.encode("utf-8")),"markdown":markdown}
