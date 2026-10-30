"""Source-bound, actually interactive browser quest director. No external IO."""
from __future__ import annotations
from hashlib import sha256
from html import escape
import json
from typing import Any, Mapping
from .studio_ecosystem_quest import compile_quest_program, StudioQuestError
from .studio_ecosystem_scene import scene_catalog

_CSS = """
:root{color-scheme:dark;background:#101b28;color:#f0f5fb;font:16px system-ui}
body{max-width:950px;margin:auto;padding:clamp(14px,4vw,40px)}
section{background:#1a2a3b;border:1px solid #46627c;border-radius:12px;padding:18px;margin:16px 0}
button{font:inherit;border:2px solid #9ec8dc;border-radius:8px;padding:10px 14px;
margin:6px;background:#21465f;color:#fff;cursor:pointer}
button:focus-visible{outline:3px solid #f3cc6f;outline-offset:3px}
button:hover{background:#306583}pre{white-space:pre-wrap;overflow-wrap:anywhere}
"""
_JS = """
"use strict";
const source=JSON.parse(document.getElementById("studio-source").textContent);
const chosen=[];
const completed=new Set();
const byId=new Map(source.stages.map(s=>[s.id,s]));
const host=document.getElementById("stages");
const summary=document.getElementById("summary");
const transcript=document.getElementById("transcript");
const endings=document.getElementById("endings");
function node(tag,text){const el=document.createElement(tag);if(text!==undefined)el.textContent=text;return el;}
function reset(){chosen.length=0;completed.clear();render();}
function act(id,option){
 const stage=byId.get(id);
 if(!stage||completed.has(id)||!stage.prerequisites.every(dep=>completed.has(dep))||
    !stage.alternatives.includes(option)){return;}
 chosen.push([id,option]);completed.add(id);render();
}
function render(){
 host.replaceChildren();endings.replaceChildren();
 summary.textContent=completed.size+" of "+source.stages.length+" authored stages complete";
 for(const stage of source.stages){
   const open=!completed.has(stage.id)&&stage.prerequisites.every(dep=>completed.has(dep));
   const box=node("section");box.setAttribute("aria-label",stage.id);
   box.append(node("h2",stage.id),node("p","Scene: "+stage.scene_id));
   if(completed.has(stage.id)){box.append(node("p","Completed, sandbox reward: "+stage.reward));}
   else if(!open){box.append(node("p","Locked until dependencies are complete"));}
   else{
     box.append(node("p","Choose one source-authored action:"));
     for(const choice of stage.alternatives){
       const button=node("button",choice);button.type="button";
       button.addEventListener("click",()=>act(stage.id,choice));box.append(button);
     }
   }
   host.append(box);
 }
 const earned=new Set(completed);
 for(const stage of source.stages){if(completed.has(stage.id))earned.add(stage.reward);}
 for(const ending of source.endings){
   const missing=ending.requires.filter(required=>!earned.has(required));
   endings.append(node("li",ending.id+": "+(missing.length===0
     ?"eligible in authored sandbox only":"unmet predicates: "+missing.join(", "))));
 }
 const receipt={schema:"skeleton.game_builder.offline_story_choices.v1",
   project_id:source.project_id,source_digest:source.source_digest,
   choices:chosen.map(pair=>pair.slice()),external_evidence_verified:false,
   native_genre_runtime_verified:false,release_certified:false};
 transcript.textContent=JSON.stringify(receipt,null,2);
}
document.getElementById("restart").addEventListener("click",reset);
render();
"""

def story_source(documents: Mapping[str, Any]) -> dict[str, object]:
    program=compile_quest_program(documents)
    scenes=scene_catalog(documents)
    if len(scenes)!=len(program.stages):
        raise StudioQuestError("scene/quest cardinality mismatch")
    stages=[]
    for stage,scene in zip(program.stages,scenes,strict=True):
        if stage.key!=scene["quest_stage"]:
            raise StudioQuestError("scene and authored quest stage differ")
        stages.append({"id":stage.key,"prerequisites":list(stage.prerequisites),
                       "alternatives":list(stage.alternatives),"reward":stage.reward,
                       "scene_id":scene["scene_id"],"objects":list(scene["objects"])})
    return {"schema":"skeleton.game_builder.offline_story_source.v1",
            "project_id":program.project_id,"source_digest":program.source_digest,
            "stages":stages,
            "endings":[{"id":key,"requires":list(reqs)} for key,reqs in program.endings],
            "external_evidence_verified":False,"release_certified":False}


def render_story_html(documents: Mapping[str, Any]) -> bytes:
    source=story_source(documents)
    payload=json.dumps(source,sort_keys=True,ensure_ascii=True,allow_nan=False,
                       separators=(",",":"))
    payload=(payload.replace("<",r"\u003c").replace(">",r"\u003e")
                    .replace("&",r"\u0026"))
    project=escape(source["project_id"],quote=True)
    page=(
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<meta http-equiv='Content-Security-Policy' content=\"default-src 'none';"
        " script-src 'unsafe-inline'; style-src 'unsafe-inline';"
        " base-uri 'none'; form-action 'none'\">"
        "<title>Original interactive quest — "+project+"</title>"
        "<style>"+_CSS+"</style></head><body>"
        "<header><h1>Original interactive quest</h1><p>Project: "+project+"</p>"
        "<p>Sandbox choices, not native world interactions</p></header>"
        "<main><p id='summary' role='status' aria-live='polite'></p>"
        "<div id='stages'></div><section><h2>Ending requirements</h2>"
        "<ul id='endings'></ul></section>"
        "<section><h2>Replay transcript</h2><button type='button' id='restart'>"
        "Restart simulation</button><pre id='transcript'></pre></section></main>"
        "<script type='application/json' id='studio-source'>"+payload+"</script>"
        "<script>"+_JS+"</script></body></html>"
    )
    return page.encode("utf-8")


def story_html_receipt(documents: Mapping[str, Any]) -> dict[str, object]:
    content=render_story_html(documents)
    return {"schema":"skeleton.game_builder.offline_story_html_receipt.v1",
            "project_id":story_source(documents)["project_id"],
            "html_sha256":sha256(content).hexdigest(),"html_bytes":len(content),
            "browser_quest_choices_implemented":True,
            "native_gameplay_verified":False,"release_certified":False}
