"""Complete multi-level game campaigns: capabilities 091–100.

Works with real generated blueprints and the existing offline game compiler.
Produces independent playable levels and a navigable local campaign launcher.
"""
from __future__ import annotations
from dataclasses import dataclass,replace
from collections import deque
from hashlib import sha256
from html import escape
from io import BytesIO
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED
import json

from .game_knowledge_design import (
    GameBlueprint,propose_game_blueprint,populate_game_level,
)
from .game_playable_builder import build_playable_web_game
from .game_knowledge_index import GameKnowledgeIndex

@dataclass(frozen=True)
class Chapter:
    chapter_id:str
    blueprint:GameBlueprint
    prerequisites:tuple[str,...] = ()
    experience_reward:int = 100

@dataclass(frozen=True)
class Campaign:
    title:str
    chapters:tuple[Chapter,...]
    campaign_id:str

@dataclass(frozen=True)
class HeroProgress:
    experience:int = 0
    level:int = 1
    skill_points:int = 0
    skills:tuple[tuple[str,int],...] = ()
    cleared:frozenset[str] = frozenset()

# 091 Construct a concrete campaign with real original playable levels.
def compose_game_campaign(title:str,chapters:tuple[Chapter,...])->Campaign:
    if not isinstance(title,str) or not 1<=len(title)<=100 or not 1<=len(chapters)<=100:
        raise ValueError("invalid campaign")
    if len({c.chapter_id for c in chapters})!=len(chapters):
        raise ValueError("duplicate chapter IDs")
    roots={c.chapter_id for c in chapters}
    if any(not set(c.prerequisites)<=roots or c.chapter_id in c.prerequisites
           for c in chapters):
        raise ValueError("invalid campaign prerequisites")
    validate_campaign_graph(chapters)
    digest=sha256(json.dumps([
        title,[(c.chapter_id,c.blueprint.fingerprint,c.prerequisites)
               for c in chapters],
    ],sort_keys=True).encode()).hexdigest()
    return Campaign(title,chapters,digest)

# 092 Reject circular unlocks and construct canonical topological order.
def validate_campaign_graph(chapters:tuple[Chapter,...])->tuple[str,...]:
    lookup={c.chapter_id:c for c in chapters}
    if len(lookup)!=len(chapters):raise ValueError("duplicate chapter IDs")
    state={};order=[]
    def visit(key):
        if key not in lookup:raise ValueError("missing chapter")
        if state.get(key)==1:raise ValueError("cyclic campaign")
        if state.get(key)==2:return
        state[key]=1
        for dep in sorted(lookup[key].prerequisites):visit(dep)
        state[key]=2;order.append(key)
    for key in sorted(lookup):visit(key)
    return tuple(order)

# 093 Choose all unlocked next levels given real player completion state.
def available_campaign_chapters(campaign:Campaign,progress:HeroProgress
                                )->tuple[Chapter,...]:
    return tuple(ch for ch in campaign.chapters if
                 ch.chapter_id not in progress.cleared
                 and set(ch.prerequisites)<=progress.cleared)

# 094 Compute shortest viable chapter completion order to a chosen finale.
def plan_campaign_path(campaign:Campaign,finale:str)->tuple[str,...]:
    lookup={c.chapter_id:c for c in campaign.chapters}
    if finale not in lookup:raise ValueError("unknown finale chapter")
    included=set()
    def visit(key):
        if key in included:return
        for dep in lookup[key].prerequisites:visit(dep)
        included.add(key)
    visit(finale)
    return tuple(key for key in validate_campaign_graph(campaign.chapters)
                 if key in included)

# 095 Award experience and skill points using bounded progression curves.
def award_campaign_experience(hero:HeroProgress,amount:int)->HeroProgress:
    if not 0<=amount<=10_000_000:raise ValueError("invalid experience reward")
    exp=hero.experience+amount
    level=hero.level;points=hero.skill_points
    while level<100 and exp>=100*level*level:
        level+=1;points+=1
    return replace(hero,experience=exp,level=level,skill_points=points)

# 096 Spend earned points on real bounded skill upgrades.
def upgrade_hero_skill(hero:HeroProgress,skill:str, *,
                       cost:int=1,max_rank:int=5)->HeroProgress:
    allowed={"health","movement","combat","energy","recovery","loot"}
    if skill not in allowed or not 1<=cost<=10 or not 1<=max_rank<=20:
        raise ValueError("invalid skill upgrade")
    skills=dict(hero.skills)
    if hero.skill_points<cost or skills.get(skill,0)>=max_rank:
        raise ValueError("skill unavailable")
    skills[skill]=skills.get(skill,0)+1
    return replace(hero,skill_points=hero.skill_points-cost,
                   skills=tuple(sorted(skills.items())))

# 097 Complete a chapter, grant real XP and unlock dependent missions.
def complete_campaign_chapter(campaign:Campaign,hero:HeroProgress,
                              chapter_id:str)->HeroProgress:
    available={x.chapter_id:x for x in available_campaign_chapters(campaign,hero)}
    if chapter_id not in available:raise ValueError("chapter locked or completed")
    rewarded=award_campaign_experience(hero,available[chapter_id].experience_reward)
    return replace(rewarded,cleared=hero.cleared|{chapter_id})

# 098 Generate a fully connected campaign of varying levels from research.
def generate_game_campaign(index:GameKnowledgeIndex,*,title:str,
                           genre:str,engine:str="web",seed:int=1,
                           chapters:int=8)->Campaign:
    if not 1<=chapters<=50:raise ValueError("invalid campaign length")
    result=[]
    for i in range(chapters):
        bp=propose_game_blueprint(index,title=f"{title} — Chapter {i+1}",
            genre=genre,engine=engine,seed=seed+i*13,
            width=min(96,28+i*2),height=14)
        bp=populate_game_level(bp,pickups=5+i//2,
                               enemies=min(16,1+i//2))
        depends=(result[-1].chapter_id,) if result else ()
        result.append(Chapter(f"chapter-{i+1:02d}",bp,depends,100+i*40))
    return compose_game_campaign(title,tuple(result))

# 099 Serialize and restore tamper-detectable player campaign progress.
def encode_campaign_save(campaign:Campaign,hero:HeroProgress)->bytes:
    if not hero.cleared<={c.chapter_id for c in campaign.chapters}:
        raise ValueError("save references unknown chapters")
    payload={
        "schema":"skeleton.game_campaign.save.v1",
        "campaign":campaign.campaign_id,
        "xp":hero.experience,"level":hero.level,
        "skill_points":hero.skill_points,"skills":hero.skills,
        "cleared":sorted(hero.cleared),
    }
    raw=json.dumps(payload,sort_keys=True,separators=(",",":")).encode()
    envelope={"payload":payload,"sha256":sha256(raw).hexdigest()}
    return json.dumps(envelope,sort_keys=True,separators=(",",":")).encode()

def decode_campaign_save(campaign:Campaign,payload:bytes)->HeroProgress:
    if len(payload)>1000000:raise ValueError("save too large")
    envelope=json.loads(payload)
    info=envelope["payload"]
    canonical=json.dumps(info,sort_keys=True,separators=(",",":")).encode()
    if sha256(canonical).hexdigest()!=envelope.get("sha256") or (
        info.get("campaign")!=campaign.campaign_id
    ):
        raise ValueError("save does not belong to this campaign")
    return HeroProgress(info["xp"],info["level"],info["skill_points"],
                        tuple(tuple(x) for x in info["skills"]),
                        frozenset(info["cleared"]))

# 100 Export a complete offline multi-level playable campaign ZIP.
def export_campaign_archive(campaign:Campaign)->bytes:
    if not 1<=len(campaign.chapters)<=100:
        raise ValueError("invalid campaign archive")
    index=[
        '<!doctype html><html lang="en"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width,initial-scale=1">',
        '<title>'+escape(campaign.title)+'</title>',
        '<style>body{margin:3rem auto;max-width:740px;background:#101827;',
        'color:#e8f5ff;font:18px system-ui;padding:1rem}',
        'a{display:block;padding:1rem;margin:.5rem 0;background:#273e55;',
        'color:white;border-radius:10px;text-decoration:none}</style></head>',
        '<body><h1>'+escape(campaign.title)+'</h1>',
        '<p>Original offline campaign. Complete levels in order.</p>',
    ]
    files=[]
    for i,chapter in enumerate(campaign.chapters,1):
        if chapter.blueprint.engine not in ("web","phaser"):
            raise ValueError("campaign launcher currently supports web targets")
        name=f"levels/level-{i:03d}.html"
        original=build_playable_web_game(chapter.blueprint).html
        # Persist locally, never transmit a player completion event.
        # The exact compiled game signals success; opening a level alone
        # cannot mark it complete.
        completion=(
            '\\nfunction campaignWin(){\\n'
            '  try{const key="skeleton-campaign-'+campaign.campaign_id+'";'
            '  const before=Number(localStorage.getItem(key)||"1");'
            f'  localStorage.setItem(key,String(Math.max(before,{i+1})));'
            '}catch(_){}\\n'
            '}\\n'
        )
        original=original.replace(
            "state.won=true;state.score+=250",
            "state.won=true;state.score+=250;campaignWin()",
        )
        original=original.replace("</script>",completion+"</script>",1)
        original=original.replace(
            "<script>",
            '<p><a href="../index.html" style="color:#86d4ff">'
            'Back to Campaign</a></p><script>',1,
        )
        index.append(f'<li><a data-chapter="{i}" href="{name}">Chapter {i}: '
                     +escape(chapter.blueprint.title)+'</a></li>')
        files.append((name,original.encode()))
    index.append("""<script>
try{
  const key="skeleton-campaign-__CAMPAIGN__";
  const unlocked=Number(localStorage.getItem(key)||"1");
  for(const chapter of document.querySelectorAll("[data-chapter]")){
    const locked=Number(chapter.dataset.chapter)>unlocked;
    if(locked){chapter.setAttribute("aria-disabled","true");
      chapter.textContent="🔒 "+chapter.textContent+" (locked)";
      chapter.addEventListener("click",event=>event.preventDefault());
      chapter.style.opacity=".5";
    }
  }
}catch(error){/* File/localStorage denial: remain independently playable. */}
</script>""".replace("__CAMPAIGN__",campaign.campaign_id))
    index.append('</body></html>')
    files.insert(0,("index.html","".join(index).encode()))
    files.append(("campaign.json",json.dumps({
        "schema":"skeleton.original_campaign.v1",
        "title":campaign.title,"campaign":campaign.campaign_id,
        "chapters":[{"id":c.chapter_id,"prerequisites":c.prerequisites,
                     "blueprint":c.blueprint.fingerprint,
                     "experience":c.experience_reward}
                    for c in campaign.chapters],
    },sort_keys=True,indent=2).encode()))
    sink=BytesIO()
    with ZipFile(sink,"w",compression=ZIP_DEFLATED,compresslevel=9) as output:
        for name,payload in files:
            info=ZipInfo(name,date_time=(2026,1,1,0,0,0))
            info.compress_type=ZIP_DEFLATED
            info.external_attr=0o644<<16
            output.writestr(info,payload)
    return sink.getvalue()
