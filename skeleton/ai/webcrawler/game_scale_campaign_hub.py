"""Offline playable multi-level launcher with persistent advancement.

Every level is an original full playable Canvas game. The launcher validates
completion messages against the active iframe and its campaign/chapter ID,
tracks XP, awards levels and allows concrete skill investment. No network,
CDN, external scripts or imported game assets are needed.
"""
from __future__ import annotations

from hashlib import sha256
from html import escape
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo
import json

from .game_scale_campaign import Campaign,validate_campaign_graph
from .game_playable_builder import build_playable_web_game


def _safe_json(value: object) -> str:
    return (json.dumps(value,ensure_ascii=True,separators=(",",":"))
            .replace("<","\\u003c").replace(">","\\u003e")
            .replace("&","\\u0026"))


def _level_with_completion(original: str, campaign_id: str,
                           chapter_id: str) -> str:
    event=_safe_json({
        "type":"skeleton.game.campaign.completed.v1",
        "campaign":campaign_id,"chapter":chapter_id,
    })
    mark="state.won=true;state.score+=250;"
    if original.count(mark)!=1:
        raise ValueError("playable runtime does not expose unique goal event")
    # This message fires only inside the actual player's collision with the
    # goal, after puzzle prerequisites pass. The hub checks iframe identity.
    return original.replace(
        mark,mark+"window.parent.postMessage("+event+",'*');",1
    )


def render_campaign_hub(campaign: Campaign) -> str:
    if not isinstance(campaign,Campaign) or not campaign.chapters:
        raise ValueError("valid campaign required")
    order=validate_campaign_graph(campaign.chapters)
    entries=[]
    for idx,chapter in enumerate(campaign.chapters):
        entries.append({
            "id":chapter.chapter_id,
            "title":chapter.blueprint.title,
            "requires":list(chapter.prerequisites),
            "reward":chapter.experience_reward,
            "file":f"levels/level-{idx+1:03d}.html",
            "mechanics":list(chapter.blueprint.mechanics),
        })
    manifest=_safe_json({
        "schema":"skeleton.original_campaign.launcher.v1",
        "campaign":campaign.campaign_id,
        "title":campaign.title,
        "chapters":entries,
        "order":order,
    })
    html='''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Original Game Campaign</title>
<style>
:root{color-scheme:dark;font:16px system-ui}
*{box-sizing:border-box}body{margin:0;background:#0c1624;color:#e8f3ff}
header{padding:18px 24px;background:#1c2a3e;border-bottom:1px solid #405875}
header h1{margin:0 0 7px;font-size:24px}
#progress{font-size:14px;color:#b5d4ed}main{display:grid;grid-template-columns:300px 1fr;gap:14px;
padding:14px}
aside,section{border-radius:12px;background:#1b2c43;padding:16px}
h2{margin:0 0 12px;font-size:17px}
#chapters{display:grid;gap:8px}
button{border:1px solid #6485aa;background:#33516f;color:white;border-radius:9px;
padding:10px 12px;text-align:left;cursor:pointer;font:inherit}
button[disabled]{opacity:.55;cursor:not-allowed}
button:focus-visible{outline:3px solid #f6d38a}
#chapters button{width:100%}
#skills{display:grid;grid-template-columns:1fr 1fr;gap:7px}
#game{width:100%;height:580px;border:1px solid #536e91;border-radius:8px;
background:#08111d}
#status{min-height:22px;color:#a3e5ba}
.controls{display:flex;flex-wrap:wrap;gap:8px;margin:12px 0}
small{color:#c1d2df}
@media(max-width:850px){main{grid-template-columns:1fr}#game{height:500px}}
</style></head><body>
<header><h1 id="title"></h1>
<div id="progress"></div></header>
<main><aside><h2>Campaign Map</h2><div id="chapters"></div>
<h2 style="margin-top:20px">Character Upgrades</h2><div id="skills"></div>
<div class="controls"><button id="reset">Restart campaign</button>
<button id="save">Export progress</button>
<button id="load">Import progress</button></div>
<input type="file" id="importfile" accept="application/json,.json" hidden>
<p><small>Progress saves locally when your browser permits storage.
The exported JSON is a portable backup. This is an offline original game.</small></p></aside>
<section><h2 id="current">Select an unlocked chapter</h2>
<iframe id="game" title="Playable chapter" sandbox="allow-scripts"></iframe>
<p role="status" id="status" aria-live="polite">Choose the first chapter to play.</p>
</section></main>
<script>
"use strict";
const C=__CAMPAIGN__;
const byId=new Map(C.chapters.map(ch=>[ch.id,ch]));
const campaignStorage="skeleton.original.campaign:"+C.campaign;
const skills=["health","movement","combat","energy","recovery","loot"];
const frame=document.getElementById("game");
let active=null;
function blank(){return {schema:"skeleton.game.campaign.progress.v1",
 campaign:C.campaign,done:[],xp:0,level:1,points:0,skills:{}}}
let progress=blank();
function validProgress(data){
 if(!data||data.schema!=="skeleton.game.campaign.progress.v1"||data.campaign!==C.campaign)
   return false;
 if(!Array.isArray(data.done)||data.done.length>C.chapters.length ||
    !data.done.every(id=>byId.has(id))||new Set(data.done).size!==data.done.length)return false;
 if(!Number.isSafeInteger(data.xp)||data.xp<0||data.xp>100000000 ||
    !Number.isSafeInteger(data.level)||data.level<1||data.level>100 ||
    !Number.isSafeInteger(data.points)||data.points<0||data.points>100)return false;
 if(!data.skills||typeof data.skills!=="object"||Array.isArray(data.skills))return false;
 return Object.keys(data.skills).every(key=>skills.includes(key) &&
   Number.isSafeInteger(data.skills[key]) && data.skills[key]>=0 && data.skills[key]<=5);
}
function read(){
 try{
   const stored=localStorage.getItem(campaignStorage);
   if(stored){const candidate=JSON.parse(stored);if(validProgress(candidate))progress=candidate}
 }catch(_){}
}
function persist(){
 try{localStorage.setItem(campaignStorage,JSON.stringify(progress))}catch(_){}
}
const finished=()=>new Set(progress.done);
const unlocked=ch=>ch.requires.every(id=>finished().has(id));
function message(text){document.getElementById("status").textContent=text}
function render(){
 document.getElementById("title").textContent=C.title;
 document.getElementById("progress").textContent=
   "Level "+progress.level+" · "+progress.xp+" XP · "+progress.points+
   " skill points · "+progress.done.length+"/"+C.chapters.length+" chapters";
 const chapters=document.getElementById("chapters");chapters.replaceChildren();
 for(const ch of C.chapters){
   const won=finished().has(ch.id),available=unlocked(ch);
   const button=document.createElement("button");
   button.type="button";button.disabled=!available;
   button.textContent=(won?"✓ ":(available?"▶ ":"🔒 "))+ch.title+" · "+ch.reward+" XP";
   button.onclick=()=>launch(ch.id);
   chapters.append(button);
 }
 const container=document.getElementById("skills");container.replaceChildren();
 for(const skill of skills){
   const rank=progress.skills[skill]||0;
   const button=document.createElement("button");
   button.textContent=skill+" "+rank+"/5 (+1)";
   button.disabled=progress.points<1||rank>=5;
   button.onclick=()=>{
     if(progress.points<1||rank>=5)return;
     progress.skills[skill]=rank+1;progress.points--;persist();render();
   };
   container.append(button);
 }
}
function launch(id){
 const ch=byId.get(id);
 if(!ch||!unlocked(ch)){message("That chapter is still locked.");return}
 active=ch.id;
 document.getElementById("current").textContent=ch.title;
 frame.src=ch.file;
 message("Playing "+ch.title+". Reach the exit to unlock the next chapter.");
}
function finish(id){
 const ch=byId.get(id);
 if(!ch||ch.id!==active||!unlocked(ch)||finished().has(id))return;
 progress.done.push(id);progress.xp+=ch.reward;
 while(progress.level<100&&progress.xp>=100*progress.level*progress.level){
   progress.level++;progress.points++;
 }
 persist();render();
 const next=C.chapters.find(candidate=>unlocked(candidate) &&
   !finished().has(candidate.id));
 message("Chapter cleared! +"+ch.reward+" XP. "+
   (next?"Next: "+next.title:"All campaign chapters complete."));
}
window.addEventListener("message",event=>{
 // Same-origin is unavailable for some file:// installs, but frame identity
 // and exact campaign/chapter IDs are required. There is no network side effect.
 if(event.source!==frame.contentWindow)return;
 const data=event.data;
 if(!data||data.type!=="skeleton.game.campaign.completed.v1"||
   data.campaign!==C.campaign||data.chapter!==active)return;
 finish(data.chapter);
});
function download(value,name){
 const data=new Blob([value],{type:"application/json"});
 const url=URL.createObjectURL(data);
 const link=document.createElement("a");link.href=url;link.download=name;link.click();
 setTimeout(()=>URL.revokeObjectURL(url),1000);
}
document.getElementById("save").onclick=()=>download(
 JSON.stringify(progress,null,2),"game-campaign-progress.json");
document.getElementById("load").onclick=()=>document.getElementById("importfile").click();
document.getElementById("importfile").onchange=async event=>{
 const file=event.target.files?.[0];
 if(!file)return;
 if(file.size>100000){message("Progress file too large.");return}
 try{
   const data=JSON.parse(await file.text());
   if(!validProgress(data))throw Error("invalid campaign progress");
   // An imported save is treated as untrusted local state; dependent
   // prerequisites must be represented by already-cleared chapters.
   const prior=new Set();
   for(const id of C.order){
     if(data.done.includes(id)){
       const chapter=byId.get(id);
       if(!chapter.requires.every(dep=>prior.has(dep)))
          throw Error("save bypasses chapter prerequisites");
       prior.add(id);
     }
   }
   progress=data;persist();render();message("Campaign progress imported.");
 }catch(error){message("Import rejected: "+error.message)}
};
document.getElementById("reset").onclick=()=>{
 if(!confirm("Reset all campaign progress?"))return;
 progress=blank();active=null;frame.removeAttribute("src");
 document.getElementById("current").textContent="Select a chapter";
 persist();render();message("Campaign reset.");
};
read();render();
const first=C.chapters.find(ch=>unlocked(ch));
if(first)launch(first.id);
</script></body></html>'''
    return html.replace("__CAMPAIGN__",manifest)


def export_interactive_campaign(campaign: Campaign) -> bytes:
    """Export a truly progressive campaign, not just a list of unrelated links."""
    hub=render_campaign_hub(campaign)
    files=[("index.html",hub.encode("utf-8"))]
    seen=set()
    for idx,chapter in enumerate(campaign.chapters,1):
        if chapter.blueprint.engine not in ("web","phaser"):
            raise ValueError("interactive campaign requires Canvas target")
        name=f"levels/level-{idx:03d}.html"
        playable=build_playable_web_game(chapter.blueprint).html
        patched=_level_with_completion(playable,campaign.campaign_id,
                                       chapter.chapter_id)
        files.append((name,patched.encode("utf-8")))
        seen.add(chapter.chapter_id)
    manifest={
        "schema":"skeleton.original_campaign.launcher.v1",
        "campaign":campaign.campaign_id,"title":campaign.title,
        "chapters":[{
            "chapter":c.chapter_id,"prerequisites":c.prerequisites,
            "reward":c.experience_reward,"blueprint":c.blueprint.fingerprint,
        } for c in campaign.chapters],
    }
    files.append(("campaign.json",json.dumps(manifest,sort_keys=True,
                                            indent=2).encode("utf-8")))
    files.append(("README.md",(
        f"# {campaign.title}\n\nExtract the archive and open index.html.\n"
        "Complete playable chapters to unlock later chapters, earn XP and "
        "spend skill points. Backup progress with the Export progress button.\n"
        "Original artwork and mechanics; no external assets.\n"
        f"Campaign ID: {campaign.campaign_id}\n"
    ).encode("utf-8")))
    out=BytesIO()
    with ZipFile(out,"w",compression=ZIP_DEFLATED,compresslevel=9) as archive:
        for path,payload in files:
            entry=ZipInfo(path,date_time=(2026,1,1,0,0,0))
            entry.compress_type=ZIP_DEFLATED
            entry.external_attr=0o644<<16
            archive.writestr(entry,payload)
    return out.getvalue()
