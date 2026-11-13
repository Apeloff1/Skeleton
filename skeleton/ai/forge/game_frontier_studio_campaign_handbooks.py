"""900,000 reproducible original-game campaign manuals with real quality/length ranking.

One previously indexed phase book × ten implemented campaign authors =
900,000 addressable books. Each covers 50 source archetypes × ten gameplay
systems × ten final passes = 5,000 source-changing commands. No million-file
startup allocation, and no quality claims about untested gameplay.

Quality is a transparent, deterministic document-completeness rubric; length
is measured from actual rendered Markdown. The only exact ranked comparison
is ten alternatives *within one selected production context*.
"""
from __future__ import annotations

from collections.abc import Sequence
from hashlib import sha256
import re
from typing import Any

from .game_frontier_studio import StudioError
from .game_frontier_studio_phase_handbooks import (
    BOOK_COUNT as PARENT_COUNT, identity as parent_identity,
    number as parent_number, render as parent_render,
    ORIGINAL_ACCEPTANCE,
)
from .game_frontier_studio_campaign_production import (
    CAMPAIGNS, CAMPAIGN_ACTIONS, OBJECTIVES, EFFECTS,
)
from .game_frontier_studio_production_recipes import _DOMAINS, TREATMENTS, _slug
from .game_frontier_studio_system_expansions import GAMEPLAY_LAYERS
from .game_frontier_studio_directed_production import DIRECTORS
from .game_frontier_studio_final_production import FINISHES
from .game_frontier_studio_worldline_production import WORLDLINES
from .game_frontier_studio_phase_production import PHASES

SCHEMA = "skeleton.forge.campaign_handbook.v1"
RANK_SCHEMA = "skeleton.forge.campaign_handbook_ranking.v1"
BOOK_COUNT = PARENT_COUNT*len(CAMPAIGNS)
if BOOK_COUNT != 900_000:
    raise RuntimeError("900,000 campaign production manuals required")


def number(domain:str,treatment:str,director:str,worldline:str,
           phase:str,campaign:str)->int:
    if campaign not in CAMPAIGNS:
        raise StudioError("unknown authored campaign handbook")
    return parent_number(domain,treatment,director,worldline,phase)*10+CAMPAIGNS.index(campaign)


def identity(index:int)->tuple[str,str,str,str,str,str]:
    if type(index) is not int or not 0<=index<BOOK_COUNT:
        raise StudioError("campaign handbook identity outside real source catalog")
    parent,axis=divmod(index,10)
    return (*parent_identity(parent),CAMPAIGNS[axis])


class CampaignBookPaths(Sequence[str]):
    __slots__=()
    def __len__(self):
        return BOOK_COUNT
    def __getitem__(self,index):
        if isinstance(index,slice):
            return tuple(self[i] for i in range(*index.indices(len(self))))
        d,t,r,w,p,c=identity(index)
        return f"game_studio_5000000000/{d}/{t}/{r}/{w}/{p}/{c}.md"


CAMPAIGN_BOOK_PATHS=CampaignBookPaths()


def metadata(domain:str,treatment:str,director:str,worldline:str,
             phase:str,campaign:str)->dict[str,Any]:
    i=number(domain,treatment,director,worldline,phase,campaign)
    return {"schema":SCHEMA,"volume":i+100_001,"volume_index":i,
            "path":CAMPAIGN_BOOK_PATHS[i],
            "domain":domain,"treatment":treatment,"director":director,
            "worldline":worldline,"phase":phase,"campaign":campaign,
            "source_archetypes":50,"gameplay_systems":10,
            "finish_passes":10,"covered_commands":5_000,
            "source_bound":True}


def list_books(*,domain:str="",treatment:str="",director:str="",
               worldline:str="",phase:str="",campaign:str="",
               offset:int=0,limit:int=32)->dict[str,Any]:
    vals=(domain,treatment,director,worldline,phase,campaign)
    catalogs=(tuple(row[0] for row in _DOMAINS),TREATMENTS,DIRECTORS,
              WORLDLINES,PHASES,CAMPAIGNS)
    if (any(type(v) is not str or len(v)>40 or (v and v not in opts)
            for v,opts in zip(vals,catalogs)) or
        type(offset) is not int or not 0<=offset<=BOOK_COUNT or
        type(limit) is not int or not 1<=limit<=64):
        raise StudioError("invalid bounded 900,000-book query")
    selected=tuple(tuple(x for x in opts if not value or value==x)
                   for value,opts in zip(vals,catalogs))
    counts=tuple(len(group) for group in selected)
    stride=1
    for count in counts:
        stride*=count
    results=[]
    for rank in range(offset,min(stride,offset+limit)):
        local=rank
        selection=[None]*len(selected)
        for idx in range(len(selected)-1,-1,-1):
            local,sub=divmod(local,counts[idx])
            selection[idx]=selected[idx][sub]
        results.append(metadata(*selection))
    return {"schema":"skeleton.forge.campaign_handbook_listing.v1",
            "total_catalog":BOOK_COUNT,"matched":stride,
            "offset":offset,"limit":limit,
            "next_offset":offset+limit if offset+limit<stride else None,
            "items":results}


def render(domain:str,treatment:str,director:str,worldline:str,
           phase:str,campaign:str)->str:
    """Produce one genuine source-grounded manuscript with exact operations."""
    meta=metadata(domain,treatment,director,worldline,phase,campaign)
    archetypes=next(row[1] for row in _DOMAINS if row[0]==domain)
    steps=next(row[2] for row in _DOMAINS if row[0]==domain)
    axis=CAMPAIGNS.index(campaign)
    effects=EFFECTS[axis]
    rows=[]
    for idx,blueprint in enumerate(archetypes):
        name=(f"campaign_{domain}_{_slug(blueprint)}__{treatment}___"
              f"{GAMEPLAY_LAYERS[0]}____{director}_____{FINISHES[0]}"
              f"______{worldline}_______{phase}________{campaign}")
        if name not in CAMPAIGN_ACTIONS:
            raise StudioError("campaign book has an unregistered game source producer")
        rows.append(f"| {idx+1} | `{blueprint}` | `{name}` |")
    systems=[]
    for i,game in enumerate(GAMEPLAY_LAYERS):
        name=(f"campaign_{domain}_{_slug(archetypes[i])}__{treatment}___"
              f"{game}____{director}_____{FINISHES[i]}______{worldline}"
              f"_______{phase}________{campaign}")
        if name not in CAMPAIGN_ACTIONS:
            raise StudioError("campaign book gameplay example not implemented")
        systems.append(
            f"### Gameplay system {i+1}: {game}\n\n"
            f"Exact executable source command: `{name}`.\n\n"
            f"Run source producer `{' + '.join(steps)}`, the `{game}` gameplay "
            f"overlay, the `{director}` director, the `{FINISHES[i]}` finisher, "
            f"then `{worldline}`, `{phase}` and `{campaign}`. "
            "Verify actual changed cells, distinct observed event predicates, "
            "stable actor ID references and reachable chapter outcomes.\n"
        )
    construction=(
        "1. Load authenticated project source revision and exact 64-character SHA-256.\n"
        "2. Read the actual ground layer, tile palette and compatible actor catalog.\n"
        "3. Select one of fifty real source archetypes and an explicit deterministic seed.\n"
        "4. Compose the original producer, treatment, gameplay, director and finisher.\n"
        "5. Execute the existing worldline and phase real source mutations.\n"
        "6. Apply this campaign's own tile topology and observed RPG event page.\n"
        "7. Adjust only newly generated NPCs or quests; never replace prior canon.\n"
        "8. Validate one independently reachable ending and event target identity.\n"
        "9. Preview immutable before/after SHA, then commit via authorized CAS.\n"
        "10. Export native Godot map, actor interactions and native quest graph.\n"
        "11. Test actual travel, environmental signal matching and scene transitions.\n"
        "12. Sign rights, quality, reproducibility and native-playability evidence.\n"
    )
    detail=(
        f"**Campaign:** {campaign}. **Objective:** {OBJECTIVES[axis]}. "
        "This production composes seven prior source-editing layers and adds "
        "a distinct deterministic map-mask and two-signal RPG action proposal. "
        "The editor cannot execute damage, commerce, travel, music or quest effects "
        "without approval from the native gameplay authority.\n\n"
        f"**Observed signals:** `{effects[0]}` {effects[1]} {effects[2]} and "
        f"`{effects[3]}` {effects[4]} {effects[5]}. "
        f"**Proposed action:** `{effects[6]}` on `{effects[7]}` toward "
        f"`{effects[8]}` with authored value `{effects[9]}`.\n\n"
    )
    parent=parent_render(domain,treatment,director,worldline,phase)
    output=(
        f"# Production volume {meta['volume']:,}/1,000,000 — "
        f"{domain} / {treatment} / {director} / {worldline} / {phase} / {campaign}\n\n"
        f"**Reproducible source path:** `{meta['path']}` · "
        f"**Registered combinations in this volume:** {meta['covered_commands']:,}\n\n"
        "## Gameplay objective and limits\n\n"+detail+
        "## Fifty implemented source archetypes and exact commands\n\n"
        "| # | Canonical authored blueprint | Executable campaign action |\n"
        "|---:|---|---|\n"+"\n".join(rows)+"\n\n"
        "## Ten gameplay systems with actual execution examples\n\n"
        +"\n".join(systems)+"\n\n"
        "## Native-world production and data continuity\n\n"+construction+"\n"
        "## Thirty objective and adversarial acceptance probes\n\n"
        +"\n".join(f"{i+1}. {check}." for i,check in enumerate(ORIGINAL_ACCEPTANCE))
        +"\n\n## Upstream source-grounded phase dossier\n\n"+parent+
        "\n## Release boundary\n\n"
        "This documentation describes registered executable *combinations*, not "
        "independently authored finished games. A long document does not prove "
        "long-duration runtime reliability or artistic originality. Before "
        "promotion, verify native gameplay, copyright, game quality and "
        "actual source-owned app builds. The source owner is the original "
        "immutable Forge Studio project.\n"
    )
    if len(output.encode("utf8"))>128_000:
        raise StudioError("campaign manuscript exceeds bounded document limit")
    return output


_WORDS=re.compile(r"\b[\w'-]+\b",re.UNICODE)


def grade(markdown:str,meta:dict[str,Any])->dict[str,Any]:
    """Deterministic *document-completeness* score, not actual game quality."""
    if type(markdown) is not str or len(markdown)>128_000:
        raise StudioError("invalid bounded document for comparative grading")
    headings=tuple(x.strip().lower() for x in markdown.splitlines() if x.startswith("## "))
    required=("gameplay objective", "fifty implemented", "ten gameplay systems",
              "native-world production", "thirty objective",
              "upstream source-grounded", "release boundary")
    source_rows=sum(1 for line in markdown.splitlines()
                    if line.startswith("| ") and "| `campaign_" in line)
    system_examples=sum(1 for line in markdown.splitlines()
                        if line.startswith("Exact executable source command:"))
    checks=tuple(re.findall(r"(?m)^\d+\. .+$",markdown))
    criteria={
        "registered_source": bool(meta.get("source_bound")) and
              meta.get("covered_commands")==5_000,
        "fifty_archetypes":source_rows==50,
        "ten_system_examples":system_examples==10,
        "seven_required_sections":all(any(part in x for x in headings)
                                       for part in required),
        "thirty_qualified_checks":len(checks)>=30,
        "observed_game_conditions":"**Observed signals:**" in markdown
                                   and "**Proposed action:**" in markdown,
        "source_immutability":"authorized CAS" in markdown and
                              "SHA-256" in markdown,
        "native_release_boundary":"native gameplay" in markdown.lower() and
                                  "copyright" in markdown.lower(),
    }
    points=(15,20,15,10,10,10,10,10)
    score=sum(value for ok,value in zip(criteria.values(),points) if ok)
    words=len(_WORDS.findall(markdown))
    return {"quality_score":score,"quality_max":100,
            "quality_kind":"objective_document_completeness_not_playability",
            "criteria":criteria,"words":words,
            "characters":len(markdown),"bytes":len(markdown.encode("utf8"))}


def receipt(domain:str,treatment:str,director:str,worldline:str,
            phase:str,campaign:str)->dict[str,Any]:
    meta=metadata(domain,treatment,director,worldline,phase,campaign)
    body=render(domain,treatment,director,worldline,phase,campaign)
    return {**meta,**grade(body,meta),
            "content_sha256":sha256(body.encode("utf8")).hexdigest(),
            "markdown":body}


def rank_variants(domain:str,treatment:str,director:str,worldline:str,
                  phase:str,*,sort:str="quality")->dict[str,Any]:
    """Exact rank of TEN alternatives for one context; never global top 900K."""
    if sort not in ("quality","length"):
        raise StudioError("ranking mode must be quality or length")
    options=[]
    for choice in CAMPAIGNS:
        entry=receipt(domain,treatment,director,worldline,phase,choice)
        entry.pop("markdown")
        options.append(entry)
    if sort=="quality":
        options.sort(key=lambda r:(-r["quality_score"],-r["words"],r["campaign"]))
    else:
        options.sort(key=lambda r:(-r["words"],-r["quality_score"],r["campaign"]))
    for i,row in enumerate(options,1):
        row["rank"]=i
    return {"schema":RANK_SCHEMA,"sort":sort,
            "scope":"ten_campaign_variants_for_one_exact_production_context",
            "compared":len(options),"items":options}
