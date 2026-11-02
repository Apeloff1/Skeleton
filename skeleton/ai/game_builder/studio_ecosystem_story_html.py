"""Source-bound, actually interactive browser quest director. No external IO."""
from __future__ import annotations
from base64 import b64encode
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
textarea{display:block;width:100%;box-sizing:border-box;min-height:9em;
 background:#0d1723;color:#f0f5fb;border:2px solid #9ec8dc;border-radius:8px;
 padding:10px;font:14px ui-monospace,monospace;overflow-wrap:anywhere}
textarea:focus-visible{outline:3px solid #f3cc6f;outline-offset:3px}
"""
_JS = """
"use strict";
const source=JSON.parse(document.getElementById("studio-source").textContent);
const chosen=[];
const completed=new Set();
const byId=new Map(source.stages.map(s=>[s.id,s]));
const host=document.getElementById("stages");
const summary=document.getElementById("summary");
const premise=document.getElementById("premise");
const transcript=document.getElementById("transcript");
const endings=document.getElementById("endings");
const checkpoint=document.getElementById("checkpoint");
const checkpointStatus=document.getElementById("checkpoint-status");
const previewStatus=document.getElementById("choice-preview");
const compareStatus=document.getElementById("checkpoint-compare-status");
const mergeStatus=document.getElementById("checkpoint-merge-status");
const ancestorInput=document.getElementById("checkpoint-ancestor");
function node(tag,text){const el=document.createElement(tag);if(text!==undefined)el.textContent=text;return el;}
function reset(){chosen.length=0;completed.clear();previewStatus.textContent="";compareStatus.textContent="";render();}
function act(id,option){
 const stage=byId.get(id);
 if(!stage||completed.has(id)||!stage.prerequisites.every(dep=>completed.has(dep))||
    !stage.alternatives.includes(option)){return;}
 chosen.push([id,option]);completed.add(id);previewStatus.textContent="";compareStatus.textContent="";render();
}
function parseCheckpoint(raw){
 if(typeof raw!=="string"||raw.length>16384){throw Error("checkpoint too large");}
 const data=JSON.parse(raw);
 // Accept only the exact pretty-printed receipt emitted by this browser.
 // JSON.parse alone silently collapses duplicate keys and ambiguous spellings.
 if(raw.trim()!==JSON.stringify(data,null,2)){
   throw Error("noncanonical or duplicate-key checkpoint");
 }
 if(!data||Array.isArray(data)||typeof data!=="object"||
    Object.keys(data).sort().join(",")!==
    "choices,external_evidence_verified,native_genre_runtime_verified,project_id,release_certified,schema,source_digest"||
    data.schema!=="skeleton.game_builder.offline_story_choices.v1"||
    data.project_id!==source.project_id||data.source_digest!==source.source_digest||
    data.external_evidence_verified!==false||
    data.native_genre_runtime_verified!==false||data.release_certified!==false||
    !Array.isArray(data.choices)||data.choices.length>source.stages.length){
   throw Error("checkpoint source or schema mismatch");
 }
 const done=new Set();
 const validated=[];
 for(const pair of data.choices){
   if(!Array.isArray(pair)||pair.length!==2||
      typeof pair[0]!=="string"||typeof pair[1]!=="string"){
     throw Error("invalid checkpoint action");
   }
   const stage=byId.get(pair[0]);
   if(!stage||done.has(pair[0])||!stage.alternatives.includes(pair[1])||
      !stage.prerequisites.every(dep=>done.has(dep))){
     throw Error("illegal checkpoint quest history");
   }
   done.add(pair[0]);validated.push(pair.slice());
 }
 return validated;
}
function restoreCheckpoint(){
 try{
   const actions=parseCheckpoint(checkpoint.value);
   chosen.splice(0,chosen.length,...actions);
   completed.clear();
   for(const [id] of actions){completed.add(id);}
   previewStatus.textContent="";
   compareStatus.textContent="";
   render();
   checkpointStatus.textContent="Source-matched sandbox checkpoint restored";
 }catch(error){
   checkpointStatus.textContent="Checkpoint rejected; current progress preserved";
 }
}
function earnedFacts(history){
 const earned=new Set();
 for(const [id,option] of history){
   const stage=byId.get(id);
   if(!stage){throw Error("unknown authored stage");}
   earned.add(id);earned.add(stage.reward);
   const effects=stage.choice_effects;
   // JSON objects inherit names such as toString and constructor. An
   // unlisted alternative must never execute inherited prototype values.
   const tokens=Object.prototype.hasOwnProperty.call(effects,option)
     ? effects[option] : [];
   for(const token of tokens){earned.add(token);}
 }
 return earned;
}
function previewChoice(id,option){
 const stage=byId.get(id);
 if(!stage||completed.has(id)||!stage.prerequisites.every(dep=>completed.has(dep))||
    !stage.alternatives.includes(option)){return;}
 const before=earnedFacts(chosen);
 const after=earnedFacts([...chosen,[id,option]]);
 const newly=[];
 const remaining=[];
 for(const ending of source.endings){
   const unmet=ending.requires.filter(required=>!after.has(required));
   if(unmet.length===0 && ending.requires.some(required=>!before.has(required))){
     newly.push(ending.id);
   }
   if(unmet.length){remaining.push(ending.id+": "+unmet.join(", "));}
 }
 previewStatus.textContent="Sandbox preview "+id+" / "+option+
   "; newly eligible endings: "+(newly.join(", ")||"none")+
   "; still unmet: "+(remaining.join("; ")||"none")+
   ". This preview does not commit a choice or verify external consequences.";
}
function undoChoice(){
 if(chosen.length===0){return;}
 const last=chosen.pop();
 completed.delete(last[0]);
 previewStatus.textContent="";
 compareStatus.textContent="";
 render();
}
function compareCheckpoint(){
 try{
   const other=parseCheckpoint(checkpoint.value);
   let common=0;
   while(common<chosen.length&&common<other.length&&
     chosen[common][0]===other[common][0]&&chosen[common][1]===other[common][1]){
     common++;
   }
   const eligible=history=>source.endings.filter(ending=>
     ending.requires.every(token=>earnedFacts(history).has(token))).map(ending=>ending.id);
   const current=new Set(eligible(chosen));
   const proposed=new Set(eligible(other));
   const gained=[...proposed].filter(id=>!current.has(id));
   const lost=[...current].filter(id=>!proposed.has(id));
   compareStatus.textContent="Source-verified sandbox comparison: common actions "+
     common+"; current-only "+(chosen.length-common)+"; pasted-only "+
     (other.length-common)+"; endings gained "+(gained.join(", ")||"none")+
     "; endings lost "+(lost.join(", ")||"none")+
     ". No choice was changed or externally verified.";
 }catch(error){
   compareStatus.textContent="Checkpoint comparison rejected; current progress preserved";
 }
}
function mergeCheckpoint(){
 // Browser-side reconciliation is a convenience preview only. The canonical
 // Python merge CLI must independently replay and save the proposed result.
 try{
   const ancestor=parseCheckpoint(ancestorInput.value);
   const candidate=parseCheckpoint(checkpoint.value);
   const current=chosen.map(pair=>pair.slice());
   const prefix=(base,history)=>base.length<=history.length&&
     base.every((pair,index)=>pair[0]===history[index][0]&&pair[1]===history[index][1]);
   if(!prefix(ancestor,current)||!prefix(ancestor,candidate)){
     throw Error("fork does not extend the shared ancestor");
   }
   const mergedMap=new Map(ancestor);
   for(const [id,choice] of [...current.slice(ancestor.length),
                              ...candidate.slice(ancestor.length)]){
     if(mergedMap.has(id)&&mergedMap.get(id)!==choice){
       throw Error("conflicting authored choice");
     }
     mergedMap.set(id,choice);
   }
   const ancestorIds=new Set(ancestor.map(pair=>pair[0]));
   const merged=[...ancestor.map(pair=>pair.slice())];
   for(const stage of source.stages){
     if(mergedMap.has(stage.id)&&!ancestorIds.has(stage.id)){
       merged.push([stage.id,mergedMap.get(stage.id)]);
     }
   }
   const subsequence=(history)=>{
     let cursor=0;
     for(const pair of merged){
       if(cursor<history.length&&history[cursor][0]===pair[0]&&
          history[cursor][1]===pair[1]){cursor++;}
     }
     return cursor===history.length;
   };
   if(!subsequence(current)||!subsequence(candidate)){
     throw Error("incompatible fork ordering");
   }
   // Validate the merged history using the same source-leased replay as restore.
   const receipt={schema:"skeleton.game_builder.offline_story_choices.v1",
     project_id:source.project_id,source_digest:source.source_digest,
     choices:merged,external_evidence_verified:false,
     native_genre_runtime_verified:false,release_certified:false};
   const proposed=JSON.stringify(receipt,null,2);
   parseCheckpoint(proposed);
   checkpoint.value=proposed;
   mergeStatus.textContent="Proposed "+merged.length+"-action checkpoint is in the editor. "+
     "Current progress was not changed. Save using the operator CLI for canonical replay "+
     "and exclusive private publication; no external evidence is verified.";
 }catch(error){
   mergeStatus.textContent="Fork merge rejected; current progress and pasted candidate preserved.";
 }
}
function render(){
 host.replaceChildren();endings.replaceChildren();
 summary.textContent=completed.size+" of "+source.stages.length+" authored stages complete";
 document.getElementById("undo").disabled=chosen.length===0;
 premise.textContent=source.premise+" — "+source.protagonist_name;
 for(const stage of source.stages){
   const open=!completed.has(stage.id)&&stage.prerequisites.every(dep=>completed.has(dep));
   const box=node("section");box.setAttribute("aria-label",stage.id);
   box.append(node("h2",stage.id),node("p","Scene: "+stage.scene_id));
   box.append(node("p","Authored goal: "+stage.authored_goal),
              node("p","Decision: "+stage.authored_decision));
   if(completed.has(stage.id)){box.append(node("p","Completed, sandbox reward: "+stage.reward));}
   else if(!open){box.append(node("p","Locked until dependencies are complete"));}
   else{
     box.append(node("p","Choose one source-authored action:"));
     for(const choice of stage.alternatives){
       const button=node("button",choice);button.type="button";
       button.addEventListener("click",()=>act(stage.id,choice));box.append(button);
       const preview=node("button","Preview: "+choice);preview.type="button";
       preview.addEventListener("click",()=>previewChoice(stage.id,choice));
       box.append(preview);
     }
   }
   host.append(box);
 }
 const earned=earnedFacts(chosen);
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
document.getElementById("undo").addEventListener("click",undoChoice);
document.getElementById("checkpoint-compare").addEventListener("click",compareCheckpoint);
document.getElementById("checkpoint-merge").addEventListener("click",mergeCheckpoint);
document.getElementById("checkpoint-copy").addEventListener("click",()=>{
 checkpoint.value=transcript.textContent;
 checkpointStatus.textContent="Copy this checkpoint to save it privately";
});
document.getElementById("checkpoint-restore").addEventListener("click",restoreCheckpoint);
render();
"""

def story_source(documents: Mapping[str, Any]) -> dict[str, object]:
    program=compile_quest_program(documents)
    scenes=scene_catalog(documents)
    if len(scenes)!=len(program.stages):
        raise StudioQuestError("scene/quest cardinality mismatch")
    narrative=documents.get("narrative")
    if type(narrative) is not dict or type(narrative.get("premise")) is not str:
        raise StudioQuestError("missing authored story premise")
    premise=narrative["premise"]
    cast=documents.get("cast")
    protagonist=cast.get("protagonist") if type(cast) is dict else None
    name=protagonist.get("name") if type(protagonist) is dict else None
    if type(name) is not str or not 1 <= len(name) <= 512:
        raise StudioQuestError("invalid authored protagonist presentation")
    beats=narrative.get("plot_beats")
    if (not 1 <= len(premise) <= 1024 or type(beats) is not list
            or len(beats) != len(program.stages)):
        raise StudioQuestError("invalid authored story presentation")
    stages=[]
    for stage,scene,beat in zip(program.stages,scenes,beats,strict=True):
        if type(beat) is not dict:
            raise StudioQuestError("invalid authored story beat")
        for key in ("goal", "decision"):
            if type(beat.get(key)) is not str or not 1 <= len(beat[key]) <= 1024:
                raise StudioQuestError("invalid authored story beat presentation")
        if stage.key!=scene["quest_stage"]:
            raise StudioQuestError("scene and authored quest stage differ")
        stages.append({"id":stage.key,"prerequisites":list(stage.prerequisites),
                       "alternatives":list(stage.alternatives),"reward":stage.reward,
                       "choice_effects":{choice:list(tokens)
                                         for choice,tokens in stage.choice_effects},
                       "scene_id":scene["scene_id"],"objects":list(scene["objects"]),
                       "authored_goal":beat["goal"],"authored_decision":beat["decision"]})
    return {"schema":"skeleton.game_builder.offline_story_source.v1",
            "project_id":program.project_id,"source_digest":program.source_digest,
            "premise":premise,"protagonist_name":name,
            "stages":stages,
            "endings":[{"id":key,"requires":list(reqs)} for key,reqs in program.endings],
            "external_evidence_verified":False,"release_certified":False}


def _csp_hash(source: str) -> str:
    digest=b64encode(sha256(source.encode("utf-8")).digest()).decode("ascii")
    return "'sha256-"+digest+"'"


def render_story_html(documents: Mapping[str, Any]) -> bytes:
    source=story_source(documents)
    payload=json.dumps(source,sort_keys=True,ensure_ascii=True,allow_nan=False,
                       separators=(",",":"))
    payload=(payload.replace("<",r"\u003c").replace(">",r"\u003e")
                    .replace("&",r"\u0026"))
    project=escape(source["project_id"],quote=True)
    policy=("default-src 'none'; script-src "+_csp_hash(payload)+" "+
            _csp_hash(_JS)+"; style-src "+_csp_hash(_CSS)+
            "; base-uri 'none'; form-action 'none'; object-src 'none'")
    page=(
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<meta http-equiv='Content-Security-Policy' content=\""+policy+"\">"
        "<title>Original interactive quest — "+project+"</title>"
        "<style>"+_CSS+"</style></head><body>"
        "<header><h1>Original interactive quest</h1><p>Project: "+project+"</p>"
        "<p>Sandbox choices, not native world interactions</p></header>"
        "<main><p id='premise'></p><p id='summary' role='status' aria-live='polite'></p>"
        "<div id='stages'></div><section><h2>Noncommitting choice preview</h2>"
        "<p id='choice-preview' role='status' aria-live='polite'></p></section>"
        "<section><h2>Ending requirements</h2>"
        "<ul id='endings'></ul></section>"
        "<section><h2>Replay transcript</h2><button type='button' id='restart'>"
        "Restart simulation</button><button type='button' id='undo'>"
        "Undo last authored choice</button><pre id='transcript'></pre>"
        "<h3>Private copy/paste checkpoint</h3>"
        "<p>Save the text yourself; restoring verifies source and legal quest order.</p>"
        "<button type='button' id='checkpoint-copy'>Copy current receipt into editor</button>"
        "<label for='checkpoint'>Checkpoint JSON</label>"
        "<textarea id='checkpoint' rows='8' maxlength='16384' spellcheck='false'></textarea>"
        "<button type='button' id='checkpoint-restore'>Restore pasted checkpoint</button>"
        "<button type='button' id='checkpoint-compare'>Compare pasted checkpoint</button>"
        "<p id='checkpoint-compare-status' role='status' aria-live='polite'></p>"
        "<p id='checkpoint-status' role='status' aria-live='polite'></p>"
        "<h3>Reconcile offline story forks</h3>"
        "<p>Paste the common ancestor here and a second fork in the checkpoint editor. "
        "Preview is noncommitting; the operator CLI must verify and privately save it.</p>"
        "<label for='checkpoint-ancestor'>Shared ancestor checkpoint JSON</label>"
        "<textarea id='checkpoint-ancestor' rows='8' maxlength='16384' spellcheck='false'></textarea>"
        "<button type='button' id='checkpoint-merge'>Preview three-way fork merge</button>"
        "<p id='checkpoint-merge-status' role='status' aria-live='polite'></p>"
        "</section></main>"
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
