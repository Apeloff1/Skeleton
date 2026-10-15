"""A self-contained operator-only dual-screen live study page.

The HTML's script/style are nonce restricted, input appears below each native
screen, and all dynamic game names/labels are textContent. Browser never
receives game source, disk paths, credentials for native worker, or BIOS.
"""
from __future__ import annotations
import re


def render_live_comparison_page(token: str, nonce: str) -> str:
    if (not isinstance(token,str) or not re.fullmatch(r"[0-9a-f]{64}",token)
        or not isinstance(nonce,str) or not re.fullmatch(r"[0-9a-f]{32}",nonce)):
        raise ValueError("Live viewer requires process-bound cryptographic tokens")
    page=r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Jeeves · Live Comparative Emulator Lab</title>
<style nonce="__NONCE__">
:root{color-scheme:dark;background:#0f1725;color:#e7f0fb;font:14px system-ui,sans-serif}
*{box-sizing:border-box}body{margin:0;padding:22px;max-width:1650px;margin-inline:auto}
h1{font-size:24px;margin:0}h2{font-size:17px;margin:12px 0 8px}h3{font-size:15px;margin:7px 0}
p{line-height:1.45}small,.subtle{color:#b2bfd0}
header{display:flex;flex-wrap:wrap;justify-content:space-between;gap:14px;align-items:center;margin-bottom:17px}
button,select,input,textarea{background:#1b2b40;border:1px solid #56708c;border-radius:8px;color:#f5faff;font:inherit;padding:8px;max-width:100%}
button{cursor:pointer;touch-action:manipulation}button:hover{background:#315374}button:disabled{opacity:.5}
button:focus-visible,select:focus-visible{outline:3px solid #d6c083}
main{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:15px}
.player{min-width:0;background:#1b2839;border:1px solid #3c4c62;padding:15px;border-radius:12px}
.screen{aspect-ratio:16/10;background:#05080e;display:flex;align-items:center;justify-content:center;overflow:hidden;border-radius:8px;margin-top:10px}
.screen img{max-width:100%;max-height:100%;object-fit:contain}
.deck{border:2px solid #405d7b;background:#24334b;border-radius:15px;padding:12px;margin-top:13px}
.deckface{position:relative;height:150px;background:#142034;border-radius:24px;margin-top:9px}
.inputbutton{position:absolute;transform:translate(-50%,-50%);padding:8px;min-width:36px;max-width:76px;font-size:11px;border-radius:20px}
.inputbutton.selected{background:#c5eeb0;color:#14231d;border:1px solid #87aa81}
.inline{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-top:10px}
.stats{font:12px ui-monospace,monospace;overflow-wrap:anywhere;color:#b6cad9;line-height:1.55;margin-top:9px}
canvas{height:125px;width:100%;background:#0d1725;border-radius:8px;margin-top:9px}
.events{max-height:175px;overflow:auto;font:11px ui-monospace,monospace;overflow-wrap:anywhere;line-height:1.7}
.events div{padding:4px;border-bottom:1px solid #35465d}
button.critical{border-color:#c88b7e}footer{margin-top:20px;color:#b2bfd0}
.port-extra{display:flex;flex-wrap:wrap;gap:5px}.port-extra label{font:11px system-ui;max-width:110px}
.port-extra input{width:88px}
section.notes{background:#192536;border:1px solid #3e5268;border-radius:12px;margin-top:16px;padding:15px}
textarea{width:100%;min-height:75px;resize:vertical}
@media(max-width:900px){main{grid-template-columns:1fr}body{padding:12px}}
</style></head>
<body>
<header><div><h1>Live Comparative Emulator Lab</h1>
<small>Approved local libretro · two visible games · up to ten simultaneous lanes</small></div>
<div class="inline"><label>Steps per advance <select id="repeat"><option value="1">1</option><option value="2">2</option><option value="4">4</option><option value="8">8</option></select></label>
<button id="all">Advance all active games</button>
<button id="evidence">Export native evidence</button>
<button id="stop" class="critical">Stop &amp; close workers</button></div></header>
<p id="message" role="status" aria-live="polite">Connecting to the operator-approved native session…</p>
<main><section id="left" class="player"></section><section id="right" class="player"></section></main>
<section class="notes">
<h2>Attributable viewer notes</h2>
<p class="subtle">Drafts stay in this browser until exported. They are never uploaded to Dragon or model memory automatically.</p>
<div class="inline"><label>Dimension <select id="dimension"></select></label>
<label>Checkpoint <select id="checkpoint"><option>earlier</option><option>middle</option><option>after</option></select></label>
<label>Kind <select id="claim"><option>observation</option><option>interpretation</option><option>hypothesis</option></select></label></div>
<textarea id="note" maxlength="1000" placeholder="Describe a measured control response, mechanical contrast or a question for further review…"></textarea>
<div class="inline"><button id="addnote">Add note for visible pair</button><button id="exportnotes">Export notes JSON</button><small id="notecount">0 local notes</small></div>
</section>
<footer>Controllers are mounted strictly <strong>under</strong> real screens, never superimposed on gameplay. Frame/audio hashes and event graphs are native observations, not game accuracy, learned wisdom or production-weight gains. Browser commands use a local process token and cannot change installed core binaries.</footer>
<script nonce="__NONCE__">
"use strict";
const auth="__TOKEN__";
const $=id=>document.getElementById(id);
const msg=value=>{$("message").textContent=value};
const txt=(tag,value,cls)=>{const el=document.createElement(tag);el.textContent=String(value??"");if(cls)el.className=cls;return el};
const choose=(value,label)=>{const o=txt("option",label);o.value=value;return o};
let current=null;
const selected={left:null,right:null};
const pressed=new Map(),numeric=new Map();
const notes=[];
const dims=["movement","input","combat","navigation","story","dialogue","camera","cutscene","character","npc","environment","pacing","challenge","reward","audio","music","ambience","visuals","interface","accessibility","emergence","economy","physics","mission","level_design","consequence","world_design","other"];
dims.forEach(x=>$("dimension").append(choose(x,x)));
const key=(id,port)=>id+"::"+port;
const active=(id,port)=>{const k=key(id,port);if(!pressed.has(k))pressed.set(k,new Map());return pressed.get(k)};
const numbers=(id,port)=>{const k=key(id,port);if(!numeric.has(k))numeric.set(k,[0,0,0,0]);return numeric.get(k)};
async function request(path,body){
 const init={method:body===undefined?"GET":"POST",headers:{"X-Study-Token":auth}};
 if(body!==undefined){init.headers["Content-Type"]="application/json";init.body=JSON.stringify(body)}
 const res=await fetch(path,init);
 const value=await res.json();
 if(!res.ok)throw Error(value.reason||"Local native request rejected");
 return value
}
const empty=()=>({buttons:0,axes:[0,0,0,0],keys:[],mouse:[0,0,0,0,0,0],pointer:[0,0,0]});
function vector(id){
 const layout=current.lanes[id].controller_layout;
 return layout.ports.map(port=>{
  const value=empty(),choices=active(id,port.port);
  for(const item of choices.values()){
   if(item.input_kind==="bitmask")value.buttons|=item.mask;
   else if(item.input_kind==="keycode")value.keys.push(item.key_code);
   else if(item.input_kind==="mouse_button")value.mouse[item.mouse_index]=1;
   else if(item.input_kind==="pointer_button")value.pointer[item.pointer_index]=1;
  }
  const extra=numbers(id,port.port);
  if(port.device==="analog")value.axes=extra.slice(0,4);
  else if(port.device==="mouse"){value.mouse[0]=extra[0];value.mouse[1]=extra[1]}
  else if(port.device==="pointer"){value.pointer[0]=extra[0];value.pointer[1]=extra[1]}
  return value
 })
}
function clearInputs(id){
 for(const port of current.lanes[id].controller_layout.ports){active(id,port.port).clear();
  numeric.set(key(id,port.port),[0,0,0,0])
 }
}
function exportJSON(name,value){
 const url=URL.createObjectURL(new Blob([JSON.stringify(value,null,2)],{type:"application/json"}));
 const link=document.createElement("a");link.href=url;link.download=name.replace(/[^a-z0-9_-]/gi,"_")+".json";
 document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),5000)
}
async function load(){
 current=await request("/api/state");
 if(!selected.left||!current.lanes[selected.left])selected.left=current.native_game_ids[0];
 if(!selected.right||!current.lanes[selected.right]||selected.left===selected.right)
  selected.right=current.native_game_ids.find(x=>x!==selected.left);
 render()
}
async function step(ids){
 if(!current)return;
 try{
  msg("Running "+ids.length+" actual native game worker(s)…");
  const repeat=Number($("repeat").value)||1;
  const response=await request("/api/step",{steps:ids.map(id=>({game_id:id,controls:vector(id),repeat}))});
  ids.forEach(clearInputs);await load();
  msg(response.all_succeeded?"Real native frames updated · "+repeat+" receipt(s) per game":"One or more native bursts failed or reached a limit; inspect the per-game evidence");
 }catch(e){msg("Native step rejected: "+e.message)}
}
async function resetGame(id){
 try{await request("/api/reset",{game_id:id});clearInputs(id);await load();msg("Actual native core reset, not a fake frame")}catch(e){msg("Reset rejected: "+e.message)}
}
function deckFor(id){
 const lane=current.lanes[id],layout=lane.controller_layout;
 const deck=txt("section","","deck");
 deck.append(txt("strong",layout.profile_name+" · "+(layout.generic_fallback?"generic RetroPad fallback":"hardware-style legend, not accuracy certified")));
 deck.append(txt("p","Native input controls are below the gameplay view. Toggle buttons, choose port, then advance.","subtle"));
 const bar=txt("div","","inline");
 const select=document.createElement("select");
 layout.ports.forEach(p=>select.append(choose(String(p.port),"Port "+(p.port+1)+" · "+p.device)));
 bar.append(txt("label","Input port"),select);
 const clear=txt("button","Clear controls");bar.append(clear);deck.append(bar);
 const face=txt("div","","deckface"),extra=txt("div","","port-extra");deck.append(face,extra);
 function redraw(){
  const port=layout.ports[Number(select.value)||0],act=active(id,port.port);
  face.replaceChildren();extra.replaceChildren();
  if(port.device==="none"){face.append(txt("p","Disconnected controller port","subtle"));return}
  (port.controls||[]).forEach(item=>{
   const b=txt("button",item.legend,"inputbutton"+(act.has(item.id)?" selected":""));
   b.type="button";b.style.left=item.x+"%";b.style.top=item.y+"%";
   b.title=item.id+" / "+item.input_kind;
   b.setAttribute("aria-pressed",act.has(item.id)?"true":"false");
   b.onclick=()=>{act.has(item.id)?act.delete(item.id):act.set(item.id,item);redraw()};
   face.append(b)
  });
  const values=numbers(id,port.port);
  const labels=port.device==="analog"?["Left X","Left Y","Right X","Right Y"]:
    port.device==="mouse"?["Mouse ΔX","Mouse ΔY"]:
    port.device==="pointer"?["Pointer X","Pointer Y"]:[];
  labels.forEach((label,index)=>{
   const wrap=txt("label",label),input=document.createElement("input");input.type="number";
   input.min="-32768";input.max="32767";input.step="1";input.value=values[index];
   input.onchange=()=>{const next=Number(input.value);
    values[index]=Number.isInteger(next)&&next>=-32768&&next<=32767?next:0;
    input.value=String(values[index])
   };
   wrap.append(input);extra.append(wrap)
  })
 }
 select.onchange=redraw;clear.onclick=()=>{clearInputs(id);redraw()};
 redraw();return deck
}
function graphFor(lane){
 const container=txt("div","");
 const cv=document.createElement("canvas");cv.width=640;cv.height=125;
 cv.setAttribute("aria-label","Actual native visual-change and audio RMS traces");
 container.append(cv);
 const cx=cv.getContext("2d"),list=lane.native_receipts||[];
 if(cx){cx.fillStyle="#0d1725";cx.fillRect(0,0,640,125);
  [["visual_change","#80c1e5"],["audio_rms","#e6b77c"]].forEach(([measure,color])=>{
   const values=list.map(r=>Number(r.objective_observations?.[measure]||0));
   const upper=Math.max(1e-6,...values.map(Math.abs));
   cx.strokeStyle=color;cx.lineWidth=2;cx.beginPath();
   values.forEach((v,i)=>{const x=8+624*i/Math.max(1,values.length-1),y=115-106*Math.min(1,Math.abs(v)/upper);
    if(i===0)cx.moveTo(x,y);else cx.lineTo(x,y)});cx.stroke()
  })
 }
 container.append(txt("small","Blue visual change · amber audio RMS · independent scales, not game scores"));
 const details=document.createElement("details"),summary=txt("summary","Native event log · "+list.length+" receipts");details.append(summary);
 const table=txt("div","","events");
 list.slice(-64).forEach(r=>{
  table.append(txt("div","#"+r.index+" input "+r.input_vector_sha256?.slice(0,12)+
  " · frame "+r.frame_sha256?.slice(0,12)+" · PCM "+r.pcm_sha256?.slice(0,12)+
  " · chain "+r.receipt_sha256?.slice(0,15)))
 });details.append(table);container.append(details);return container
}
const activeAudioUrls=[];
function nativeAudioMonitor(frame){
 const audio=frame?.recent_native_pcm_preview;
 const region=txt("div","","inline");
 if(!audio||!audio.samples_base64||!audio.sample_frames){
  region.append(txt("small","Native PCM excerpt unavailable for this frame."));
  return region
 }
 const button=txt("button","Listen to bounded native PCM");
 button.type="button";
 const description=txt("small",audio.sample_frames+" frames @ "+audio.sample_rate+
   " Hz · "+audio.sample_duration_seconds+" s · captured native game audio");
 const player=document.createElement("audio");player.controls=true;player.preload="none";
 player.setAttribute("aria-label","Actual native audio excerpt, manual playback only");
 button.onclick=()=>{
  try{
   const binary=atob(audio.samples_base64),length=binary.length;
   if(length!==audio.sample_frames*4||length>65536)throw Error("PCM length mismatch");
   const data=new ArrayBuffer(length+44),view=new DataView(data);
   function tag(offset,str){for(let i=0;i<str.length;i++)view.setUint8(offset+i,str.charCodeAt(i))}
   const rate=Number(audio.sample_rate);
   if(!Number.isFinite(rate)||rate<8000||rate>384000)throw Error("Invalid PCM sample rate");
   tag(0,"RIFF");view.setUint32(4,length+36,true);
   tag(8,"WAVE");tag(12,"fmt ");view.setUint32(16,16,true);
   view.setUint16(20,1,true);view.setUint16(22,2,true);
   view.setUint32(24,rate,true);view.setUint32(28,rate*4,true);
   view.setUint16(32,4,true);view.setUint16(34,16,true);
   tag(36,"data");view.setUint32(40,length,true);
   const output=new Uint8Array(data,44);
   for(let i=0;i<length;i++)output[i]=binary.charCodeAt(i);
   const url=URL.createObjectURL(new Blob([data],{type:"audio/wav"}));
   activeAudioUrls.push(url);
   player.src=url;player.load();
   button.disabled=true;description.textContent+=" · sample loaded locally"
  }catch(error){description.textContent="Native PCM playback rejected: "+error.message}
 };
 region.append(button,player,description);
 return region
}
function discDeckFor(id){
 const lane=current.lanes[id],status=lane.native_disc_status;
 const section=txt("section","","deck");
 section.append(txt("strong","Native console media · installed core only"));
 if(!status?.supported||status.image_count<2){
  section.append(txt("small","No multi-disc interface registered by this native core."));
  return section
 }
 const summary=txt("p","Disc "+(status.image_index===null?"not inserted":(status.image_index+1))+
    " of "+status.image_count+" · "+(status.ejected?"tray ejected":"tray closed")+
    " · swaps "+lane.native_disc_change_count+"/32","subtle");
 const controls=txt("div","","inline"),select=document.createElement("select");
 select.setAttribute("aria-label","Select previously loaded console disc");
 for(let i=0;i<status.image_count;i++)select.append(choose(String(i),"Disc "+(i+1)));
 select.value=String(status.image_index??0);
 const button=txt("button","Switch to selected disc");
 button.type="button";
 button.disabled=lane.status!=="running"||status.ejected||lane.native_disc_change_count>=32;
 button.onclick=async()=>{
  const target=Number(select.value);
  if(!Number.isInteger(target)||target<0||target>=status.image_count){
   msg("Disc change rejected: invalid preloaded disc");return
  }
  if(target===status.image_index){
   msg("That native disc is already inserted");return
  }
  try{
   msg("Requesting actual libretro eject/select/insert transaction…");
   const result=await request("/api/disc_swap",{game_id:id,image_index:target});
   await load();
   msg(result.changed?"Native core changed disc; advance a frame to observe game response":
       "Native disc unchanged or worker rejected the swap; inspect lane status")
  }catch(error){msg("Native disc switch rejected: "+error.message);await load()}
 };
 controls.append(select,button);
 section.append(summary,controls);
 const discEvents=(lane.recent_native_events||[]).filter(x=>x.event_kind==="native_disc_swap");
 const details=document.createElement("details");
 details.append(txt("summary","Disc-change evidence · "+discEvents.length+" recent receipt(s)"));
 discEvents.forEach(event=>{
  const r=event.receipt;
  details.append(txt("div","Disc "+(r.previous_image_index+1)+" → "+(r.selected_image_index+1)+
     " · step "+r.episode_step+" · host "+r.native_host_disc_receipt_sha256.slice(0,12)+
     " · chain "+r.receipt_sha256.slice(0,12),"stats"))
 });
 section.append(details);
 section.append(txt("small","Only core-preloaded, hash-pinned media. No new files, automatic model learning or claimed console fidelity."));
 return section
}
function panel(side){
 const root=$(side),id=selected[side],lane=current.lanes[id];
 root.replaceChildren();
 const heading=txt("div","","inline");heading.append(txt("h2",side==="left"?"Game A":"Game B"));
 const sel=document.createElement("select");current.native_game_ids.forEach(k=>{
  const row=current.lanes[k];sel.append(choose(k,row.title+" · "+row.core_id))
 });sel.value=id;sel.onchange=()=>{selected[side]=sel.value;
  if(selected.left===selected.right){selected[side==="left"?"right":"left"]=
   current.native_game_ids.find(k=>k!==sel.value)}
  render()
 };heading.append(sel);root.append(heading);
 const stage=txt("div","","screen"),frame=lane.native_preview;
 if(frame?.image_data_uri){const img=document.createElement("img");img.src=frame.image_data_uri;
  img.alt="Actual isolated libretro frame from "+lane.title;stage.append(img)
 }else stage.append(txt("p",lane.status==="running"?"Actual frame exceeds bounded preview limit":lane.status,"subtle"));
 root.append(stage);
 root.append(deckFor(id));
 root.append(discDeckFor(id));
 root.append(nativeAudioMonitor(frame));
 const actions=txt("div","","inline"),doStep=txt("button","Advance native frame"),doReset=txt("button","Reset this emulator");
 doStep.disabled=lane.status!=="running"||lane.lifetime_steps>=lane.max_lifetime_steps;doReset.disabled=lane.status==="native_execution_failed"||lane.reset_count>=4;
 doStep.onclick=()=>step([id]);doReset.onclick=()=>resetGame(id);
 actions.append(doStep,doReset);root.append(actions);
 root.append(txt("p",lane.status+" · lifetime "+lane.lifetime_steps+"/"+lane.max_lifetime_steps+
    " native actions · reset "+lane.reset_count+"/4","stats"));
 root.append(txt("div","Frame SHA-256 "+(frame?.frame_sha256||"unavailable")+
    " · native evidence root "+lane.latest_event_chain_sha256,"stats"));
 root.append(graphFor(lane))
}
function render(){
 if(!current)return;
 activeAudioUrls.splice(0).forEach(url=>URL.revokeObjectURL(url));
 panel("left");panel("right")
}
$("all").onclick=()=>{if(!current)return;
 const repeat=Number($("repeat").value)||1;
 const ids=current.native_game_ids.filter(id=>current.lanes[id].status==="running"
    && current.lanes[id].lifetime_steps+repeat<=current.lanes[id].max_lifetime_steps);
 if(ids.length)step(ids);else msg("No active games can advance")
};
$("evidence").onclick=async()=>{try{
 const value=await request("/api/evidence");exportJSON(value.study_id+"_live_native_evidence",value);
 msg("Exported exact native receipts; no ROM bytes or model weights included")
 }catch(e){msg("Evidence export rejected: "+e.message)}
};
$("stop").onclick=async()=>{try{await request("/api/stop",{});msg("Local native emulator workers are shutting down");
 $("all").disabled=true;$("stop").disabled=true
 }catch(e){msg("Stop rejected: "+e.message)}
};
$("addnote").onclick=()=>{const value=$("note").value.trim();
 if(!value||value.length>1000){msg("A note must contain 1–1000 characters");return}
 notes.push({
  note_id:"live_viewer_"+String(notes.length+1),
  author:"viewer",game_ids:[selected.left,selected.right],
  checkpoint:$("checkpoint").value,dimension:$("dimension").value,
  claim_type:$("claim").value,text:value,review_status:"pending",build_parameter:null,
 });
 $("note").value="";$("notecount").textContent=notes.length+" local note(s)";
 msg("Locally drafted note linked to visible game IDs; export and review separately")
};
$("exportnotes").onclick=()=>{if(!current)return;
 exportJSON(current.study_id+"_live_notes",{schema_version:"skeleton.game.comparison_notes.v1",
  study_id:current.study_id,notes});msg("Viewer notes exported for separate governed review")
};
load().catch(e=>msg("Local native study is unavailable: "+e.message));
</script></body></html>"""
    return page.replace("__TOKEN__",token).replace("__NONCE__",nonce)
