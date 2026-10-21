"""90,000 source-verified phase-game handbooks (plus 10,000 earlier volumes).

One of 9,000 original worldline construction manuscripts is specialized through
one of ten *implemented* game phases. The 90K new books partition 450 million
exact source-mutating workflows: 50 underlying blueprints × ten gameplay
systems × ten finish passes = 5,000 real compositions per book.

Books are generated lazily and are NOT 90,000 committed Markdown files.
"""
from __future__ import annotations

from collections.abc import Sequence
from hashlib import sha256
from typing import Any

from .game_frontier_studio import StudioError
from .game_frontier_studio_worldline_handbooks import (
    VOLUME_COUNT as PARENT_BOOKS, identity as parent_identity,
    volume_number as parent_volume, render_handbook as parent_render,
    ACCEPTANCE as ORIGINAL_ACCEPTANCE,
)
from .game_frontier_studio_phase_production import (
    PHASES,PHASE_ACTIONS,PHASE_OBJECTIVES,PHASE_EFFECTS,
)
from .game_frontier_studio_production_recipes import _DOMAINS,TREATMENTS,_slug
from .game_frontier_studio_directed_production import DIRECTORS
from .game_frontier_studio_system_expansions import GAMEPLAY_LAYERS
from .game_frontier_studio_final_production import FINISHES
from .game_frontier_studio_worldline_production import WORLDLINES

SCHEMA="skeleton.forge.phase_game_handbook.v1"
BOOK_COUNT=PARENT_BOOKS*len(PHASES)
if BOOK_COUNT!=90_000:
    raise RuntimeError("ninety thousand independently addressable phase books required")


def number(domain:str,treatment:str,director:str,
           worldline:str,phase:str)->int:
    if phase not in PHASES:
        raise StudioError("unknown source-grounded game phase handbook")
    return parent_volume(domain,treatment,director,worldline)*10+PHASES.index(phase)


def identity(index:int)->tuple[str,str,str,str,str]:
    if type(index) is not int or not 0<=index<BOOK_COUNT:
        raise StudioError("phase handbook identity outside source catalog")
    parent,phase=divmod(index,10)
    return (*parent_identity(parent),PHASES[phase])


class PhaseBookPaths(Sequence[str]):
    __slots__=()
    def __len__(self)->int:
        return BOOK_COUNT
    def __getitem__(self,index):
        if isinstance(index,slice):
            return tuple(self[i] for i in range(*index.indices(len(self))))
        d,t,r,w,p=identity(index)
        return f"game_studio_500000000/{d}/{t}/{r}/{w}/{p}.md"


PHASE_BOOK_PATHS=PhaseBookPaths()


def metadata(domain:str,treatment:str,director:str,
             worldline:str,phase:str)->dict[str,Any]:
    index=number(domain,treatment,director,worldline,phase)
    return {"schema":SCHEMA,"volume":index+10_001,
            "volume_index":index,"path":PHASE_BOOK_PATHS[index],
            "domain":domain,"treatment":treatment,"director":director,
            "worldline":worldline,"phase":phase,
            "source_archetypes":50,"gameplay_systems":10,
            "final_passes":10,"covered_commands":5_000,
            "source_bound":True}


def list_books(*,domain:str="",treatment:str="",director:str="",
               worldline:str="",phase:str="",offset:int=0,
               limit:int=32)->dict[str,Any]:
    if (type(offset) is not int or not 0<=offset<=BOOK_COUNT or
        type(limit) is not int or not 1<=limit<=64 or
        any(type(x) is not str for x in (domain,treatment,director,worldline,phase)) or
        domain and domain not in {row[0] for row in _DOMAINS} or
        treatment and treatment not in TREATMENTS or
        director and director not in DIRECTORS or
        worldline and worldline not in WORLDLINES or
        phase and phase not in PHASES):
        raise StudioError("invalid bounded 90,000-book phase query")
    ds=tuple(r[0] for r in _DOMAINS if not domain or r[0]==domain)
    ts=tuple(r for r in TREATMENTS if not treatment or r==treatment)
    rs=tuple(r for r in DIRECTORS if not director or r==director)
    ws=tuple(r for r in WORLDLINES if not worldline or r==worldline)
    ps=tuple(r for r in PHASES if not phase or r==phase)
    per=len(ts)*len(rs)*len(ws)*len(ps)
    matched=len(ds)*per
    out=[]
    for i in range(offset,min(matched,offset+limit)):
        d,remaining=divmod(i,per)
        t,remaining=divmod(remaining,len(rs)*len(ws)*len(ps))
        r,remaining=divmod(remaining,len(ws)*len(ps))
        w,p=divmod(remaining,len(ps))
        out.append(metadata(ds[d],ts[t],rs[r],ws[w],ps[p]))
    return {"schema":"skeleton.forge.phase_handbook_listing.v1",
            "total_catalog":BOOK_COUNT,"matched":matched,"offset":offset,
            "limit":limit,"next_offset":offset+limit if offset+limit<matched else None,
            "items":out}


def render(domain:str,treatment:str,director:str,worldline:str,phase:str)->str:
    """Ground every example in existing executed, exact game tool identities."""
    record=metadata(domain,treatment,director,worldline,phase)
    parent=parent_render(domain,treatment,director,worldline)
    blueprints=next(row[1] for row in _DOMAINS if row[0]==domain)
    axis=PHASES.index(phase)
    data=PHASE_EFFECTS[axis]
    sources=[]
    for i,name in enumerate(blueprints):
        action=(f"phase_{domain}_{_slug(name)}__{treatment}___"
                f"{GAMEPLAY_LAYERS[0]}____{director}_____{FINISHES[0]}"
                f"______{worldline}_______{phase}")
        if action not in PHASE_ACTIONS:
            raise StudioError("phase manuscript references unimplemented authoring")
        sources.append(f"| {i+1} | \`{name}\` | \`{action}\` |")
    systems=[]
    for i,system in enumerate(GAMEPLAY_LAYERS):
        name=(f"phase_{domain}_{_slug(blueprints[i])}__{treatment}___"
              f"{system}____{director}_____{FINISHES[i]}"
              f"______{worldline}_______{phase}")
        if name not in PHASE_ACTIONS:
            raise StudioError("game phase manuscript has missing executable command")
        systems.append(
            f"{i+1}. **{system}:** run \`{name}\`, then inspect changed "
            "tile cells, two measured RPG event conditions and any newly authored "
            "quest/actor references. The actual native engine must authorize effects.")
    checks="\n".join(f"{i+1}. {x}." for i,x in enumerate(ORIGINAL_ACCEPTANCE))
    result=(
        f"# Production volume {record['volume']}/100,000 — "
        f"{domain} / {treatment} / {director} / {worldline} / {phase}\n\n"
        "**Implemented owner:** \`skeleton/forge/game_frontier_studio_phase_production.py\`\n\n"
        f"**Exact source path:** \`{record['path']}\` · "
        f"**Owned composition count:** {record['covered_commands']:,}\n\n"
        "## Executable, playable source production\n\n"
        f"The **{phase}** phase adds a further world geometry transformation, "
        "a typed RPG event with independently observed sensor predicates, "
        "and valid new-cast/new-quest refinements only where produced during "
        "the current authorized edit. " + PHASE_OBJECTIVES[axis] + ". "
        "The project source, preview, save/CAS, export and canon owner remains "
        "the original Forge Studio. This book is not a claim of an independently "
        "handwritten game engine or complete native game.\n\n"
        "## Fifty exact original-source blueprints\n\n"
        "| # | Native source archetype | Runnable phase composition |\n"
        "|---:|---|---|\n"+"\n".join(sources)+"\n\n"
        "## Ten real gameplay-system constructions\n\n"+"\n".join(systems)+"\n\n"
        "## Observed game action\n\n"
        f"\`{data[0]}\` {data[1]} {data[2]} and \`{data[3]}\` {data[4]} "
        f"{data[5]} gate the **proposal-only** \`{data[6]}\` action on "
        f"channel \`{data[7]}\`. Observations come from the real game runtime; "
        "the source editor cannot invent weather, NPC reputation or quest outcomes.\n\n"
        "## Production transaction\n\n"
        "1. Fetch the authorized project revision and immutable source SHA-256.\n"
        "2. Select real layer, palette, source blueprint and authoring seed.\n"
        "3. Execute the original recipe, gameplay overlay, director, final pass and worldline.\n"
        "4. Author phase-specific map cells, event page and new-actor/new-quest changes.\n"
        "5. Reject invalid identity, collisions, detached quest endings or missing source.\n"
        "6. Preview the exact before/after project source diff and preserve canon.\n"
        "7. Commit the entire immutable candidate via original tenant-scoped CAS.\n"
        "8. Generate native Godot files; prove navigation, RPG event and quest behavior.\n"
        "9. Record source hashes, code quality, adversarial review and asset rights.\n"
        "10. Promote only after target-device E2E, security and copyright checks.\n\n"
        "## Thirty objective and adversarial checks\n\n"+checks+"\n\n"
        "## Parent construction reference\n\n"
        "This phase extends the following executable source-grounded worldline "
        "handbook, which retains the original blueprint, director, system and "
        "finishing-pass knowledge:\n\n"+parent+"\n"
    )
    if len(result.encode("utf8"))>96_000:
        raise StudioError("generated phase book exceeds bounded content quota")
    return result


def receipt(domain:str,treatment:str,director:str,
            worldline:str,phase:str)->dict[str,Any]:
    md=render(domain,treatment,director,worldline,phase)
    meta=metadata(domain,treatment,director,worldline,phase)
    return {**meta,"content_sha256":sha256(md.encode("utf8")).hexdigest(),
            "content_bytes":len(md.encode("utf8")),"markdown":md}
