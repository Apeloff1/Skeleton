"""Offline original quest-browser player script; never executes source scripts."""
DIRECTOR_CLIENT = r"""
"use strict";
const world=__WORLD__;
const sceneMap=Object.fromEntries(world.scenes.map(x=>[x.key,x]));
const get=id=>document.getElementById(id);
let state,stack=[],trace=[];
function fresh(){
 const stage={},started={};
 for(const q of world.quests){stage[q.key]=0;started[q.key]=0;}
 return {scene:world.starting_scene,turn:0,stage,started,completed:[],
  events:{},results:[],inventory:[],flags:[]};
}
function openQuests(){return world.quests.filter(q=>state.stage[q.key]<q.stages.length&&
 q.requires_quests.every(k=>state.completed.includes(k)));}
function allowed(){
 const current=sceneMap[state.scene],needed=new Set();
 for(const q of openQuests()){
  const phase=q.stages[state.stage[q.key]];
  if(!phase.scene_ids.includes(current.key))continue;
  for(const sol of phase.solutions)for(const p of sol.required)
   needed.add(p.kind+":"+p.target);
  for(const p of phase.optional)needed.add(p.kind+":"+p.target);
 }
 const out=current.links.map(key=>({kind:"travel",key,scene:current.key}));
 for(const a of current.affordances)if(needed.has(a.kind+":"+a.target)&&
   (!a.consumes||state.inventory.includes(a.consumes)))
   out.push({kind:"use",key:a.key,scene:current.key});
 return [...out,{kind:"wait",key:"wait",scene:current.key}];
}
function action(ev){
 if(!allowed().some(x=>x.kind===ev.kind&&x.key===ev.key&&x.scene===ev.scene))return;
 stack.push(JSON.parse(JSON.stringify(state)));trace.push(ev);
 if(ev.kind==="travel"){state.scene=ev.key;state.turn++;render();cinema("on_enter");return;}
 if(ev.kind==="wait"){state.turn++;render();return;}
 const a=sceneMap[state.scene].affordances.find(x=>x.key===ev.key);
 if(a.consumes)state.inventory.splice(state.inventory.indexOf(a.consumes),1);
 if(a.produces&&!state.inventory.includes(a.produces))state.inventory.push(a.produces);
 const time=state.turn+a.effort;
 for(const q of openQuests()){
  const idx=state.stage[q.key],phase=q.stages[idx];
  if(!phase.scene_ids.includes(state.scene))continue;
  const sign=a.kind+":"+a.target;
  if(![...phase.optional,...phase.solutions.flatMap(s=>s.required)]
   .some(p=>p.kind+":"+p.target===sign))continue;
  const record=q.key+"/"+phase.key+"/"+sign;
  state.events[record]=Math.min(100,(state.events[record]||0)+1);
  const valid=phase.solutions.filter(s=>s.required.every(p=>
    (state.events[q.key+"/"+phase.key+"/"+p.kind+":"+p.target]||0)>=p.count));
  if(!valid.length)continue;
  valid.sort((x,y)=>y.creativity-x.creativity||y.key.localeCompare(x.key));
  const win=valid[0],duration=Math.max(1,time-state.started[q.key]);
  const speed=Math.max(0,phase.time_target-duration)*3;
  const methods=new Set(Object.keys(state.events).filter(k=>
    k.startsWith(q.key+"/"+phase.key+"/")).map(k=>k.split("/")[2].split(":")[0]));
  const creative=win.creativity*2+Math.max(0,methods.size-1)*8;
  const bonus=15*phase.optional.filter(p=>(state.events[
    q.key+"/"+phase.key+"/"+p.kind+":"+p.target]||0)>=p.count).length;
  state.results.push({quest:q.key,stage:phase.key,approach:win.key,
   score:100+speed+creative+bonus,speed_bonus:speed,
   creativity_bonus:creative,optional_bonus:bonus,
   lore:q.narrative_cause+" "+phase.lore+" "+q.consequences+" Choice: "+win.key+"."});
  state.stage[q.key]=idx+1;state.started[q.key]=time;
  if(!state.flags.includes(win.outcome_flag))state.flags.push(win.outcome_flag);
  if(state.stage[q.key]===q.stages.length)state.completed.push(q.key);
  cinema("on_stage_complete");
 }
 state.turn=time;state.completed.sort();state.flags.sort();state.inventory.sort();
 render();
}
let timers=[];
function applyCinematicCue(cue){
 const stage=get("stage-screen"),subtitle=get("stage-subtitle");
 const actor=[...get("stage-cast").children].find(
  e=>e.dataset.actor===cue.target);
 if(cue.kind==="camera_zoom"||cue.kind==="camera_dolly"){
  stage.style.transform="scale(1.02)";
 }else if(cue.kind==="camera_pan"||cue.kind==="camera_track"){
  stage.style.transform="translateX(7px)";
 }else if(cue.kind==="camera_cut"){
  stage.style.transform="none";
 }else if(cue.kind==="lighting"||cue.kind==="color_grade"){
  stage.style.background=cue.value.includes("amber")?"#755836":
   cue.value.includes("blue")?"#2c467c":"#294a59";
 }else if(cue.kind==="actor_move"||cue.kind==="actor_enter"){
  if(actor){actor.style.transform="translateX(20px)";actor.style.opacity="1";}
 }else if(cue.kind==="actor_exit"){
  if(actor)actor.style.opacity="0";
 }else if(cue.kind==="actor_pose"||cue.kind==="actor_emote"||cue.kind==="animation"){
  if(actor)actor.style.transform="translateY(-10px)";
 }else if(cue.kind==="subtitle"||cue.kind==="dialogue"||cue.kind==="objective_reveal"){
  subtitle.textContent=cue.value;
 }else if(cue.kind==="fade"){
  stage.style.opacity=".65";
 }else if(cue.kind==="resume"){
  stage.style.opacity="1";
 }
}
function cinema(trigger){
 const cut=sceneMap[state.scene].cutscenes.find(x=>x.trigger===trigger);
 if(!cut)return;
 for(const t of timers)clearTimeout(t);timers=[];
 const pane=get("cinema");pane.hidden=false;
 get("cinema-title").textContent=cut.title;get("skip").disabled=!cut.skippable;
 get("cues").replaceChildren();
 for(const cue of cut.cues){
  const timer=setTimeout(()=>{
   const item=document.createElement("p");
   item.textContent=cue.kind+" — "+cue.target+": "+cue.value;
   get("cues").append(item);
   applyCinematicCue(cue);
  },cue.at);
  timers.push(timer);
 }
}
function drawChoices(){
 const area=get("actions");area.replaceChildren();
 const current=sceneMap[state.scene];
 for(const ev of allowed()){
  const button=document.createElement("button");button.type="button";
  if(ev.kind==="travel")button.textContent="Travel: "+sceneMap[ev.key].title;
  else if(ev.kind==="wait")button.textContent="Wait one turn";
  else{
   const a=current.affordances.find(x=>x.key===ev.key);
   button.textContent=a.kind+" "+a.target+" ("+a.effort+" turns)";
  }
  button.addEventListener("click",()=>action(ev));area.append(button);
 }
}
function render(){
 const scene=sceneMap[state.scene];
 const stage=get("stage-screen");
 stage.style.transform="none";stage.style.opacity="1";
 stage.style.background="#294a59";
 get("stage-subtitle").textContent=scene.setting;
 const cast=get("stage-cast");cast.replaceChildren();
 for(const npc of scene.cast){
  const actor=document.createElement("span");actor.textContent=npc;
  actor.dataset.actor=npc;cast.append(actor);
 }
 get("name").textContent=scene.title;
 get("set").textContent=scene.setting;
 get("visual").textContent="Camera "+scene.camera+" | Light "+scene.lighting+
  " | Weather "+scene.weather+" | Music "+scene.music;
 get("actors").textContent="Cast "+scene.cast.join(", ")+" | Props "+scene.props.join(", ");
 get("stats").textContent="Turn "+state.turn+" | Completed "+state.completed.length+
  "/"+world.quests.length+" | Score "+state.results.reduce((a,r)=>a+r.score,0);
 drawChoices();
 const q=get("quests");q.replaceChildren();
 for(const arc of openQuests()){
  const stage=arc.stages[state.stage[arc.key]];
  const block=document.createElement("article");
  block.textContent=arc.name+" / "+stage.title+" — "+stage.lore+
   " | Any method: "+stage.solutions.map(x=>x.required.map(p=>
     p.kind+" "+p.target+" x"+p.count).join(" AND ")).join(" OR ");
  q.append(block);
 }
 get("journal").textContent=[
  "MAIN STORY: "+world.bible.invariant_goal,
  "Canon: "+world.bible.canonical_facts.join(" | "),
  "Outcome principles: "+world.bible.ending_outcomes.join(" | "),
  "Decision flags: "+state.flags.join(", "),
  ...state.results.map(r=>r.lore+" Score "+r.score+
    " (speed "+r.speed_bonus+", creativity "+r.creativity_bonus+
    ", optional "+r.optional_bonus+")"),
 ].join("\n\n");
 get("undo").disabled=!stack.length;
}
function restart(){state=fresh();stack=[];trace=[];render();cinema("on_enter");}
get("undo").addEventListener("click",()=>{
 if(!stack.length)return;state=stack.pop();trace.pop();render();
});
get("restart").addEventListener("click",restart);
get("skip").addEventListener("click",()=>{
 if(get("skip").disabled)return;
 for(const t of timers)clearTimeout(t);timers=[];get("cinema").hidden=true;
});
get("download").addEventListener("click",()=>{
 const raw=JSON.stringify({schema:"skeleton.director.preview_actions.v1",
  world_digest:world.world_digest,actions:trace,
  warning:"Preview requires separate Python replay verification."},null,2);
 const url=URL.createObjectURL(new Blob([raw],{type:"application/json"}));
 const anchor=document.createElement("a");anchor.href=url;
 anchor.download="story-director-actions.json";document.body.append(anchor);
 anchor.click();anchor.remove();setTimeout(()=>URL.revokeObjectURL(url),0);
});
restart();
"""
