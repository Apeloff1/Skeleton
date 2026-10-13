"""Localhost scene/project studio visual controls for current, archive, demo trees.

Every edit is proposed first and explicitly committed second. Visual panes
never directly write to read-only previous or demo projects. Client requests
stay within a loopback server, with CSRF token and strict same-origin policy.
"""
STYLE=r"""
:root{color-scheme:dark;font:14px/1.5 system-ui;background:#0a1925;color:#eaf5f2}
*{box-sizing:border-box}body{margin:0}header{padding:1rem 1.5rem;background:#193d4d}
h1{margin:.1rem 0;font-size:1.5rem}h2{font-size:1.1rem;margin:0 0 .5rem}
main{display:grid;grid-template-columns:minmax(250px,1fr) minmax(280px,1.3fr) minmax(280px,1.7fr);gap:.8rem;padding:.8rem;min-height:86vh}
section{background:#142f40;border:1px solid #496d78;border-radius:.6rem;padding:1rem;min-width:0}
select,input,button,textarea{font:inherit;color:inherit;background:#21485b;border:1px solid #749da8;border-radius:.4rem;padding:.5rem;max-width:100%}
input,select,textarea{width:100%;min-height:42px}textarea{font-family:ui-monospace,monospace;font-size:13px;min-height:240px;resize:vertical}
button{cursor:pointer;min-height:40px;margin:.15rem}button:hover{background:#326478}
button:focus-visible,input:focus-visible,textarea:focus-visible{outline:2px solid #ffdb86}
button:disabled{opacity:.5;cursor:not-allowed}
label{display:block;margin:.5rem 0}fieldset{margin:.6rem 0;border:1px solid #537783;border-radius:.5rem}
small{color:#b9d0d3}.status{background:#254653;padding:.6rem;margin:.8rem 0;white-space:pre-wrap}
#files,#projects{display:grid;gap:.2rem;max-height:340px;overflow:auto}
#files button,#projects button{text-align:left;width:100%;margin:0;overflow-wrap:anywhere}
#files button[aria-current=true],#projects button[aria-current=true]{border:2px solid #ffd58a}
#diff{background:#0b2331;color:#d7f7df;white-space:pre-wrap;overflow:auto;max-height:270px;font:12px/1.5 ui-monospace,monospace}
#revision{font-family:ui-monospace,monospace}
.readonly{border:1px solid #dbbd88;padding:.7rem}
#system-fields{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:.4rem}
#system-fields label{margin:0}
#system-fields input[type=checkbox]{width:auto;min-height:auto}
#system-preview{max-height:170px;overflow:auto;white-space:pre-wrap;font:12px/1.4 ui-monospace,monospace}
#system-canvas,#advanced-canvas,#advanced-scene-grid{width:100%;max-width:500px;height:auto;border:1px solid #537783;
 background:#0b2331;border-radius:.4rem}
#advanced-actions{display:flex;flex-wrap:wrap;gap:.3rem}
#advanced-actions button{font-size:12px}
#advanced-state{font:12px/1.5 ui-monospace,monospace;white-space:pre-wrap;max-height:220px;overflow:auto}
#system-description{display:block;min-height:2.5rem}
@media(max-width:940px){main{grid-template-columns:1fr}section{min-height:0}}
"""
SCRIPT=r"""
"use strict";
const TOKEN=__TOKEN__;
const $=id=>document.getElementById(id);
let selectedTree="current",selectedProject=null,selectedFile=null,loaded=null,proposal=null;
let model=null;
async function api(route,data=null){
 const options={method:data===null?"GET":"POST",
  headers:{"X-Game-Studio-Token":TOKEN}};
 if(data!==null){options.headers["Content-Type"]="application/json";
  options.body=JSON.stringify(data);}
 const response=await fetch(route,options);
 const result=await response.json();
 if(!response.ok)throw Error(result.error||"Studio request failed");
 return result;
}
function status(message){$("status").textContent=message;}
function setOptions(id,values){
 const element=$(id);element.replaceChildren();
 for(const value of values){
  const option=document.createElement("option");option.value=value;
  option.textContent=value;element.append(option);
 }
}
function fileButtons(list){
 const target=$("files");target.replaceChildren();
 for(const file of list){
  const button=document.createElement("button");
  button.textContent=file.path+" · "+file.bytes+" B";
  button.type="button";button.setAttribute("aria-current",
    String(selectedFile===file.path));
  button.addEventListener("click",()=>openFile(file.path));
  target.append(button);
 }
}
async function refresh(){
 try{
  model=await api("/api/tree");
  $("active").textContent=model.active||"No active project";
  $("revision").textContent="Revision "+model.revision;
  let list=model[selectedTree]||[];
  const options=list.map(x=>x.ref);
  setOptions("project-choice",options);
  if(!selectedProject||!options.includes(selectedProject))selectedProject=options[0]||null;
  $("project-choice").value=selectedProject||"";
  await listFiles();
  await refreshModel();
  status("Local studio ready · previous/demo are immutable until forked");
 }catch(error){status(error.message);}
}
async function refreshModel(){
 try{
  const state=await api("/api/model-status");
  const rows=[
    "Reviewer: "+state.phase+" · revision "+state.revision,
    "Candidate staged: "+(state.candidate?"yes":"no"),
    "Active local advisory reviewer: "+(state.active?"yes":"no"),
    "Independent signoffs: "+state.signed_roles.join(", "),
    "Fresh usage games verified: "+(state.usage_checked?"yes":"pending"),
    "Independent idle games verified: "+(state.idle_checked?"yes":"pending"),
    "Source projects: "+(state.source_project_count||0),
    "Jeeves/Dragon neural weights unchanged",
  ];
  if(state.last_incident)rows.push("Last incident: "+state.last_incident);
  $("model-progress").textContent=rows.join("\\n");
 }catch(error){
  $("model-progress").textContent="Review registry unavailable: "+error.message;
 }
}
async function listFiles(){
 const target=$("files");target.replaceChildren();
 if(!selectedProject){selectedFile=null;loaded=null;return;}
 try{
  const response=await api("/api/files?tree="+encodeURIComponent(selectedTree)+
                      "&project="+encodeURIComponent(selectedProject));
  fileButtons(response.files);
  if(selectedFile&&response.files.some(f=>f.path===selectedFile))
    await openFile(selectedFile);
  else{selectedFile=null;loaded=null;$("editor").value="";$("file-name").textContent="Select a source file";}
  const edit=selectedTree==="current"&&selectedProject===model.active;
  $("propose").disabled=!edit;
  $("commit").disabled=true;
  $("readonly").textContent=edit?"Selected active current game: edits create reviewed proposals.":
   "Read-only historic/demo reference. Fork a previous genre to edit it.";
 }catch(error){status(error.message);}
}
async function openFile(path){
 selectedFile=path;proposal=null;
 try{
  loaded=await api("/api/file?tree="+encodeURIComponent(selectedTree)+
   "&project="+encodeURIComponent(selectedProject)+"&path="+encodeURIComponent(path));
  $("editor").value=loaded.content;
  $("file-name").textContent=selectedTree+"/"+selectedProject+"/"+path;
  $("hash").textContent="SHA-256 "+loaded.version.sha256;
  $("editor").readOnly=!loaded.version.editable;
  $("propose").disabled=!loaded.version.editable;
  $("commit").disabled=true;
  $("diff").textContent="Edit active source, then choose Review proposed edit.";
  status("Opened "+path+" · "+(loaded.version.editable?"editable with approval":"read only"));
 }catch(error){status(error.message);}
}
function diff(){
 if(!loaded)return;
 const before=loaded.content.split("\n");
 const after=$("editor").value.split("\n");
 const out=[];
 for(let i=0;i<Math.max(before.length,after.length);i++){
  if(before[i]===after[i])continue;
  if(i<before.length)out.push("- "+(i+1)+" "+before[i]);
  if(i<after.length)out.push("+ "+(i+1)+" "+after[i]);
  if(out.length>350){out.push("… diff preview truncated …");break;}
 }
 $("diff").textContent=out.length?out.join("\n"):"No change to this file.";
}
$("new-file").addEventListener("click",()=>{
 if(selectedTree!=="current"||selectedProject!==model.active){
  status("Only the active original project permits source creation.");return;
 }
 const path=$("new-path").value.trim();
 if(!path){status("Enter one exact path within the current project.");return;}
 selectedFile=path;proposal=null;
 const hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855";
 loaded={content:"",version:{tree:"current",project:selectedProject,
   path,sha256:hash,bytes:0,editable:true}};
 $("editor").value="";
 $("editor").readOnly=false;$("propose").disabled=false;
 $("file-name").textContent="NEW: current/"+selectedProject+"/"+path;
 $("hash").textContent="SHA-256 "+hash;
 $("diff").textContent="New source file: enter content, review, then commit.";
 status("New exact path staged without writing disk.");
});
$("plan").addEventListener("click",async()=>{
 try{
  if(!model.active)throw Error("Open or create a current original game");
  const result=await api("/api/plan",{project:model.active,
                                    prompt:$("user-prompt").value});
  const text="Axes: "+result.axes.map(x=>x.key).join(", ")+
   "\\nSuggested source targets:\\n"+result.files.map(x=>
    x.path+" · "+(x.exists?"existing":"new")+" · "+x.axis).join("\\n")+
   "\\n"+result.guidance.join("\\n");
  $("plan-results").textContent=text;
  $("reason").value="User prompt: "+$("user-prompt").value.slice(0,800);
  status("Prompt routing complete. This does not secretly run a model. "+
         "Choose a target and submit an explicit source proposal.");
 }catch(error){status("Prompt routing failed: "+error.message);}
});
$("editor").addEventListener("input",diff);
$("tree").addEventListener("change",()=>{
 selectedTree=$("tree").value;selectedProject=null;selectedFile=null;refresh();
});
$("project-choice").addEventListener("change",()=>{
 selectedProject=$("project-choice").value;selectedFile=null;listFiles();
});
$("refresh").addEventListener("click",refresh);
$("model-refresh").addEventListener("click",refreshModel);
$("propose").addEventListener("click",async()=>{
 if(!loaded||!loaded.version.editable)return;
 try{
  const request={project:selectedProject,path:selectedFile,
    content:$("editor").value,
    expected_sha256:loaded.version.sha256,
    reason:$("reason").value};
  proposal=await api("/api/propose",request);
  $("proposal").textContent=proposal.proposal_id;
  $("commit").disabled=false;
  status("Proposed change recorded. Review the diff and explicitly commit.");
 }catch(error){status("Proposal rejected: "+error.message);}
});
$("commit").addEventListener("click",async()=>{
 if(!proposal)return;
 try{
  const approved=$("approval").checked;
  if(!approved)throw Error("Check explicit human approval before committing");
  await api("/api/commit",{proposal_id:proposal.proposal_id,human_approved:true});
  status("Approved targeted file edit applied. Refetching exact file source.");
  $("approval").checked=false;proposal=null;
  await refresh();
 }catch(error){status("Commit blocked: "+error.message);}
});
$("create").addEventListener("click",async()=>{
 try{
  const project=$("new-project").value,genre=$("new-genre").value;
  await api("/api/create",{project,genre});
  selectedTree="current";$("tree").value=selectedTree;
  selectedProject=project;selectedFile=null;await refresh();
 }catch(error){status("New project blocked: "+error.message);}
});
$("archive").addEventListener("click",async()=>{
 try{
  if(!model.active)throw Error("Select current project");
  const result=await api("/api/archive",{project:model.active,demo:false});
  status("Archived immutable prior source: "+result.ref);
  await refresh();
 }catch(error){status("Archive blocked: "+error.message);}
});
$("demo").addEventListener("click",async()=>{
 try{
  if(!model.active)throw Error("Select current project");
  const result=await api("/api/archive",{project:model.active,demo:true});
  status("Original demo made: "+result.ref);
  await refresh();
 }catch(error){status("Demo blocked: "+error.message);}
});
$("autoload").addEventListener("click",async()=>{
 try{
  const result=await api("/api/autoload",{
    genre:$("load-genre").value,
    project:$("load-project").value});
  selectedTree="current";$("tree").value=selectedTree;
  selectedProject=result.active;selectedFile=null;await refresh();
  status("Previous genre safely forked as "+result.active);
 }catch(error){status("Autoload blocked: "+error.message);}
});
$("fork-demo").addEventListener("click",async()=>{
 try{
  const result=await api("/api/fork-demo",{
    reference:$("demo-ref").value,
    project:$("demo-target").value});
  selectedTree="current";$("tree").value="current";
  selectedProject=result.active;selectedFile=null;await refresh();
  status("Original demo forked to editable current game: "+result.active);
 }catch(error){status("Demo edit fork blocked: "+error.message);}
});
$("download").addEventListener("click",()=>{
 if(!loaded)return;
 const blob=new Blob([$("editor").value],{type:"text/plain;charset=utf-8"});
 const url=URL.createObjectURL(blob),a=document.createElement("a");
 a.href=url;a.download=selectedFile.split("/").pop();
 document.body.append(a);a.click();a.remove();
 setTimeout(()=>URL.revokeObjectURL(url),0);
});
// System editor family controls are generated from the locally verified
// catalog. No generic string-to-code evaluation or remote plugin execution.
let systemCatalog=[];
function systemEditor(){
 return systemCatalog.find(x=>x.id===$("system-kind").value);
}
function renderSystemControls(){
 const spec=systemEditor(),target=$("system-fields");target.replaceChildren();
 $("system-preview").textContent="";
 if(!spec)return;
 $("system-description").textContent=spec.description+
  (spec.runtime_maturity==="advanced_reference_runtime"?
    " · advanced playable reference engine":spec.preview?
    " · deterministic prototype only":" · authoring-only, runtime not integrated");
 for(const field of spec.fields){
  const label=document.createElement("label");label.textContent=field.key.replaceAll("_"," ");
  let element;
  if(field.kind==="enum"){
   element=document.createElement("select");
   for(const choice of field.options){
    const option=document.createElement("option");
    option.value=choice;option.textContent=choice;element.append(option);
   }
   element.value=field.default;
  }else{
   element=document.createElement("input");
   element.type=field.kind==="bool"?"checkbox":field.kind==="int"?"number":"text";
   if(field.kind==="bool")element.checked=field.default;
   else element.value=String(field.default);
   if(field.kind==="int"){
    element.min=field.minimum;element.max=field.maximum;element.step="1";
   }
  }
  element.dataset.systemField=field.key;
  element.dataset.systemKind=field.kind;
  label.append(element);target.append(label);
 }
}
function systemSettings(){
 const spec=systemEditor();
 if(!spec)throw Error("Choose a system-editor family");
 const values={};
 for(const field of spec.fields){
  const input=[...$("system-fields").querySelectorAll("[data-system-field]")]
   .find(x=>x.dataset.systemField===field.key);
  if(!input)throw Error("Missing system setting: "+field.key);
  if(field.kind==="bool")values[field.key]=input.checked;
  else if(field.kind==="int"){
   if(!/^-?[0-9]+$/.test(input.value))throw Error("Invalid integer: "+field.key);
   values[field.key]=Number(input.value);
  }else values[field.key]=input.value;
 }
 return values;
}
async function loadSystemEditors(){
 try{
  const reply=await api("/api/editors");systemCatalog=reply.editors;
  const select=$("system-kind");select.replaceChildren();
  const groups=[...new Set(systemCatalog.map(x=>x.group))];
  for(const group of groups){
   const optgroup=document.createElement("optgroup");optgroup.label=group;
   for(const spec of systemCatalog.filter(x=>x.group===group)){
    const option=document.createElement("option");option.value=spec.id;
    option.textContent=spec.title;optgroup.append(option);
   }
   select.append(optgroup);
  }
  select.value="platformer";renderSystemControls();drawSystemPreview(null);paintPalette();
  $("system-count").textContent=systemCatalog.length+" system editors ready";
 }catch(error){status("System editor catalog unavailable: "+error.message);}
}
// Offline canvas views reproduce validated backend evidence: they never
// become the authoritative simulation or a replacement for proof receipts.
function drawSystemPreview(report){
 const canvas=$("system-canvas"),c=canvas.getContext("2d");
 const w=canvas.width,h=canvas.height;
 c.fillStyle="#0b2331";c.fillRect(0,0,w,h);
 c.font="14px system-ui";c.fillStyle="#d5ecf0";
 if(!report||!report.simulation_executed){
  c.fillText("Choose Validate and simulate preview",14,28);return;
 }
 c.fillText(report.editor.replaceAll("_"," ").toUpperCase()+" · reference simulation",14,25);
 const state=report.state;
 if(report.editor==="platformer"){
  const points=state.trajectory;
  c.strokeStyle="#7fe4bd";c.lineWidth=3;c.beginPath();
  const maxX=Math.max(1,...points.map(x=>x.x));
  const maxY=Math.max(1,...points.map(x=>x.y));
  for(let i=0;i<points.length;i++){
   const x=30+points[i].x/maxX*(w-60), y=h-28-points[i].y/maxY*(h-82);
   if(i===0)c.moveTo(x,y);else c.lineTo(x,y);
  }
  c.stroke();c.fillText("Horizontal movement / jump arc",14,h-8);
 }else if(report.editor==="racing"){
  const points=state.telemetry,maxSpeed=Math.max(1,...points.map(x=>x.speed));
  c.strokeStyle="#f2c879";c.lineWidth=3;c.beginPath();
  for(let i=0;i<points.length;i++){
   const x=20+(i/(Math.max(1,points.length-1)))*(w-45);
   const y=h-35-(points[i].speed/maxSpeed)*(h-78);
   if(i===0)c.moveTo(x,y);else c.lineTo(x,y);
  }
  c.stroke();c.fillText("Speed / tick · "+state.distance+" units traversed",14,h-8);
 }else if(report.editor==="tactics"){
  const side=8,size=17,ox=25,oy=39;
  c.strokeStyle="#496d78";c.lineWidth=1;
  for(let i=0;i<=side;i++){
   c.beginPath();c.moveTo(ox+i*size,oy);c.lineTo(ox+i*size,oy+side*size);c.stroke();
   c.beginPath();c.moveTo(ox,oy+i*size);c.lineTo(ox+side*size,oy+i*size);c.stroke();
  }
  const px=Math.min(side-1,state.unit[0]),py=Math.min(side-1,state.unit[1]);
  c.fillStyle="#7fe4bd";c.fillRect(ox+px*size+3,oy+py*size+3,size-6,size-6);
  c.fillStyle="#d5ecf0";c.fillText("AP "+state.ap_remaining+" · enemy HP "+state.enemy_hp,195,75);
 }else{
  const metrics=Object.entries(state).filter(x=>typeof x[1]==="number" ||
   typeof x[1]==="boolean").slice(0,6);
  metrics.forEach((entry,i)=>{
   const y=48+i*27;
   c.fillStyle=i%2?"#f2c879":"#7fe4bd";
   c.fillRect(15,y-12,7,15);
   c.fillStyle="#d5ecf0";
   c.fillText(entry[0].replaceAll("_"," ")+": "+String(entry[1]),30,y);
  });
 }
}
$("system-kind").addEventListener("change",()=>{
 renderSystemControls();drawSystemPreview(null);paintPalette();
});
$("system-assembly").addEventListener("click",async()=>{
 try{
  if(!model||selectedTree!=="current"||selectedProject!==model.active)
   throw Error("Select the active current project for system composition");
  const result=await api("/api/editor-assembly?project="+
   encodeURIComponent(selectedProject));
  const lines=[
   "Assembly "+result.digest,
   "Reviewed systems: "+result.source_system_count,
   "Reference prototypes: "+result.prototype_evidence.length,
   "Cross-system contracts to integrate: "+result.coupling_edges.length,
   "Runtime adapters still required: "+result.unresolved_runtime_adapters.join(", "),
   "Composition release-ready: "+result.ready_for_release,
  ];
  $("system-preview").textContent=lines.join("\n");
  status("Reviewed authored-system assembly without writing any source.");
 }catch(error){status("System assembly rejected: "+error.message);}
});
$("system-try").addEventListener("click",async()=>{
 try{
  const result=await api("/api/editor-preview",{
   editor:systemEditor().id,settings:systemSettings()});
  $("system-preview").textContent=JSON.stringify(result.preview,null,2);
  drawSystemPreview(result.preview);
  status("Validated "+result.editor+" settings without writing files.");
 }catch(error){status("System preview blocked: "+error.message);}
});
$("system-stage").addEventListener("click",async()=>{
 try{
  if(!model||selectedTree!=="current"||selectedProject!==model.active)
   throw Error("Select the active current project before staging a system");
  const result=await api("/api/editor-preview",{
   editor:systemEditor().id,settings:systemSettings()});
  let prior={content:"",version:{
   tree:"current",project:selectedProject,path:result.path,
   sha256:"e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
   editable:true}};
  const list=await api("/api/files?tree=current&project="+encodeURIComponent(selectedProject));
  if(list.files.some(x=>x.path===result.path)){
   prior=await api("/api/file?tree=current&project="+
    encodeURIComponent(selectedProject)+"&path="+encodeURIComponent(result.path));
  }
  loaded=prior;selectedFile=result.path;proposal=null;
  $("editor").value=result.content;$("editor").readOnly=false;
  $("file-name").textContent="SYSTEM: current/"+selectedProject+"/"+result.path;
  $("hash").textContent="SHA-256 "+prior.version.sha256;
  $("reason").value="Configure original "+systemEditor().title+
    " system with reviewed typed authoring parameters";
  $("propose").disabled=false;$("commit").disabled=true;
  $("proposal").textContent="";
  $("system-preview").textContent=JSON.stringify(result.preview,null,2);
  drawSystemPreview(result.preview);
  diff();
  status("System staged in source review. Use Review proposed edit, inspect diff, then explicitly approve commit.");
 }catch(error){status("System staging rejected: "+error.message);}
});
// The advanced playable reference runs stateless server-side. No client state
// is trusted: every button submits the full transcript for independent replay.
let advancedCommands=[],advancedSession=null,advancedSettings=null,advancedEditor=null;
let advancedScene=null;
function drawAdvancedGame(session){
 const canvas=$("advanced-canvas"),c=canvas.getContext("2d");
 const W=canvas.width,H=canvas.height;
 c.fillStyle="#0b2331";c.fillRect(0,0,W,H);
 c.font="13px system-ui";c.fillStyle="#d8eef0";
 if(!session){c.fillText("Start an advanced playable reference scenario",12,25);return;}
 const state=session.state,editor=session.editor;
 c.fillText(editor.toUpperCase()+" · turn "+session.validated_turn_count+
  " · advanced floor",12,20);
 if(editor==="platformer"){
  const scale=(W-32)/Math.max(1,state.exit_x),floor=H-44;
  c.strokeStyle="#799da8";c.lineWidth=2;c.beginPath();
  c.moveTo(16,floor);c.lineTo(W-16,floor);c.stroke();
  for(const x of state.spikes){
   c.fillStyle="#ee827d";c.beginPath();c.moveTo(16+x*scale-5,floor);
   c.lineTo(16+x*scale,floor-13);c.lineTo(16+x*scale+5,floor);c.fill();
  }
  for(const x of state.collectibles){
   if(state.crystals.includes(x))continue;
   c.fillStyle="#f5da77";c.fillRect(16+x*scale-3,floor-27,6,8);
  }
  for(const x of state.checkpoints){
   c.fillStyle="#7ca4ee";c.fillRect(16+x*scale,floor-19,2,19);
  }
  c.fillStyle="#80ecc5";c.fillRect(12+state.x*scale,floor-22-Math.min(70,state.y),10,20);
  c.fillStyle="#d8eef0";c.fillText("HP "+state.health+
   " · crystals "+state.crystals.length+"/"+state.collectibles.length,15,H-9);
 }else if(editor==="tactics"){
  const dims=[Math.max(1,...state.enemies.map(x=>x.x+1),
    ...state.units.map(x=>x.x+1),state.objective[0]+1),
    Math.max(1,...state.enemies.map(x=>x.y+1),
    ...state.units.map(x=>x.y+1),state.objective[1]+1)];
  const size=Math.min(18,Math.floor((W-155)/dims[0]),Math.floor((H-60)/dims[1]));
  const ox=15,oy=34;
  c.strokeStyle="#4f7484";
  for(let x=0;x<=dims[0];x++){
   c.beginPath();c.moveTo(ox+x*size,oy);c.lineTo(ox+x*size,oy+dims[1]*size);c.stroke();
  }
  for(let y=0;y<=dims[1];y++){
   c.beginPath();c.moveTo(ox,oy+y*size);c.lineTo(ox+dims[0]*size,oy+y*size);c.stroke();
  }
  for(const [x,y] of state.obstacles){
   c.fillStyle="#728091";c.fillRect(ox+x*size+1,oy+y*size+1,size-2,size-2);
  }
  state.units.forEach((unit,index)=>{
   if(unit.hp===0)return;
   c.fillStyle=index===state.active_unit?"#70f1c7":"#66a4e2";
   c.fillRect(ox+unit.x*size+3,oy+unit.y*size+3,Math.max(2,size-6),Math.max(2,size-6));
  });
  for(const enemy of state.enemies){
   c.fillStyle="#f1997d";c.fillRect(ox+enemy.x*size+3,oy+enemy.y*size+3,
                                   Math.max(2,size-6),Math.max(2,size-6));
  }
  c.fillStyle="#d8eef0";c.fillText("Round "+state.round,Math.min(W-125,ox+dims[0]*size+14),55);
  c.fillText("AP "+state.action_points,Math.min(W-125,ox+dims[0]*size+14),76);
  c.fillText("Enemies "+state.enemies.length,Math.min(W-125,ox+dims[0]*size+14),97);
 }else if(editor==="tower_defense"){
  const y=H-85,scale=(W-40)/Math.max(1,state.lane_length);
  c.strokeStyle="#799da8";c.lineWidth=4;c.beginPath();c.moveTo(20,y);
  c.lineTo(W-20,y);c.stroke();
  for(const enemy of state.enemies){
   c.fillStyle=enemy.armor?"#faac80":"#ec797f";
   c.fillRect(20+enemy.x*scale,y-8,13,15);
  }
  for(const tower of state.towers){
   c.fillStyle=tower.level>1?"#eed27b":"#7be2c0";
   c.fillRect(20+(tower.slot*Math.max(1,Math.floor(state.lane_length/3))+2)*scale,
              y-38,12,30);
  }
  c.fillStyle="#d8eef0";c.fillText("Credits "+state.credits+" · Base "+state.base_hp,15,H-42);
  c.fillText("Defeated "+state.defeated+" · Escaped "+state.escaped,15,H-18);
 }else if(editor==="racing"){
  const progress=state.distance/(state.track_length*state.laps);
  c.fillStyle="#315569";c.fillRect(16,58,W-32,25);
  c.fillStyle="#77d7b5";c.fillRect(16,58,(W-32)*progress,25);
  c.fillStyle="#dceff0";c.fillText(
   "Lap "+state.lap+"/"+state.laps+" · "+state.weather+" circuit",16,46);
  c.fillText("Speed "+state.speed+" · lane "+state.lane,16,119);
  c.fillText("Fuel "+state.fuel+" · tires "+state.tire_condition,16,147);
  c.fillText("Engine "+state.engine_integrity+" · boosts "+state.boost_charges,16,175);
  c.fillText("Pit crews "+state.pit_crews+" · score "+state.championship_points,16,205);
 }else if(editor==="survival"){
  const region=state.regions[state.region];
  c.fillStyle="#78d6bd";c.fillText("Day "+state.day+" · "+
    region.biome+" · "+state.weather,16,50);
  const resources=[
   ["Health",state.health],["Energy",state.energy],
   ["Food",state.food],["Water",state.water],
   ["Wood",state.wood],["Stone",state.stone],
   ["Shelter",state.shelter_level],["Tools",state.tools],
  ];
  for(let i=0;i<resources.length;i++){
   const x=16+(i%2)*225,y=79+Math.floor(i/2)*34;
   c.fillStyle=i<2?"#92e4a7":"#e8cb82";
   c.fillRect(x,y-12,8,14);
   c.fillStyle="#e3edf1";
   c.fillText(resources[i][0]+": "+resources[i][1],x+16,y);
  }
  c.fillStyle="#e2edf0";c.fillText(
   "Milestones: "+(state.milestones.join(", ")||"open-ended"),16,H-18);
 }
 else if(editor==="shooter"){
  const tile=Math.min(14,Math.floor((W-140)/state.width),Math.floor((H-60)/state.height));
  const ox=12,oy=39;
  c.strokeStyle="#315869";c.lineWidth=1;
  for(let y=0;y<=state.height;y++){
   c.beginPath();c.moveTo(ox,oy+y*tile);
   c.lineTo(ox+state.width*tile,oy+y*tile);c.stroke();
  }
  for(let x=0;x<=state.width;x++){
   c.beginPath();c.moveTo(ox+x*tile,oy);
   c.lineTo(ox+x*tile,oy+state.height*tile);c.stroke();
  }
  function dot(point,color,margin=3){
   c.fillStyle=color;c.fillRect(ox+point[0]*tile+margin,
    oy+point[1]*tile+margin,Math.max(2,tile-margin*2),
    Math.max(2,tile-margin*2));
  }
  for(const point of state.cover)dot(point,"#607a8a",1);
  for(const point of state.pickups)dot(point,"#eccb79",4);
  for(const foe of state.enemies)dot(foe.pos,"#e9837d",2);
  dot(state.extraction,"#688ed9",3);dot(state.player,"#74e3b1",2);
  const left=Math.min(W-105,ox+state.width*tile+12);
  c.fillStyle="#deedf0";
  c.fillText("HP "+state.hp,left,55);
  c.fillText("Ammo "+state.ammo,left,77);
  c.fillText("Wave "+state.wave,left,99);
  c.fillText("Kills "+state.defeated,left,121);
  c.fillText("Dodge "+state.dashes,left,143);
 }else if(editor==="deck_battler"){
  c.fillStyle="#dbecef";c.fillText("Enemy HP "+state.enemy_hp+
     " / "+state.enemy_max_hp+"   Shield "+state.enemy_block,16,46);
  c.fillText("Player HP "+state.hp+"   Block "+state.block+
     "   Energy "+state.energy,16,68);
  c.fillText("Turn "+state.round+"   Intent "+state.enemy_intent+
     "   Poison "+state.poison,16,90);
  c.fillText("Draw "+state.draw_pile.length+"   Discard "+state.discard.length+
     "   Potions "+state.potions,16,112);
  state.hand.forEach((card,i)=>{
   const x=14+(i%5)*92;
   c.fillStyle="#294b61";c.fillRect(x,134,86,60);
   c.strokeStyle="#80b5ac";c.strokeRect(x,134,86,60);
   c.fillStyle="#e7eef0";c.fillText(card.slice(0,11),x+5,157);
   c.fillText("play:"+i,x+5,177);
  });
  c.fillStyle="#dbecef";
  c.fillText("Finite deck / active-hand rules",16,H-14);
 }else if(editor==="puzzle"){
  const t=Math.max(3,Math.min(17,Math.floor((W-24)/state.width),
     Math.floor((H-55)/state.height)));
  const ox=16,oy=36;
  c.strokeStyle="#3a6374";c.lineWidth=1;
  for(let x=0;x<=state.width;x++){
   c.beginPath();c.moveTo(ox+x*t,oy);c.lineTo(ox+x*t,oy+state.height*t);c.stroke();
  }
  for(let y=0;y<=state.height;y++){
   c.beginPath();c.moveTo(ox,oy+y*t);c.lineTo(ox+state.width*t,oy+y*t);c.stroke();
  }
  const block=(p,color)=>{
   c.fillStyle=color;
   c.fillRect(ox+p[0]*t+2,oy+p[1]*t+2,Math.max(1,t-4),Math.max(1,t-4));
  };
  state.walls.forEach(p=>block(p,"#637483"));
  state.doors.forEach(p=>block(p,"#c48178"));
  state.targets.forEach(p=>block(p,"#8dbbcb"));
  state.switches.forEach(p=>block(p,"#e9c57b"));
  state.nodes.forEach(p=>block(p,"#8bcee1"));
  state.phase_gates.forEach(p=>block(p,"#b6a1ec"));
  state.crates.forEach(p=>block(p,"#b58a65"));
  state.portals.forEach(pair=>pair.forEach(p=>block(p,"#a27ee6")));
  block(state.exit,"#73cda5");block(state.player,"#f5f3df");
  c.fillStyle="#dbecef";
  c.fillText(state.mode+"  ·  undo "+state.undo_available,16,H-12);
 }
 if(editor==="colony"){
  const pad=14;
  c.fillStyle="#d5e8e0";
  c.fillText("Day "+state.day+"  ·  Settlers "+state.population+
   "  ·  Injured "+state.injured+"  ·  Morale "+state.morale,16,42);
  c.fillStyle="#e8deb2";
  c.fillText("Food "+state.food+"  Water "+state.water+
   "  Wood "+state.wood+"  Stone "+state.stone+
   "  Credits "+state.credits,16,61);
  state.districts.forEach((sector,index)=>{
   const col=index%3,row=Math.floor(index/3),x=pad+col*149,y=74+row*66;
   c.fillStyle=index===state.district?"#205b65":"#294251";
   c.fillRect(x,y,142,61);
   c.fillStyle="#e6f0ec";c.fillText((index+1)+" · "+sector.biome,x+6,y+16);
   const stock=sector.wood+sector.stone+sector.food+sector.water;
   c.fillStyle="#b6e1ba";c.fillRect(x+6,y+24,Math.min(129,stock),5);
   c.fillStyle="#dce5ed";
   c.fillText("W"+sector.wood+" S"+sector.stone+" F"+sector.food+
    " H"+sector.water,x+6,y+45);
  });
  const names=Object.entries(state.workers).filter(([,count])=>count>0)
   .map(([name,count])=>name.slice(0,3)+":"+count).join("  ");
  c.fillStyle="#cae9e1";c.fillText("Jobs  "+(names||"unassigned"),16,213);
  c.fillStyle="#dfd7a5";
  c.fillText(state.milestones.length?
   state.milestones.join(" · ").slice(0,69):
   "No milestones yet · build, farm, defend, explore",16,232);
 }
 if(editor==="city_builder"){
  const shades={empty:"#35495a",road:"#89999d",bridge:"#aa9c82",
   residential:"#4cbb89",commercial:"#e2c77a",industry:"#c98e76",
   park:"#68a960",power:"#d0a5c3",waterworks:"#76accd",
   firehouse:"#d5776b",clinic:"#cee3db",school:"#a899d6"};
  const road=[...state.parcels].filter(p=>p.kind==="road"||p.kind==="bridge").length;
  c.fillStyle="#deefe9";c.fillText("Day "+state.day+" · population "+state.population+
    " · employed "+state.employment+" · happiness "+state.happiness,15,40);
  state.parcels.forEach(p=>{
   const x=16+(p.id%4)*52,y=56+Math.floor(p.id/4)*39;
   c.fillStyle=shades[p.kind]||"#465b6a";c.fillRect(x,y,48,35);
   c.fillStyle="#0d2630";c.fillText(String(p.id),x+5,y+14);
   c.fillStyle=p.kind==="empty"?"#d3dfdd":"#0b2028";
   c.fillText(p.kind.slice(0,7),x+4,y+28);
  });
  c.fillStyle="#cce8ed";c.fillText("Roads "+road+
    " · congestion "+state.congestion+" · pollution "+state.pollution,238,70);
  c.fillText("Treasury "+state.credits+" · debt "+state.debt,238,94);
  c.fillText("Power "+state.power_capacity+" · water "+state.water_capacity,238,118);
  c.fillText("Aquifer "+state.aquifer+" · wood "+state.wood+
   " · stone "+state.stone,238,142);
  c.fillText("Income policy: "+state.tax+" / "+state.policy,238,165);
  c.fillText(state.milestones.length?
    state.milestones.join(" · ").slice(0,40):"Build roads, zones and utilities",238,189);
  c.fillStyle="#e9d8aa";
  c.fillText("Select a parcel below, then issue a reviewed city command.",12,232);
 }

 if(editor==="stealth"){
  const ox=15,oy=36,cell=23;
  const mark=(p,color,label="")=>{
   c.fillStyle=color;c.fillRect(ox+p[0]*cell+1,oy+p[1]*cell+1,cell-2,cell-2);
   if(label){c.fillStyle="#071b28";c.fillText(label,ox+p[0]*cell+6,oy+p[1]*cell+17);}
  };
  c.fillStyle="#c5dedf";c.fillText("Original infiltration 10×8",15,32);
  for(let y=0;y<8;y++)for(let x=0;x<10;x++)
   mark([x,y],"#173e4e");
  for(const p of state.shadows)mark(p,"#2b4e66");
  for(const p of state.vents)mark(p,"#4f7282","v");
  for(const p of state.walls)mark(p,"#7d8592");
  for(const p of state.doors)mark(p,state.open_doors.some(q=>q[0]===p[0]&&q[1]===p[1])?"#7bb3b1":"#b46f63","D");
  for(const p of state.keycards)mark(p,"#e6cc80","K");
  for(const p of state.intel)mark(p,"#ad9bdd","I");
  for(const p of state.cameras)
   if(p.active)mark(p.position,"#d7a977","C");
  for(const g of state.guards)
   mark(g.position,g.disabled?"#869493":"#e58683",g.disabled?"z":"G");
  mark(state.terminal,"#8db8e6","T");
  mark(state.objective,state.archive?"#5e9882":"#d9bb79","A");
  mark(state.extraction,"#83c99e","E");
  mark(state.player,"#83ecc0","P");
  c.fillStyle="#ddede6";
  c.fillText("HP "+state.hp+"/"+state.max_hp+" · alarm "+state.alarm+
    " · stamina "+state.stamina,253,59);
  c.fillText("Cards "+state.keycards_owned+" · hack "+state.hacking,253,83);
  c.fillText("Stuns "+state.stun_charges+" · smoke "+state.smoke_charges+
    " · EMP "+state.emp_charges,253,107);
  c.fillText("Guards "+state.guards.length+" · cameras "+
    state.cameras.filter(x=>x.active).length,253,131);
  c.fillText("Archive "+(state.archive?"secured":"pending")+
    " · intel "+state.intel_collected,253,155);
  c.fillText("Patrols use real rays, hearing and cover.",253,179);
  c.fillText("Score "+state.score+" · extracted "+state.extracted,253,203);
  c.fillText("No player-issued teleport or hidden native execution.",15,247);
 }
 if(editor==="metroidvania"){
  const rooms=state.rooms,region=state.region;
  const n=rooms.length,ox=14,oy=37;
  const xy=i=>[ox+(i%6)*48,oy+Math.floor(i/6)*43];
  c.strokeStyle="#637f90";c.lineWidth=2;
  for(const p of state.passages){
   const [x,y]=xy(p.a),[xx,yy]=xy(p.b);
   c.strokeStyle=p.gate&&!state.abilities.includes(p.gate)?"#cb8978":"#73b1a2";
   c.beginPath();c.moveTo(x+19,y+14);c.lineTo(xx+19,yy+14);c.stroke();
  }
  for(const r of rooms){
   const [x,y]=xy(r.id);
   c.fillStyle=r.id===region?"#e0c67c":r.visited?"#4ea989":"#29495c";
   c.fillRect(x,y,38,29);
   c.fillStyle=r.id===region?"#112935":"#edf7f3";
   c.fillText(String(r.id),x+5,y+14);
   if(r.ability&&!r.claimed){
    c.fillStyle="#a8d8f5";c.fillText("*",x+22,y+14);
   }
   if(r.foe>0){c.fillStyle="#f29c93";c.fillRect(x+4,y+21,25,3);}
  }
  const room=rooms[region];
  c.fillStyle="#e1ebe7";
  c.fillText("World "+rooms.length+" rooms · in "+room.biome+
    " / "+region,313,43);
  c.fillText("HP "+state.health+" · stamina "+state.stamina,313,69);
  c.fillText("Enemy "+room.foe+" · boss "+state.guardian_hp,313,95);
  c.fillText("Abilities "+state.abilities.join(",").slice(0,17),313,120);
  c.fillText("Shards "+state.shards+" · tonics "+state.tonics,313,145);
  c.fillText("Explored "+state.visited.length+"/"+rooms.length,313,170);
  c.fillText("Secrets "+state.secrets_found+
    " · breaks "+state.sequence_breaks,313,195);
  c.fillText(state.boss_defeated?"Guardian defeated; world persists":
   "Route locks demand earned abilities",12,236);
 }
 if(editor==="sandbox"){
  const tiles=state.regions[String(state.region)]||[];
  const terrainInk={grass:"#3c6e57",forest:"#2b8657",
   ridge:"#8a816c",sand:"#c6ad77",marsh:"#367884",lake:"#337cc6"};
  const glyph={house:"H",road:"r",bridge:"=",farm:"F",well:"W",
   workshop:"T",kiln:"K",fence:"f",beacon:"B",generator:"G",storehouse:"S"};
  c.fillStyle="#e6f0df";
  c.fillText("Original streamed sandbox · region "+state.region+
    " / "+state.visited_regions.length+" visited",12,31);
  for(const t of tiles){
   const x=12+(t.id%8)*27,y=37+Math.floor(t.id/8)*24;
   c.fillStyle=terrainInk[t.terrain]||"#516b6e";
   c.fillRect(x,y,25,22);
   c.fillStyle="#f7f5dc";
   if(t.building)c.fillText(glyph[t.building]||"?",x+6,y+16);
   else if(t.animal)c.fillText(t.tamed?"a":"w",x+7,y+15);
   else if(t.sapling)c.fillText("s",x+8,y+15);
   else if(t.crop)c.fillText(String(t.crop),x+8,y+16);
   if(t.fire){
    c.fillStyle="#fc9c4c";c.fillRect(x+19,y+1,4,5);
   }
  }
  const px=12+(state.position%8)*27;
  const py=37+Math.floor(state.position/8)*24;
  c.strokeStyle="#ffffcc";c.lineWidth=3;c.strokeRect(px,py,25,22);
  const cols=247;
  c.fillStyle="#e1ebe7";
  c.fillText("Day "+state.day+" · weather "+state.weather,cols,43);
  c.fillText("HP "+state.health+" · energy "+state.energy,cols,65);
  c.fillText("Food "+state.inventory.food+" · water "+state.inventory.water,cols,87);
  c.fillText("Wood "+state.inventory.wood+" · stone "+state.inventory.stone,cols,109);
  c.fillText("Ore "+state.inventory.ore+" · tools "+state.inventory.tool,cols,131);
  c.fillText("Credits "+state.credits+" · power "+state.power,cols,153);
  c.fillText("Settlers "+state.settlers.length+" · housing "+state.houses,cols,175);
  c.fillText("Seasons "+state.season+" · achievement "+
   state.achievements.length,cols,197);
  c.fillText("NPC witnesses "+state.observations.length+" · open quests "+
   state.quests.filter(q=>q.status==="open").length,cols,219);
  c.fillStyle="#a6dcc0";
  c.fillText("Draw / play only in source-validated original cells.",12,247);
 }
 if(editor==="roguelike"){
  const map=state.map,ink={floor:"#294a5b",wall:"#79858c"};
  c.fillStyle="#d9e9e8";
  c.fillText("Original procedural dungeon floor "+state.floor+
    " / "+(advancedSettings?.floors??"?"),12,34);
  for(let i=0;i<36;i++){
   const x=14+(i%6)*34,y=41+Math.floor(i/6)*32;
   c.fillStyle=ink[map.terrain[i]]||"#35586b";
   c.fillRect(x,y,32,30);
   let glyph="";
   if(i===map.exit)glyph="E";
   else if(i===map.shop)glyph="$";
   else if(i===map.shrine)glyph="S";
   else if(map.chests.includes(i)&&!state.chests_opened.includes(i))glyph="C";
   else if(map.traps.includes(i)&&!state.traps_disarmed.includes(i))glyph="!";
   const foe=map.enemies.find(e=>e.cell===i&&e.hp>0);
   if(foe){glyph=foe.is_boss?"B":"G";c.fillStyle="#c36a62";}
   if(i===state.player){glyph="P";c.fillStyle="#73bea0";}
   if(glyph){c.fillText(glyph,x+10,y+21);}
  }
  const tx=238;c.fillStyle="#e0ebe7";
  c.fillText("HP "+state.hp+"/"+state.max_hp+" · poison "+state.poison,tx,50);
  c.fillText("Mana "+state.mana+" · stamina "+state.stamina,tx,74);
  c.fillText("Attack "+state.attack+" · armor "+state.armor,tx,98);
  c.fillText("Gold "+state.gold+" · relics "+state.relics,tx,122);
  c.fillText("Arrows "+state.arrows+" · potions "+state.potions,tx,146);
  c.fillText("Key "+state.floor_key+" · lockpicks "+state.lockpicks,tx,170);
  c.fillText("Enemies "+map.enemies.filter(e=>e.hp>0).length+
    " · reserve "+map.reserve,tx,194);
  c.fillText("Loot "+state.treasure+" · score "+state.score,tx,218);
  c.fillText("A signed source map governs every room and reward.",12,249);
 }
 if(editor==="rts"){
  const map=state.map;
  const seen=new Set(state.visible),known=new Set(state.discovered);
  c.fillStyle="#dcece4";
  c.fillText("Original strategy · tick "+state.tick+" · "+
    map.environment,12,35);
  const terrain={};
  for(let i=0;i<64;i++){
   const x=14+(i%8)*26,y=43+Math.floor(i/8)*25;
   c.fillStyle=map.obstacles.includes(i)?"#747b7b":
    !known.has(i)?"#112b34":!seen.has(i)?"#294753":"#406f60";
   c.fillRect(x,y,24,23);
   let marker="";
   if(seen.has(i)||!advancedSettings?.fog_of_war){
    const deposit=map.nodes.find(n=>n.cell===i&&n.stock>0);
    if(deposit)marker=deposit.type==="wood"?"W":deposit.type==="ore"?"O":"E";
    const building=state.buildings.find(b=>b.cell===i&&b.hp>0);
    if(building)marker=building.side==="blue"?"B":"X";
    const enemy=state.enemies.find(u=>u.cell===i&&u.hp>0);
    if(enemy)marker="R";
   }
   const ally=state.units.find(u=>u.cell===i&&u.hp>0);
   if(ally)marker=ally.kind==="worker"?"w":"U";
   if(i===map.relay&&seen.has(i)&&!ally)marker="C";
   if(marker){
    c.fillStyle=marker==="R"?"#ffaaa7":marker==="X"?"#f9b9a8":"#f3f5d3";
    c.fillText(marker,x+7,y+16);
   }
   if(ally&&ally.id===state.selected){
    c.strokeStyle="#fbd875";c.lineWidth=2;c.strokeRect(x+1,y+1,22,21);
   }
  }
  const tx=237;c.fillStyle="#e1ebe7";
  c.fillText("Wood "+state.wood+" · ore "+state.ore,tx,51);
  c.fillText("Energy "+state.energy+" · supply "+state.supply_used,tx,75);
  c.fillText("Units "+state.units.filter(u=>u.hp>0).length+
   " · opposing "+state.enemies.filter(u=>u.hp>0&&seen.has(u.cell)).length,tx,99);
  c.fillText("Selected unit #"+state.selected,tx,123);
  c.fillText("Relay "+state.relay_owner+" · "+state.relay_progress,tx,147);
  c.fillText("Relay hold "+state.relay_hold,tx,171);
  c.fillText("Map visibility "+state.visible.length+"/64",tx,195);
  c.fillText("Enemy HQ "+state.buildings.find(b=>b.side==="red").hp+
   " · waves "+state.wave_index,tx,219);
  c.fillStyle="#a3d8c2";
  c.fillText("All movement, mining and conquest uses real map cells",12,252);
 }
 if(editor==="rhythm"){
  const chart=state.chart,notes=chart.notes,clock=state.clock_ms;
  const laneCount=chart.lanes,ox=14,oy=44,lw=28;
  c.fillStyle="#e2f0eb";
  c.fillText("Original synthesized rhythm chart · "+chart.bpm+" BPM · "+
     chart.meter+"/4",12,33);
  for(let j=0;j<laneCount;j++){
   c.fillStyle=j%2?"#304d60":"#23435a";
   c.fillRect(ox+j*lw,oy,lw-2,185);
   c.fillStyle="#f2ede0";c.fillText(String(j+1),ox+j*lw+8,oy+178);
  }
  c.strokeStyle="#fee09c";c.lineWidth=3;c.beginPath();
  c.moveTo(ox,oy+151);c.lineTo(ox+laneCount*lw,oy+151);c.stroke();
  for(const n of notes){
   if(state.judgements[n.id]!==null)continue;
   const t=n.at+chart.offset_ms-clock;
   if(t< -200||t>1500)continue;
   const y=oy+151-t/9;
   if(y<oy||y>oy+185)continue;
   const x=ox+n.lane*lw;
   c.fillStyle=n.kind==="mine"?"#f88a81":
    n.kind==="hold"?"#bba6f2":
    n.kind==="slide"?"#9cddec":
    n.kind==="chord"?"#e3c985":"#80e9b7";
   c.fillRect(x+4,y-4,20,8);
   if(n.kind==="chord"&&n.partner!==null)
    c.fillRect(ox+n.partner*lw+4,y-4,20,8);
   if(n.kind==="hold")c.fillRect(x+10,y-n.duration/9,8,n.duration/9);
  }
  c.fillStyle="#edf2e8";const tx=205;
  c.fillText("Clock "+clock+"ms · beat "+chart.beats,tx,48);
  c.fillText("Score "+state.score+" · combo "+state.combo,tx,72);
  c.fillText("Perfect "+state.perfect+" · great "+state.great,tx,96);
  c.fillText("Good "+state.good+" · missed "+state.miss,tx,120);
  c.fillText("HP "+state.health+" · stray "+state.stray,tx,144);
  c.fillText("Mines "+state.mines_avoided+"/"+state.mines_hit,tx,168);
  c.fillText("Progress "+state.judgements.filter(v=>v!==null).length+
    "/"+notes.length,tx,192);
  c.fillText("Held "+state.held.length+" · rank "+state.rank,tx,216);
  c.fillText("Game time advances only via verified wait actions.",12,254);
 }
 if(editor==="fighting"){
  const arena=state.arena,ox=12,oy=48,cell=19,laneH=53;
  c.fillStyle="#e4efe4";
  c.fillText("Original frame-bounded arena · round "+state.round+
    " · frame "+state.clock_frames,12,35);
  for(let y=0;y<arena.lanes;y++){
   for(let x=0;x<arena.width;x++){
    c.fillStyle=y%2?"#345b5b":"#28434e";
    c.fillRect(ox+x*cell,oy+y*laneH,cell-2,laneH-3);
    const hazard=arena.hazards.find(h=>h.x===x&&h.lane===y);
    if(hazard){c.fillStyle="#d17f61";c.fillRect(ox+x*cell,oy+y*laneH+40,cell-2,8);}
    const cover=arena.cover.find(v=>v.x===x&&v.lane===y&&v.hp>0);
    if(cover){c.fillStyle="#a5a9aa";c.fillRect(ox+x*cell+3,oy+y*laneH+12,12,25);}
   }
  }
  for(const fighter of [state.opponent,state.player]){
   const x=ox+fighter.x*cell,y=oy+fighter.lane*laneH;
   c.fillStyle=fighter.side==="blue"?"#96f3c0":"#ffc0a9";
   c.fillRect(x+2,y+8,13,32);
   c.fillStyle="#122631";
   c.fillText(fighter.side==="blue"?"P":"A",x+4,y+28);
   if(fighter.airborne){c.fillStyle="#f2e78d";c.fillText("↑",x+3,y+7);}
   if(fighter.parry){c.strokeStyle="#fbe5a1";c.strokeRect(x,y+5,17,38);}
  }
  c.fillStyle="#eef0dd";const px=328;
  c.fillText("Player HP "+state.player.hp+"/"+state.player.max_hp,px,55);
  c.fillText("Enemy HP "+state.opponent.hp+"/"+state.opponent.max_hp,px,79);
  c.fillText("Stamina "+state.player.stamina,px,103);
  c.fillText("Special "+state.player.meter,px,127);
  c.fillText("Guard "+state.player.guard,px,151);
  c.fillText("Combo "+state.player.combo+" · stun "+state.player.stun,px,175);
  c.fillText("Rounds "+state.blue_rounds+" — "+state.red_rounds,px,199);
  c.fillText("Ringouts "+state.ringouts+" · turns "+state.turn,px,223);
  c.fillStyle="#a9dccc";
  c.fillText("Original sprites are drawn primitives; collision and judging are backend-owned.",12,258);
 }
 if(editor==="quest_director"){
  const ox=14,oy=47,cell=25;
  c.fillStyle="#dbece5";
  c.fillText("Original witnessed causal world · day "+state.day+
       " · tick "+state.tick,12,35);
  for(let i=0;i<49;i++){
   const x=ox+(i%7)*cell,y=oy+Math.floor(i/7)*27;
   c.fillStyle=state.world.obstacles.includes(i)?"#67767c":
      selectedQuestCell===i?"#4e7770":"#315a59";
   c.fillRect(x,y,23,25);
   let token="";
   const site=state.sites.find(s=>s.cell===i);
   const npc=state.npcs.find(n=>n.cell===i);
   if(site)token=site.kind==="settlement"?"S":site.kind==="bridge"?"B":
             site.kind==="grove"?"G":"A";
   if(npc)token=npc.memories.length?"!":npc.investigations?.length?"F":npc.heard.length?"?":"N";
   if(state.player===i)token="P";
   if(token){
    c.fillStyle=token==="P"?"#ffde98":token==="!"?"#a0f5c1":"#e2dfe2";
    c.fillText(token,x+6,y+18);
   }
  }
  c.fillStyle="#e4ede6";
  const tx=215;
  c.fillText("Reputation "+state.reputation+" · gold "+state.gold,tx,58);
  c.fillText("Supplies "+state.supplies+" · stamina "+state.stamina,tx,82);
  c.fillText("Direct events "+state.events_log.length,tx,106);
  c.fillText("Corroborated quests "+state.quests.length,tx,130);
  c.fillText("Resolved "+state.quests_completed+
     " · exploited "+state.quests_exploited,tx,154);
  c.fillText("Rumors "+state.rumor_edges.length+" · forensics "+state.forensic_edges.length,tx,178);
  c.fillText("Player "+state.player+" · NPC walks "+state.npc_walks,tx,202);
  const active=state.quests.find(q=>q.status==="active");
  if(active)c.fillText("Quest #"+active.id+" · "+
    (active.choice||"uncommitted")+
    " · evidence "+active.testimonies.length,tx,225);
  c.fillStyle="#a7dcc6";
  c.fillText("Witness (!) / forensic (F) / rumor (?) differ · original player P",12,256);
 }
 if(editor==="physics"){
  const sx=17,sy=44,scale=Math.min(19,282/Math.max(1,state.width-1)),
       renderHeight=Math.max(2,(state.floor_y)*scale);
  c.fillStyle="#dbeae5";
  c.fillText("Original fixed-point bodies · "+(state.depth>1?"3D slices":"2D")+" · frame "+state.frame,12,36);
  c.fillStyle="#1c4250";c.fillRect(sx,sy,scale*(state.width-1),renderHeight);
  c.strokeStyle="#3c6670";c.lineWidth=1;
  for(let x=0;x<state.width;x++){
   c.beginPath();c.moveTo(sx+x*scale,sy);
   c.lineTo(sx+x*scale,sy+renderHeight);c.stroke();
  }
  for(let y=0;y<=state.floor_y;y++){
   c.beginPath();c.moveTo(sx,sy+y*scale);
   c.lineTo(sx+scale*(state.width-1),sy+y*scale);c.stroke();
  }
  c.fillStyle="#bba078";
  c.fillRect(sx,sy+renderHeight,scale*(state.width-1),4);
  if(state.water_y<=state.floor_y){
   c.fillStyle="#2d7c9b55";
   c.fillRect(sx,sy+state.water_y*scale,scale*(state.width-1),
              Math.max(0,(state.floor_y-state.water_y)*scale));
  }
  for(const fixture of state.fixtures){
   c.fillStyle="#6a777c";
   const p=fixture.position,h=fixture.half_size;
   c.save();c.translate(sx+p[0]/100*scale,sy+p[1]/100*scale);
   c.rotate((fixture.orientation||0)*Math.PI/180000);
   c.fillRect(-h[0]/100*scale,-h[1]/100*scale,
              h[0]/50*scale,h[1]/50*scale);
   c.restore();
  }
  for(const [i,anchor] of state.anchors.entries()){
   c.fillStyle="#ecce8d";c.fillRect(sx+anchor[0]/100*scale-3,
              sy+anchor[1]/100*scale-3,6,6);
  }
  const goalX=sx+state.goal[0]/100*scale,goalY=sy+state.goal[1]/100*scale;
  c.strokeStyle="#80d6a1";c.lineWidth=2;c.strokeRect(goalX-7,goalY-7,14,14);
  if(state.rope){
   const selected=state.bodies.find(b=>b.id===state.rope.body);
   if(selected){const end=state.anchors[state.rope.anchor];
    c.strokeStyle="#ecd6a2";c.beginPath();
    c.moveTo(sx+end[0]/100*scale,sy+end[1]/100*scale);
    c.lineTo(sx+selected.position[0]/100*scale,
             sy+selected.position[1]/100*scale);c.stroke();}
  }
  for(const [index,body] of state.bodies.entries()){
   const bx=sx+body.position[0]/100*scale,
         by=sy+body.position[1]/100*scale;
   c.fillStyle=body.broken?"#925969":
      index===state.selected?"#fff1c5":
      body.material==="metal"?"#b9c7d8":
      body.material==="glass"?"#93d6d4":"#a5c68a";
   if(state.geometry_mode==="oriented_box"){
    const theta=body.orientation*Math.PI/180000,
          xRadius=body.shape_half[0]/100*scale,
          yRadius=body.shape_half[1]/100*scale;
    c.save();c.translate(bx,by);c.rotate(theta);
    c.fillRect(-xRadius,-yRadius,2*xRadius,2*yRadius);
    c.restore();
   }else{
    c.beginPath();c.arc(bx,by,Math.max(3,body.radius/100*scale),
                        0,Math.PI*2);c.fill();
   }
   // Orientation comes from source-replayed angular state, not client drag.
   const arm=Math.max(3,body.radius/100*scale);
   const angle=body.orientation*Math.PI/180000;
   c.strokeStyle=body.broken?"#eed0d0":"#263f54";
   c.lineWidth=2;c.beginPath();c.moveTo(bx,by);
   c.lineTo(bx+Math.cos(angle)*arm,by+Math.sin(angle)*arm);c.stroke();
   if(state.depth>1){
    c.fillStyle="#f1e1ac";c.font="9px monospace";
    c.fillText(String(body.position[2]/100),bx-5,by-8);}
  }
  const tx=Math.min(345,sx+scale*(state.width-1)+12);
  c.font="10px monospace";c.fillStyle="#d6e5e9";
  [
   "Contact: "+state.contacts,
   "Battery: "+state.battery,
   "Impulses: "+state.impulses_left,
   "Motors: "+state.motors_used,
   "Ropes: "+state.rope_breaks,
   "Fractures: "+state.fractures,
   "Selected: "+state.selected,
   "Goal dwell: "+state.goal_frames,
   "Max speed: "+state.max_velocity_seen,
   "Pair CCD: "+state.continuous_pair_contacts,
   "Angular: "+state.max_angular_speed_seen,
   "Cable ext: "+state.peak_cable_extension,
   "SAT hits: "+state.oriented_contacts,
   "Sweep hits: "+state.rotating_swept_contacts,
   "Broadphase: "+(state.broadphase_pairs+state.broadphase_fixtures),
   "Pruned: "+state.broadphase_pruned,
   "SAT probes: "+state.oriented_sat_evaluations,
   "Asleep: "+state.sleeping_bodies
  ].forEach((line,i)=>c.fillText(line,tx,47+i*14));
 }
 if(editor==="flight"){
  const ox=15,trackY=83,trackW=W-188,trackH=154;
  const extent=Math.max(state.runway_end,1);
  c.fillStyle="#c9e6f2";
  c.fillText(state.title+" · "+state.weather+" · "+String(state.tick)+" steps",12,36);
  c.fillStyle="#345568";c.fillRect(ox,trackY,trackW,trackH);
  for(const ridge of state.ridges){
   const x=ox+ridge.x/extent*trackW;
   const height=Math.min(trackH-12,ridge.altitude/Math.max(1,state.altitude+90)*trackH);
   c.fillStyle="#d6a67d";c.fillRect(x-4,trackY+trackH-height,8,height);
  }
  for(const b of state.beacons){
   const x=ox+b.x/extent*trackW;
   c.strokeStyle=state.beacons_seen.includes(b.x)?"#79e0b9":
      state.beacons_missed.includes(b.x)?"#e9978e":"#e4d68a";
   c.setLineDash([3,4]);c.beginPath();c.moveTo(x,trackY+5);
   c.lineTo(x,trackY+trackH-2);c.stroke();c.setLineDash([]);
  }
  const runwayX=ox+state.runway_start/extent*trackW;
  c.fillStyle="#8ca8a8";
  c.fillRect(runwayX,trackY+trackH-7,Math.max(3,trackW-(runwayX-ox)),7);
  const ax=ox+Math.min(extent+2,state.x)/extent*trackW;
  const ay=trackY+trackH-14-Math.min(trackH-24,
    state.altitude/Math.max(1,250)*trackH);
  c.fillStyle="#a6f1d2";
  c.beginPath();c.moveTo(ax+10,ay);c.lineTo(ax-9,ay-6);
  c.lineTo(ax-7,ay+6);c.closePath();c.fill();
  c.fillStyle="#eaf7ef";const tx=W-157;
  c.fillText("Speed "+state.speed,tx,68);
  c.fillText("Altitude "+state.altitude,tx,91);
  c.fillText("Fuel "+state.fuel,tx,114);
  c.fillText("Hull "+state.hull,tx,137);
  c.fillText("Heat "+state.temperature,tx,160);
  c.fillText("Wind "+state.wind_direction,tx,183);
  c.fillText("NAV "+state.beacons_seen.length+"/"+state.beacons.length,tx,206);
  c.fillText("Gear "+(state.gear?"DOWN":"UP"),tx,229);
  c.fillStyle="#a6e9ce";
  c.fillText("Arcade / simcade / simulation · full replay-owned physics",12,265);
 }
 if(editor==="sailing"){
  const ox=17,trackY=75,trackW=W-177,trackH=157;
  const extent=Math.max(1,state.harbor_end);
  c.fillStyle="#d0e9ef";
  c.fillText(state.title+" · "+state.sea+" · day tick "+String(state.tick),12,36);
  c.fillStyle="#255368";c.fillRect(ox,trackY,trackW,trackH);
  const shoreX=ox+state.harbor_start/extent*trackW;
  c.fillStyle="#bdb498";c.fillRect(shoreX,trackY,trackW-(shoreX-ox),trackH);
  for(const mark of state.buoys){
   const x=ox+mark/extent*trackW;
   c.fillStyle=state.buoys_seen.includes(mark)?"#8ef0c4":"#f1d187";
   c.fillRect(x-2,trackY+13,4,trackH-26);
  }
  for(const shoal of state.shoals){
   const x=ox+shoal.x/extent*trackW;
   const y=trackY+trackH/2+shoal.lane*17;
   c.fillStyle="#d79e75";c.fillRect(x-4,y-3,8,7);
  }
  const sx=ox+Math.min(extent+2,state.x)/extent*trackW;
  const sy=trackY+trackH/2+state.lane*17;
  c.fillStyle="#d5f4e4";c.fillRect(sx-9,sy-3,18,10);
  if(state.sails){c.fillStyle="#f9e3ab";c.beginPath();
   c.moveTo(sx,sy-25);c.lineTo(sx,sy-4);c.lineTo(sx+12,sy-4);c.fill();}
  c.fillStyle="#eaf7ef";const tx=W-155;
  c.fillText("Speed "+state.speed,tx,66);
  c.fillText("Hull "+state.hull,tx,90);
  c.fillText("Mast "+state.mast,tx,114);
  c.fillText("Cargo "+state.cargo,tx,138);
  c.fillText("Fuel "+state.fuel,tx,162);
  c.fillText("Crew "+state.crew_morale,tx,186);
  c.fillText("NAV "+state.buoys_seen.length+"/"+state.buoys.length,tx,210);
  c.fillText(state.anchor?"ANCHORED":"Underway",tx,234);
  c.fillStyle="#b6edcf";
  c.fillText("Skiff / sloop / schooner · physical port cargo delivery",12,265);
 }
 if(state.finished||state.failed){
  c.fillStyle=state.finished?"#a2f5cb":"#ffaba6";
  c.fillText(state.finished?"Completed":"Defeat",W-100,20);
 }
}

document.addEventListener("keydown",event=>{
 if(!advancedSession||advancedSession.editor!=="fighting"||advancedSession.terminal)return;
 if(event.target&&(["INPUT","TEXTAREA","SELECT"].includes(event.target.tagName)||
    event.target.isContentEditable))return;
 const actions={ArrowRight:"approach",ArrowLeft:"retreat",
   ArrowUp:"sidestep_up",ArrowDown:"sidestep_down",
   j:"jab",k:"kick",p:"parry"," ":"jump"};
 const action=actions[event.key];
 if(!action)return;
 event.preventDefault();advanceAdvanced(action);
});
document.addEventListener("keydown",event=>{
 if(!advancedSession||advancedSession.editor!=="rhythm"||advancedSession.terminal)return;
 if(event.target&&(["INPUT","TEXTAREA","SELECT"].includes(event.target.tagName)||
    event.target.isContentEditable))return;
 if(!/^[1-6]$/.test(event.key))return;
 const lane=Number(event.key)-1;
 if(lane>=advancedSession.state.chart.lanes)return;
 event.preventDefault();advanceAdvanced("tap:"+lane);
});
document.addEventListener("keydown",event=>{
 if(!advancedSession||advancedSession.editor!=="roguelike"||advancedSession.terminal)return;
 if(event.target&&(["INPUT","TEXTAREA","SELECT"].includes(event.target.tagName)||
    event.target.isContentEditable))return;
 const direction={ArrowUp:"north",ArrowDown:"south",ArrowLeft:"west",ArrowRight:"east"}[event.key];
 if(!direction)return;
 event.preventDefault();advanceAdvanced((event.shiftKey?"dash":"move")+"_"+direction);
});
document.addEventListener("keydown",event=>{
 if(!advancedSession||advancedSession.editor!=="stealth"||advancedSession.terminal)return;
 if(event.target && (["INPUT","TEXTAREA","SELECT"].includes(event.target.tagName)||
     event.target.isContentEditable))return;
 const direction={ArrowUp:"north",ArrowDown:"south",
  ArrowLeft:"west",ArrowRight:"east"}[event.key];
 if(!direction)return;
 event.preventDefault();
 const mode=event.shiftKey?"sprint":event.ctrlKey?"crouch":"move";
 advanceAdvanced(mode+"_"+direction);
});
let originalRhythmLongrunRecord=null;
let originalRoguelikeLongrunRecord=null;
let advancedAvailableActions=[];
let selectedQuestSite=0;
let selectedQuestNPC=0;
let selectedQuestCell=8;
let selectedRhythmNote=0;
let selectedRTSCell=27;
let selectedSandboxCell=0;
let selectedCityParcel=0;
function renderAdvancedActions(actions){
 const target=$("advanced-actions");target.replaceChildren();
 if(advancedSession?.editor==="quest_director"){
  const state=advancedSession.state;
  const picker=document.createElement("label");picker.textContent="Original player action";
  const action=document.createElement("select");
  action.id="quest-director-command";
  for(const registered of actions){
   const option=document.createElement("option");option.value=registered;
   option.textContent=registered.replaceAll("_"," ");
   action.append(option);
  }
  picker.append(action);target.append(picker);
  const submit=document.createElement("button");submit.type="button";
  submit.textContent="Execute physical witnessed-world action";
  submit.disabled=Boolean(advancedSession.terminal);
  submit.addEventListener("click",()=>advanceAdvanced(action.value));
  target.append(submit);
  const context=document.createElement("small");
  context.id="quest-director-context";
  const cell=selectedQuestCell;
  const site=state.sites.find(s=>s.cell===cell);
  const npc=state.npcs.find(n=>n.cell===cell);
  context.textContent="Selected world cell "+cell+
   (site?" · site #"+site.id+" "+site.kind+" HP "+site.integrity:"")+
   (npc?" · NPC #"+npc.id+" "+npc.role+
     " direct:"+npc.memories.length+" rumor:"+npc.heard.length+
     " forensic:"+(npc.investigations?.length||0)+" steps:"+(npc.walks||0):"");
  target.append(context);
  const nearby=document.createElement("label");
  nearby.textContent="NPC witness origin and current quest status";
  const report=document.createElement("pre");
  report.id="quest-director-evidence";
  report.textContent=JSON.stringify({
    player:state.player,
    latest_event:state.events_log.at(-1)||null,
    active_quests:state.quests.filter(q=>q.status==="active").map(q=>({
      id:q.id,event_id:q.origin_event,source:q.site_id,
      witnessed:q.witnesses,testimonies:q.testimonies,
      hearsay:q.heard_from,choice:q.choice,
      physical_followups:q.material_actions
    })),
    forensic_edges:state.forensic_edges.slice(-8),
    physical_npc_walks:state.npc_walks,
    npc_positions:state.npcs.map(n=>({id:n.id,cell:n.cell,energy:n.energy,
      original_home:n.home,investigations:n.investigations})),
    milestones:state.milestones.slice(-4),
    completed:state.quests_completed,
    nonterminal_world:!advancedSession.terminal,
    native_hardware_verified:advancedSession.native_hardware_verified
  },null,2);
  nearby.append(report);target.append(nearby);
  return;
 }

 if(advancedSession?.editor==="fighting"){
  const label=document.createElement("label");
  label.textContent="Original arena strike / defense / movement";
  const command=document.createElement("select");
  command.id="fighting-registered-action";
  command.setAttribute("aria-label","Select registered original tactical fighting action");
  for(const action of actions){
   const option=document.createElement("option");
   option.value=action;option.textContent=action.replaceAll("_"," ");
   command.append(option);
  }
  label.append(command);target.append(label);
  const submit=document.createElement("button");submit.type="button";
  submit.textContent="Execute original arena frame";
  submit.disabled=Boolean(advancedSession.terminal);
  submit.addEventListener("click",()=>advanceAdvanced(command.value));
  target.append(submit);
  const hint=document.createElement("small");
  hint.textContent="Arrows: approach, retreat and sidestep. J: jab · K: kick · P: parry · Space: jump. Hits require actual lanes, distance and finite stamina.";
  target.append(hint);
  const intro=document.createElement("label");
  intro.textContent="Original two-peer authoritative rollback laboratory";
  target.append(intro);
  const participants=[
    ["Blue physical actions","fighting-blue-actions",'["inspect","inspect"]'],
    ["Predicted opposing actions","fighting-predicted-actions",'["inspect","inspect"]'],
    ["Received authoritative opposing actions","fighting-real-actions",'["inspect","approach"]']
  ];
  const editors=[];
  for(const [name,id,placeholder] of participants){
    const label=document.createElement("label");label.textContent=name;
    const area=document.createElement("textarea");area.id=id;
    area.setAttribute("aria-label",name);area.rows=2;
    area.placeholder=placeholder;
    label.append(area);target.append(label);editors.push(area);
  }
  const run=document.createElement("button");run.type="button";
  run.id="fighting-rollback-reconcile";
  run.textContent="Reexecute authenticated fighting rollback";
  const proof=document.createElement("pre");proof.id="fighting-rollback-proof";
  proof.setAttribute("role","status");proof.setAttribute("aria-live","polite");
  run.addEventListener("click",async()=>{
    try{
      const [blue,predicted,authoritative]=editors.map(a=>JSON.parse(a.value));
      if(![blue,predicted,authoritative].every(Array.isArray))
        throw Error("Peer input streams must be valid JSON action lists");
      if(advancedEditor!==systemEditor().id)
        throw Error("Restart the game after changing the original fighting editor");
      const answer=await api("/api/fighting-rollback",{
        settings:advancedSettings,seed:advancedSession.seed,scene:advancedScene,
        blue_actions:blue,predicted_red:predicted,
        authoritative_red:authoritative
      });
      const evidence=answer.report;
      proof.textContent=JSON.stringify({
        frames:evidence.authoritative_match.frames,
        corrected_frames:evidence.reconciled_indices,
        correction_window:evidence.rollback_window_frames,
        authoritative_digest:evidence.authoritative_match.digest,
        winner:evidence.authoritative_match.state.reason,
        player_health:evidence.authoritative_match.state.player.hp,
        opposing_health:evidence.authoritative_match.state.opponent.hp,
        replay_verified:answer.independently_verified,
        network_certified:answer.network_transport_certified,
        native_hardware_certified:answer.native_hardware_certified,
        game_files_mutated:answer.game_files_mutated
      },null,2);
      status("Original two-peer rollback replay verified. Prediction rejected as authority; no online networking or native certification implied.");
    }catch(error){
      status("Peer input reconciliation rejected: "+error.message);
    }
  });
  target.append(run);target.append(proof);return;
 }

 if(advancedSession?.editor==="rhythm"){
  const s=advancedSession.state;
  const instructions=document.createElement("small");
  instructions.textContent="Original game clock "+s.clock_ms+
    "ms · tap with keys 1–6, chart time is advanced with bounded wait commands.";
  target.append(instructions);
  const laneLabel=document.createElement("label");
  laneLabel.textContent="Original note lane";
  const lane=document.createElement("select");lane.id="rhythm-play-lane";
  for(let i=0;i<s.chart.lanes;i++){
   const option=document.createElement("option");option.value=String(i);
   option.textContent="Lane "+(i+1);lane.append(option);
  }
  laneLabel.append(lane);target.append(laneLabel);
  const kindLabel=document.createElement("label");
  kindLabel.textContent="Real timed key action";
  const kind=document.createElement("select");kind.id="rhythm-play-kind";
  for(const name of ["tap","press","release","flick","chord"]){
   const option=document.createElement("option");
   option.value=name;option.textContent=name;kind.append(option);
  }
  kindLabel.append(kind);target.append(kindLabel);
  const partnerLabel=document.createElement("label");
  partnerLabel.textContent="Second chord key";
  const partner=document.createElement("select");partner.id="rhythm-play-partner";
  for(let j=0;j<s.chart.lanes;j++){
   const opt=document.createElement("option");opt.value=String(j);
   opt.textContent="Lane "+(j+1);partner.append(opt);
  }
  partnerLabel.append(partner);target.append(partnerLabel);
  const send=document.createElement("button");send.type="button";
  send.textContent="Submit original timed note";
  send.disabled=Boolean(advancedSession.terminal);
  send.addEventListener("click",()=>{
   const a=Number(lane.value),b=Number(partner.value);
   if(kind.value==="chord"&&a===b)throw Error("Chords require two distinct lanes");
   advanceAdvanced(kind.value+":"+a+(kind.value==="chord"?":"+b:""));
  });
  target.append(send);
  const travel=document.createElement("label");
  travel.textContent="Advance original song clock by milliseconds";
  const delta=document.createElement("select");delta.id="rhythm-time-step";
  for(const ms of [10,20,25,50,100,125,250,500,1000,2000]){
   const opt=document.createElement("option");opt.value=String(ms);
   opt.textContent=ms+" ms";if(ms===500)opt.selected=true;
   delta.append(opt);
  }
  travel.append(delta);target.append(travel);
  const wait=document.createElement("button");wait.type="button";
  wait.textContent="Run verified song clock";
  wait.disabled=Boolean(advancedSession.terminal);
  wait.addEventListener("click",()=>advanceAdvanced("wait:"+delta.value));
  target.append(wait);
  const finish=document.createElement("button");finish.type="button";
  finish.textContent="Finalize genuinely judged beat chart";
  finish.disabled=Boolean(advancedSession.terminal);
  finish.addEventListener("click",()=>advanceAdvanced("finish"));
  target.append(finish);
  const audioLabel=document.createElement("label");
  audioLabel.textContent="Original oscillator soundtrack preview";
  const audio=document.createElement("audio");
  audio.id="rhythm-original-wav-preview";
  audio.controls=true;audio.preload="none";
  audioLabel.append(audio);target.append(audioLabel);
  const hear=document.createElement("button");hear.type="button";
  hear.textContent="Synthesize reviewed original song audio";
  hear.addEventListener("click",async()=>{
   try{
    const clip=await api("/api/rhythm-audio",{
      settings:advancedSettings,seed:advancedSession.seed,scene:advancedScene,
      from_ms:Math.floor(s.clock_ms/2500)*2500,duration_ms:2500
    });
    audio.src="data:audio/wav;base64,"+clip.audio_base64;
    audio.load();
    status("Original oscillator audio SHA-256 "+clip.receipt.sha256.slice(0,16)+
      " · independent native playback remains unverified.");
   }catch(error){
    status("Original rhythm audio source rejected: "+error.message);
   }
  });
  target.append(hear);
  const marathonLabel=document.createElement("label");
  marathonLabel.textContent="Original long song action batch (JSON list of legal rhythmic inputs)";
  const marathonText=document.createElement("textarea");
  marathonText.id="rhythm-longrun-actions";
  marathonText.setAttribute("aria-label","Original authored song actions for full replay");
  marathonText.rows=3;
  marathonText.placeholder='["tap:0","wait:500","tap:3"]';
  marathonLabel.append(marathonText);target.append(marathonLabel);
  const button=document.createElement("button");
  button.type="button";button.id="rhythm-longrun-submit";
  button.textContent="Verify / resume long rhythm performance";
  const evidence=document.createElement("pre");
  evidence.id="rhythm-longrun-proof";
  evidence.setAttribute("role","status");
  evidence.setAttribute("aria-live","polite");
  button.addEventListener("click",async()=>{
   try{
    const actions=JSON.parse(marathonText.value);
    if(!Array.isArray(actions))throw Error("A JSON list of registered gameplay inputs is required");
    if(advancedEditor!==systemEditor().id)
      throw Error("Authored rhythm editor changed; restart the source session");
    const result=await api("/api/rhythm-longrun",{
      settings:advancedSettings,actions,
      prior:originalRhythmLongrunRecord,
      seed:advancedSession.seed,scene:advancedScene,
      checkpoint_interval:64
    });
    originalRhythmLongrunRecord=result.record;
    evidence.textContent=JSON.stringify({
      turns:result.record.turn_count,
      checkpoints:result.record.checkpoint_count,
      clock_ms:result.record.state.clock_ms,
      beat_count:result.record.state.chart.beats,
      score:result.record.state.score,
      accuracy:result.record.accuracy,
      victory:result.record.victory,
      terminal:result.record.finished||result.record.failed,
      head_digest:result.record.head_digest,
      independently_verified:result.independently_verified,
      native_hardware_certified:result.native_hardware_certified,
      game_files_mutated:result.game_files_mutated
    },null,2);
    marathonText.value="[]";
    status("Full original rhythm history independently reexecuted from source. No untrusted checkpoint, auto-approval or native certification.");
   }catch(error){
    status("Original rhythm marathon rejected: "+error.message);
   }
  });
  target.append(button);target.append(evidence);
  return;
 }

 if(advancedSession?.editor==="rts"){
  const troop=document.createElement("label");
  troop.textContent="Player-owned unit";
  const unit=document.createElement("select");unit.id="rts-owned-unit";
  for(const u of advancedSession.state.units){
   if(u.hp<=0)continue;
   const option=document.createElement("option");
   option.value=String(u.id);
   option.textContent="#"+u.id+" "+u.kind+" HP "+u.hp+" cell "+u.cell;
   unit.append(option);
  }
  unit.value=String(advancedSession.state.selected);
  troop.append(unit);target.append(troop);
  const choose=document.createElement("label");
  choose.textContent="Actual battlefield target tile";
  const targetCell=document.createElement("select");targetCell.id="rts-target-cell";
  for(let i=0;i<64;i++){
   const option=document.createElement("option");option.value=String(i);
   option.textContent="Tile "+i+" · "+Math.floor(i/8)+":"+i%8;
   targetCell.append(option);
  }
  targetCell.value=String(selectedRTSCell);choose.append(targetCell);
  target.append(choose);
  const order=document.createElement("label");
  order.textContent="Real movement / combat / economy action";
  const command=document.createElement("select");
  command.id="rts-command";
  const fill=()=>{
   selectedRTSCell=Number(targetCell.value);
   command.replaceChildren();
   const local=actions.filter(a=>a.endsWith(":"+targetCell.value) &&
                       !a.startsWith("select:"));
   const other=actions.filter(a=>!a.match(/:[0-9]+$/) &&
                              !a.startsWith("construct:"));
   for(const action of [...local,...other]){
    const opt=document.createElement("option");
    opt.value=action;opt.textContent=action.replaceAll("_"," ");
    command.append(opt);
   }
  };
  targetCell.addEventListener("change",fill);fill();
  order.append(command);target.append(order);
  const issue=document.createElement("button");issue.type="button";
  issue.textContent="Issue verified tactical order";
  issue.disabled=Boolean(advancedSession.terminal);
  issue.addEventListener("click",async()=>{
   const intended=Number(unit.value);
   if(intended!==advancedSession.state.selected)
    await advanceAdvanced("select:"+intended);
   await advanceAdvanced(command.value);
  });
  target.append(issue);
  const hint=document.createElement("small");
  hint.textContent="Click the battlefield to target. Worker cargo physically returns to home depots; patrols, fog and capture use real tactical positions.";
  target.append(hint);
  return;
 }

 if(advancedSession?.editor==="roguelike"){
  const selector=document.createElement("label");
  selector.textContent="Original tactical move / equipment / floor objective";
  const command=document.createElement("select");
  command.id="roguelike-player-command";
  command.setAttribute("aria-label","Choose dungeon action from authoritative registry");
  for(const act of actions){
   const option=document.createElement("option");
   option.value=act;option.textContent=act.replaceAll("_"," ");
   command.append(option);
  }
  selector.append(command);target.append(selector);
  const submit=document.createElement("button");submit.type="button";
  submit.textContent="Execute verified dungeon action";
  submit.disabled=Boolean(advancedSession.terminal);
  submit.addEventListener("click",()=>advanceAdvanced(command.value));
  target.append(submit);
  const hint=document.createElement("small");
  hint.textContent="Arrow keys move one tile; Shift+arrow spends stamina on dash; enemy blocks physical movement. A boss must actually fall before final extraction.";
  target.append(hint);
  const marathonLabel=document.createElement("label");
  marathonLabel.textContent="Long-run original dungeon transcript (JSON array of legitimate actions)";
  const marathonInput=document.createElement("textarea");
  marathonInput.id="roguelike-longrun-actions";
  marathonInput.setAttribute("aria-label","Enter additional legal original roguelike commands as JSON");
  marathonInput.placeholder='["move_east","strike_east","take_stairs"]';
  marathonInput.rows=3;marathonLabel.append(marathonInput);
  target.append(marathonLabel);
  const marathon=document.createElement("button");
  marathon.type="button";
  marathon.id="roguelike-longrun-submit";
  marathon.textContent="Verify / continue long-run dungeon";
  const result=document.createElement("pre");
  result.id="roguelike-longrun-proof";
  result.setAttribute("role","status");
  result.setAttribute("aria-live","polite");
  marathon.addEventListener("click",async()=>{
   try{
    const actions=JSON.parse(marathonInput.value);
    if(!Array.isArray(actions))throw Error("Commands must be an array");
    if(advancedEditor!==systemEditor().id)
      throw Error("Restart dungeon before submitting a changed editor");
    const answer=await api("/api/roguelike-marathon",{
      settings:advancedSettings,actions,seed:advancedSession.seed,
      scene:advancedScene,prior:originalRoguelikeLongrunRecord,
      checkpoint_interval:64
    });
    originalRoguelikeLongrunRecord=answer.record;
    result.textContent=JSON.stringify({
      floor:answer.record.state.floor,
      turns:answer.record.turn_count,
      checkpoint_count:answer.record.checkpoint_count,
      head_digest:answer.record.head_digest,
      independently_verified:answer.independently_verified,
      victory:answer.record.victory,
      terminal:answer.record.terminal,
      game_files_mutated:answer.game_files_mutated,
      native_executable_certified:answer.native_executable_certified
    },null,2);
    marathonInput.value="[]";
    status("Long-run dungeon replayed from original source and checked in bounded segments. No checkpoint bypass or native certification.");
   }catch(error){status("Roguelike longrun rejected: "+error.message);}
  });
  target.append(marathon);target.append(result);
  return;
 }

 if(advancedSession?.editor==="sandbox"){
  const terrain=advancedSession.state.regions[String(advancedSession.state.region)]||[];
  const choose=document.createElement("label");
  choose.textContent="Original 8×8 world cell";
  const cell=document.createElement("select");cell.id="sandbox-target-cell";
  cell.setAttribute("aria-label","Select local original sandbox cell");
  for(const t of terrain){
   const option=document.createElement("option");
   option.value=String(t.id);
   option.textContent=String(t.id)+" · "+t.terrain+
    (t.building?" · "+t.building:"");
   cell.append(option);
  }
  cell.value=String(selectedSandboxCell);
  choose.append(cell);target.append(choose);
  const order=document.createElement("label");
  order.textContent="Terraform / harvest / structure / world operation";
  const actionSelect=document.createElement("select");
  actionSelect.id="sandbox-registered-action";
  actionSelect.setAttribute("aria-label","Choose physically validated sandbox order");
  const generic=actions.filter(x=>!/:([0-9]+)$/.test(x));
  const fill=()=>{
   selectedSandboxCell=Number(cell.value);
   actionSelect.replaceChildren();
   const local=actions.filter(x=>x.endsWith(":"+cell.value));
   for(const command of [...local,...generic]){
    const option=document.createElement("option");
    option.value=command;option.textContent=command.replaceAll("_"," ");
    actionSelect.append(option);
   }
  };
  cell.addEventListener("change",fill);fill();order.append(actionSelect);
  target.append(order);
  const submit=document.createElement("button");submit.type="button";
  submit.textContent="Execute verified world operation";
  submit.disabled=Boolean(advancedSession.terminal);
  submit.addEventListener("click",()=>advanceAdvanced(actionSelect.value));
  target.append(submit);
  const note=document.createElement("small");
  note.textContent="Yellow frame is player; nearby terrain only. Crossing regions preserves all built and harvested terrain. Creative controls cannot bypass source review.";
  target.append(note);
  return;
 }

 if(advancedSession?.editor==="metroidvania"){
  const choose=document.createElement("label");
  choose.textContent="Connected region / traversal target";
  const region=document.createElement("select");
  region.id="exploration-target-region";
  for(const r of advancedSession.state.rooms){
   const option=document.createElement("option");
   option.value=String(r.id);
   option.textContent="Region "+r.id+" · "+r.biome+
    (r.visited?" · visited":" · unexplored");
   region.append(option);
  }
  choose.append(region);target.append(choose);
  const group=document.createElement("label");
  group.textContent="Travel / combat / crafting / realm action";
  const command=document.createElement("select");
  command.id="exploration-world-order";
  const local=["travel","break","fast"];
  const fill=()=>{
   const id=region.value;
   command.replaceChildren();
   const selected=[...local.map(kind=>kind+":"+id).filter(x=>actions.includes(x)),
                   ...actions.filter(x=>!x.includes(":"))];
   for(const action of selected){
    const opt=document.createElement("option");
    opt.value=action;opt.textContent=action.replaceAll("_"," ");
    command.append(opt);
   }
  };
  region.addEventListener("change",fill);
  fill();group.append(command);target.append(group);
  const go=document.createElement("button");go.type="button";
  go.textContent="Execute verified exploration move";
  go.disabled=Boolean(advancedSession.terminal);
  go.addEventListener("click",()=>advanceAdvanced(command.value));
  target.append(go);
  const hint=document.createElement("small");
  hint.textContent="Orange links need powers; claim a cleared shrine, revisit rooms or spend stamina on a legal break.";
  target.append(hint);
  return;
 }
 if(advancedSession?.editor==="stealth"){
  const group=document.createElement("label");
  group.textContent="Infiltration move / cover / gadget";
  const select=document.createElement("select");
  select.id="stealth-player-command";
  select.setAttribute("aria-label","Select original stealth action");
  for(const action of actions){
   const option=document.createElement("option");
   option.value=action;option.textContent=action.replaceAll("_"," ");
   select.append(option);
  }
  group.append(select);target.append(group);
  const submit=document.createElement("button");
  submit.type="button";submit.textContent="Execute verified stealth action";
  submit.disabled=Boolean(advancedSession.terminal);
  submit.addEventListener("click",()=>advanceAdvanced(select.value));
  target.append(submit);
  const hint=document.createElement("small");
  hint.textContent="Arrow keys move; shift + arrow sprints; ctrl + arrow crouches. Map is a visualization, not a teleport.";
  target.append(hint);
  return;
 }
 if(advancedSession?.editor==="city_builder"){
  const parcelLabel=document.createElement("label");
  parcelLabel.textContent="Selected urban parcel";
  const parcel=document.createElement("select");
  parcel.id="city-target-cell";
  parcel.setAttribute("aria-label","Choose original city parcel");
  for(let i=0;i<16;i++){
   const option=document.createElement("option");
   option.value=String(i);
   option.textContent=String(i)+" · "+advancedSession.state.parcels[i].terrain+
    " · "+advancedSession.state.parcels[i].kind;
   parcel.append(option);
  }
  parcel.value=String(selectedCityParcel);
  parcelLabel.append(parcel);target.append(parcelLabel);
  const commandLabel=document.createElement("label");
  commandLabel.textContent="Build / zone / municipal order";
  const select=document.createElement("select");
  select.id="city-registered-action";
  select.setAttribute("aria-label","Choose registered civic command");
  const globalOrders=actions.filter(a=>!a.includes(":")||
   a.startsWith("tax:")||a.startsWith("policy:"));
  const fill=()=>{
   const index=parcel.value;
   selectedCityParcel=Number(index);
   const local=actions.filter(a=>a.endsWith(":"+index));
   select.replaceChildren();
   for(const action of [...local,...globalOrders]){
    const option=document.createElement("option");
    option.value=action;option.textContent=action;
    select.append(option);
   }
  };
  parcel.addEventListener("change",fill);
  fill();commandLabel.append(select);target.append(commandLabel);
  const submit=document.createElement("button");
  submit.type="button";submit.textContent="Issue verified city order";
  submit.disabled=Boolean(advancedSession.terminal);
  submit.addEventListener("click",()=>advanceAdvanced(select.value));
  target.append(submit);
  return;
 }
 for(const action of actions){
  const button=document.createElement("button");
  button.type="button";button.textContent=action;button.value=action;
  button.disabled=Boolean(advancedSession&&advancedSession.terminal);
  button.addEventListener("click",()=>advanceAdvanced(action));
  target.append(button);
 }
}

$("advanced-canvas").addEventListener("click",event=>{
 if(advancedSession?.editor==="quest_director"){
  const board=$("advanced-canvas"),rect=board.getBoundingClientRect();
  const px=(event.clientX-rect.left)*board.width/rect.width;
  const py=(event.clientY-rect.top)*board.height/rect.height;
  const x=Math.floor((px-14)/25),y=Math.floor((py-47)/27);
  if(x<0||x>=7||y<0||y>=7||
      px>14+x*25+23||py>47+y*27+25)return;
  selectedQuestCell=y*7+x;
  renderAdvancedActions(advancedAvailableActions);
  drawAdvancedGame(advancedSession);
  return;
 }

 if(advancedSession&&advancedSession.editor==="rts"){
  const board=$("advanced-canvas"),rect=board.getBoundingClientRect();
  const px=(event.clientX-rect.left)*board.width/rect.width;
  const py=(event.clientY-rect.top)*board.height/rect.height;
  const x=Math.floor((px-14)/26),y=Math.floor((py-43)/25);
  if(x<0||x>=8||y<0||y>=8||
     px>14+x*26+24||py>43+y*25+23)return;
  selectedRTSCell=y*8+x;
  const field=$("rts-target-cell");
  if(field){field.value=String(selectedRTSCell);
   field.dispatchEvent(new Event("change"));}
  return;
 }

 if(advancedSession&&advancedSession.editor==="sandbox"){
  const canvas=$("advanced-canvas"),rect=canvas.getBoundingClientRect();
  const px=(event.clientX-rect.left)*canvas.width/rect.width;
  const py=(event.clientY-rect.top)*canvas.height/rect.height;
  const col=Math.floor((px-12)/27),row=Math.floor((py-37)/24);
  if(col<0||col>7||row<0||row>7||
     px>12+col*27+25||py>37+row*24+22)return;
  selectedSandboxCell=row*8+col;
  const picker=$("sandbox-target-cell");
  if(picker){picker.value=String(selectedSandboxCell);
   picker.dispatchEvent(new Event("change"));}
  return;
 }

 if(!advancedSession||advancedSession.editor!=="city_builder")return;
 const canvas=$("advanced-canvas"),rect=canvas.getBoundingClientRect();
 const px=(event.clientX-rect.left)*canvas.width/rect.width;
 const py=(event.clientY-rect.top)*canvas.height/rect.height;
 const col=Math.floor((px-16)/52),row=Math.floor((py-56)/39);
 if(col<0||col>=4||row<0||row>=4||px>16+col*52+48
    ||py>56+row*39+35)return;
 selectedCityParcel=row*4+col;
 const picker=$("city-target-cell");
 if(picker){picker.value=String(selectedCityParcel);
  picker.dispatchEvent(new Event("change"));}
});
function showAdvanced(reply){
 advancedSession=reply.session;
 advancedAvailableActions=reply.available_actions;
 const nativeSourceFamilies=new Set(["puzzle","platformer","deck_battler",
  "shooter","tactics","tower_defense","racing","survival","farming",
  "factory","colony","physics"]);
 const physicsActions=new Set(["inspect","step","step:4","push:east",
  "push:west","push:up","push:down","brake","torque:cw","torque:ccw","select:0"]);
 const authored=advancedSession.scene?.layout;
 const physicsNativeReady=advancedSession.editor!=="physics" || (
   advancedSettings?.max_bodies===1 && advancedSettings?.dimension==="2d" &&
   advancedSettings?.collision_geometry==="aabb" && advancedSettings?.substeps===1 &&
   advancedSettings?.initial_battery===0 &&
   authored?.bodies?.length===1 &&
   authored?.fixtures?.length<=8 &&
   authored.fixtures.every(fixture=>fixture.orientation===0) &&
   authored.water_y>authored.floor_y &&
   advancedSession.actions.every(action=>physicsActions.has(action)));
 const nativeReady=nativeSourceFamilies.has(advancedSession.editor)&&physicsNativeReady;
 $("advanced-godot-export").disabled=!nativeReady;
 $("advanced-godot-export").title=nativeReady?
  "Package independent original Godot source; real native replay and hardware review remain separate":
  advancedSession.editor==="physics"?
  "Physics Godot export requires an authored one-body 2D AABB scene with at most 8 axis-aligned fixtures, substeps=1, battery=0 and supported actions":
  "This family has no independently running native Godot source adapter";
 $("advanced-physics-interop").disabled=!["platformer","racing","sandbox"].includes(
  advancedSession.editor)||!advancedSession.scene;
 $("advanced-npc-observe").disabled=!["platformer","racing","sandbox"].includes(
   advancedSession.editor)||!advancedSession.scene;
 $("advanced-npc-multi").disabled=!["platformer","racing","sandbox"].includes(
   advancedSession.editor)||!advancedSession.scene;
 $("advanced-episodic-add").disabled=!["platformer","racing","sandbox"].includes(
   advancedSession.editor)||!advancedSession.scene;
 $("advanced-genre-event-inspect").disabled=!["farming","sailing","flight"].includes(
   advancedSession.editor)||!advancedSession.scene;
 $("advanced-genre-event-play").disabled=!["farming","sailing","flight"].includes(
   advancedSession.editor)||!advancedSession.scene;
 $("advanced-genre-queue").disabled=!["farming","sailing","flight"].includes(
   advancedSession.editor)||!advancedSession.scene;
 $("advanced-interop-godot").disabled=!["platformer","racing","sandbox"].includes(
   advancedSession.editor)||!advancedSession.scene;
 $("advanced-linked-step").disabled=!["platformer","racing","sandbox"].includes(
   advancedSession.editor)||!advancedSession.scene;
 const sourceChoice=$("advanced-linked-action");
 const oldChoice=sourceChoice.value;
 sourceChoice.replaceChildren();
 for(const value of reply.available_actions){
  const option=document.createElement("option");
  option.value=value;option.textContent=value.replaceAll("_"," ");
  sourceChoice.append(option);
 }
 if(reply.available_actions.includes(oldChoice))sourceChoice.value=oldChoice;
 $("advanced-state").textContent=JSON.stringify({
   session_digest:advancedSession.digest,
   turns:advancedSession.validated_turn_count,
   state:advancedSession.state,
   terminal:advancedSession.terminal,
   native_hardware_verified:advancedSession.native_hardware_verified,
 },null,2);
 drawAdvancedGame(advancedSession);
 renderAdvancedActions(reply.available_actions);
}
async function startAdvanced(){
 try{
  advancedEditor=systemEditor().id;advancedSettings=systemSettings();
  const seedText=$("advanced-seed").value;
  if(!/^[0-9]+$/.test(seedText))throw Error("Advanced seed must be an integer");
  const seed=Number(seedText);
  advancedScene=$("advanced-scene-json").value.trim()?
   JSON.parse($("advanced-scene-json").value):null;
  const reply=await api("/api/advanced-play",{
   editor:advancedEditor,settings:advancedSettings,actions:[],seed,
   scene:advancedScene});
  advancedCommands=[];
  originalRhythmLongrunRecord=null;originalRoguelikeLongrunRecord=null;
  showAdvanced(reply);
  status("Started deterministic advanced "+advancedEditor+" session. Commands are replay-audited.");
 }catch(error){status("Advanced session blocked: "+error.message);}
}
async function advanceAdvanced(action){
 try{
  if(!advancedSession)throw Error("Start the advanced scenario first");
  if(advancedEditor!==systemEditor().id)throw Error("Editor changed; start a fresh scenario");
  const actions=[...advancedCommands,action];
  const reply=await api("/api/advanced-play",{
   editor:advancedEditor,settings:advancedSettings,
   actions,seed:advancedSession.seed,scene:advancedScene});
  advancedCommands=actions;showAdvanced(reply);
  status("Advanced action verified: "+action+" · "+reply.session.head_digest.slice(0,16));
 }catch(error){status("Advanced action rejected: "+error.message);}
}
// Visual paint works only on the local draft JSON. It cannot bypass the
// server's canonical validation, exact-file review, or human commit.
const PAINT_TOOLS={
 quest_director:["obstacle_toggle","site_move","npc_move","player_spawn",
      "site_integrity_up","site_stock_up","npc_trust_up",
      "npc_perception_up","site_kind_next","npc_role_next",
      "climate_next","day_phase_next"],

 fighting:["hazard_toggle","hazard_damage_up","cover_toggle",
           "cover_hp_up","player_spawn","enemy_spawn",
           "theme_next","weather_next"],

 rhythm:["lane_next","kind_next","partner_next","accent_toggle",
         "timestamp_earlier","timestamp_later","title_next",
         "original_meter_remark"],

 rts:["obstacle_toggle","wood_node","ore_node","energy_node",
       "remove_node","wood_plus","ore_plus","energy_plus",
       "friendly_base","enemy_base","relay","friendly_spawn",
       "enemy_spawn","erase_spawn","environment_next",
       "starting_wood_up","starting_ore_up","starting_energy_up",
       "enemy_base_hp_up"],

 roguelike:["wall_toggle","trap_toggle","chest_toggle",
   "spawn","exit","shop","shrine","enemy_toggle",
   "enemy_health_up","enemy_health_down","enemy_attack_up","enemy_attack_down",
   "toggle_elite","ambient_next","light_next","trap_damage_up",
   "trap_damage_down","reserve_up","reserve_down"],

 sandbox:["terrain_next","wood_plus","wood_minus","stone_plus","stone_minus",
          "clay_plus","clay_minus","ore_plus","ore_minus","water_plus",
          "water_minus","fish_plus","fish_minus","forage_plus",
          "forage_minus","soil_toggle","crop_up","crop_down",
          "moisture_plus","animal_toggle","tamed_toggle","sapling_toggle",
          "fire_up","fire_down","pollution_down",
          "structure_next","spawn","settler_toggle","weather_next",
          "credits_plus","credits_minus"],

 shooter:["cover","medkit","player_spawn","extraction",
          "enemy_spawn_0","enemy_spawn_1","enemy_spawn_2","erase"],
 tactics:["obstacles","squad_0","squad_1","enemy_0","enemy_1",
          "objective","erase"],
 puzzle:["walls","spawn","exit","doors","switches","crates","targets",
         "nodes","phase_gates","portal_a","portal_b","erase"],
 colony:["wood_plus","wood_minus","stone_plus","stone_minus",
         "food_plus","food_minus","water_plus","water_minus",
         "biome_next","make_start","threat_up","threat_down",
         "caravan_plus","caravan_minus"],
 metroidvania:["biome_next","foe_plus","foe_minus",
              "hazard_up","hazard_down","cache_plus","cache_minus",
              "ability_next","toggle_anchor","toggle_secret",
              "set_entry","set_guardian","gate_next","toggle_break"],
 stealth:["walls","shadows","vents","doors","cameras","keycards",
          "intel","patrol_route","spawn","extraction","objective",
          "terminal","erase","lighting_next","alarm_up","alarm_down"],
 city_builder:["terrain_plain","terrain_forest","terrain_hill",
               "terrain_wetland","terrain_water","road_hub",
               "aquifer_plus","aquifer_minus","flood_up","flood_down",
               "timber_plus","stone_plus"],
};
const GRID_COLORS={
 cover:"#7690a3",medkits:"#e1c76f",enemy_spawns:"#ef9691",
 squad_spawns:"#8dd9ca",obstacles:"#6e8294",walls:"#607789",
 player_spawn:"#92e7b1",spawn:"#92e7b1",player:"#92e7b1",
 objective:"#f1db9f",extraction:"#849de1",exit:"#a0e5ba",
 switches:"#f0c36b",doors:"#b97769",crates:"#b58d61",
 targets:"#85c6dc",nodes:"#86d5ec",phase_gates:"#b39ae6",
 portal_a:"#b19eea",portal_b:"#b19eea",
};
function paintPalette(){
 const target=$("advanced-paint-tool");target.replaceChildren();
 const options=PAINT_TOOLS[systemEditor()?.id]||[];
 for(const name of options){
  const option=document.createElement("option");
  option.value=name;option.textContent=name.replaceAll("_"," ");
  target.append(option);
 }
 $("advanced-scene-grid").style.cursor=options.length?"crosshair":"default";
 renderSceneAuthoring();
}
function sceneGridShape(source){
 const kind=source.editor,layout=source.layout;
 if(kind==="stealth")return [10,8];
 if(kind==="shooter")return [layout.width,layout.height];
 if(kind==="puzzle")return [systemSettings().board_width,systemSettings().board_height];
 if(kind==="tactics")return [systemSettings().board_width,systemSettings().board_height];
 return null;
}
function renderSceneAuthoring(){
 const canvas=$("advanced-scene-grid"),ctx=canvas.getContext("2d");
 const W=canvas.width,H=canvas.height;
 ctx.fillStyle="#09202f";ctx.fillRect(0,0,W,H);
 ctx.fillStyle="#dae9ed";ctx.font="12px system-ui";
 const sourceText=$("advanced-scene-json").value.trim();
 if(!sourceText){ctx.fillText("Generate an authored scene to paint its cells.",12,24);return;}
 let source,shape;
 try{
  source=JSON.parse(sourceText);
  if(source.editor!==systemEditor()?.id)throw Error("Editor and scene family differ");
  shape=sceneGridShape(source);
 }catch(_){ctx.fillText("Invalid or mismatched scene JSON: use Validate.",12,24);return;}

 if(source.editor==="quest_director"){
  const m=source.layout,ox=13,oy=39,size=29;
  ctx.fillText("Signed 7×7 witnessed quest site and NPC source painter",12,23);
  for(let i=0;i<49;i++){
   const x=ox+(i%7)*size,y=oy+Math.floor(i/7)*28;
   ctx.fillStyle=m.obstacles.includes(i)?"#68777b":"#355e56";
   ctx.fillRect(x,y,27,26);
   const site=m.sites.find(s=>s.cell===i);
   const npc=m.npcs.find(n=>n.cell===i);
   let token="";
   if(site)token="S"+site.id;
   if(npc)token="N"+npc.id;
   if(i===m.player_spawn)token="P";
   if(token){
    ctx.fillStyle="#e8e9c6";
    ctx.fillText(token,x+6,y+18);
   }
  }
  ctx.fillStyle="#d6e7dc";const tx=230;
  ctx.fillText("Climate "+m.climate,tx,54);
  ctx.fillText("Day phase "+m.day_phase,tx,79);
  ctx.fillText("NPC witnesses "+m.npcs.length,tx,104);
  ctx.fillText("Quest origin sites "+m.sites.length,tx,129);
  ctx.fillText("Physical obstacles "+m.obstacles.length,tx,154);
  ctx.fillText("Selected authored cell "+selectedQuestCell,tx,179);
  ctx.fillText("Review identity, visibility, budgets, path reachability",12,254);
  return;
 }
 if(source.editor==="fighting"){
  const arena=source.layout,ox=12,oy=41,sx=23,sy=52;
  ctx.fillText("Original 3-lane arena · source-bound units and stage objects",12,23);
  for(let y=0;y<3;y++)for(let x=0;x<arena.width;x++){
   const px=ox+x*sx,py=oy+y*sy;
   ctx.fillStyle=y%2?"#39686c":"#2b5362";
   ctx.fillRect(px,py,sx-2,sy-3);
   let token="";
   if(arena.player_spawn[0]===x&&arena.player_spawn[1]===y)token="P";
   else if(arena.enemy_spawn[0]===x&&arena.enemy_spawn[1]===y)token="A";
   else if(arena.hazards.some(h=>h.x===x&&h.lane===y))token="!";
   else if(arena.cover.some(h=>h.x===x&&h.lane===y))token="C";
   if(token){
    ctx.fillStyle=token==="!"?"#ffb09b":"#e2f3bd";
    ctx.fillText(token,px+7,py+27);
   }
  }
  ctx.fillStyle="#dbece3";
  ctx.fillText("Theme "+arena.theme+" · weather "+arena.weather,12,224);
  ctx.fillText("Source-bound fight rounds / hazard collision. Review before use.",12,245);
  return;
 }
 if(source.editor==="rhythm"){
  const m=source.layout,notes=m.notes,from=Math.floor(
     selectedRhythmNote/16)*16;
  ctx.fillText("Original rhythm chart · 16 authored beat events per sheet",12,18);
  const cellWidth=28,laneHeight=23;
  for(let row=0;row<m.lanes;row++){
   ctx.fillStyle="#dbe9ea";
   ctx.fillText(String(row+1),13,45+row*laneHeight);
  }
  for(let i=0;i<16&&from+i<notes.length;i++){
   const n=notes[from+i],x=38+i*28,y=32+n.lane*laneHeight;
   ctx.fillStyle=n.kind==="mine"?"#fca29a":
     n.kind==="hold"?"#c4a5f7":
     n.kind==="slide"?"#99dcee":
     n.kind==="chord"?"#f1cd88":"#91e3b9";
   ctx.fillRect(x+2,y,23,16);
   if(n.kind==="chord"&&n.partner!==null)
    ctx.fillRect(x+2,32+n.partner*laneHeight,23,16);
   ctx.fillStyle="#f6f6d4";
   ctx.fillText(String(n.id),x+5,29);
   if(n.id===selectedRhythmNote){
    ctx.strokeStyle="#fff3a7";ctx.strokeRect(x,y-1,25,18);
   }
  }
  ctx.fillStyle="#d6ebe6";
  ctx.fillText("Tempo "+m.bpm+" BPM · notes "+notes.length+
    " · lanes "+m.lanes,12,198);
  ctx.fillText("Beat sheet "+(Math.floor(from/16)+1)+
    " · selected "+selectedRhythmNote,12,220);
  ctx.fillText("Select note by clicking its beat column; validate source digest",12,242);
  return;
 }
 if(source.editor==="rts"){
  const m=source.layout;
  ctx.fillText("Original 8×8 original strategic resource/capture map",12,18);
  for(let i=0;i<64;i++){
   const x=14+(i%8)*27,y=31+Math.floor(i/8)*25;
   ctx.fillStyle=m.obstacles.includes(i)?"#838581":"#3e735f";
   ctx.fillRect(x,y,25,23);
   let label="";
   if(i===m.friendly_base)label="B";
   else if(i===m.enemy_base)label="X";
   else if(i===m.relay)label="C";
   else if(m.friendly_spawns.includes(i))label="U";
   else if(m.enemy_spawns.includes(i))label="R";
   else{
    const node=m.nodes.find(n=>n.cell===i);
    if(node)label=node.type[0].toUpperCase();
   }
   if(label){
    ctx.fillStyle="#faf3ce";
    ctx.fillText(label,x+8,y+17);
   }
  }
  ctx.fillStyle="#d4e8da";
  ctx.fillText("Environment "+m.environment,251,45);
  ctx.fillText("Wood "+m.starting_wood+" · ore "+m.starting_ore,251,69);
  ctx.fillText("Energy "+m.starting_energy,251,92);
  ctx.fillText("Hostile base HP "+m.enemy_base_health,251,115);
  ctx.fillText("Nodes "+m.nodes.length+
   " · walls "+m.obstacles.length,251,138);
  ctx.fillText("Revalidate before playing; no instant victories",251,171);
  return;
 }
 if(source.editor==="roguelike"){
  const layout=source.layout;
  ctx.fillText("Original signed 6×6 procedural dungeon source (first floor)",12,18);
  for(let i=0;i<36;i++){
   const x=15+(i%6)*34,y=32+Math.floor(i/6)*32;
   ctx.fillStyle=layout.terrain[i]==="wall"?"#79838d":"#2c5764";
   ctx.fillRect(x,y,32,30);
   let glyph="";
   if(i===layout.entry)glyph="P";
   else if(i===layout.exit)glyph="E";
   else if(i===layout.shop)glyph="$";
   else if(i===layout.shrine)glyph="S";
   else if(layout.chests.includes(i))glyph="C";
   else if(layout.traps.includes(i))glyph="!";
   const foe=layout.enemies.find(e=>e.cell===i);
   if(foe){glyph=foe.is_boss?"B":"G";ctx.fillStyle="#a85e62";}
   if(glyph){ctx.fillStyle="#f1f5e5";ctx.fillText(glyph,x+10,y+19);}
  }
  ctx.fillStyle="#daeddf";
  ctx.fillText("Ambience "+layout.ambient+" · light "+layout.light,252,59);
  ctx.fillText("Enemies "+layout.enemies.length+" · reserve "+layout.reserve,252,83);
  ctx.fillText("Traps "+layout.traps.length+" · treasure "+layout.chests.length,252,107);
  ctx.fillText("Paint then validate geometry and exact digest",252,144);
  return;
 }
 if(source.editor==="sandbox"){
  const world=source.layout,tiles=world.tiles||[];
  const ink={grass:"#397c58",forest:"#27824f",ridge:"#868477",
   sand:"#bbad7c",marsh:"#48859b",lake:"#387ac7"};
  ctx.fillText("Original sandbox 8×8 · physical stocks, homes, wildlife and soil",12,18);
  for(const t of tiles){
   const x=12+(t.id%8)*27,y=32+Math.floor(t.id/8)*24;
   ctx.fillStyle=ink[t.terrain]||"#506977";ctx.fillRect(x,y,25,22);
   ctx.fillStyle="#f1f3db";
   let symbol=t.id===world.spawn?"P":t.building?
    t.building.slice(0,1).toUpperCase():t.animal?"w":t.sapling?"s":t.crop?"c":"";
   ctx.fillText(symbol,x+7,y+15);
   if(t.fire){ctx.fillStyle="#f8a058";ctx.fillRect(x+20,y+1,4,5);}
   if(world.settler_spawns.includes(t.id)){
    ctx.strokeStyle="#a4e6ec";ctx.strokeRect(x+1,y+1,22,20);
   }
  }
  ctx.fillStyle="#d1e5e3";
  ctx.fillText("Region "+world.region_name,245,52);
  ctx.fillText("Initial funds "+world.starting_credits,245,75);
  ctx.fillText("Wildlife "+world.wildlife_population+
   " · settlers "+world.settler_spawns.length,245,98);
  ctx.fillText("Weather "+world.starting_weather,245,120);
  ctx.fillText("Select palette tool; click cells; revalidate digest",245,149);
  ctx.fillText("Other streamed regions generate from stable seed",245,174);
  return;
 }
 if(source.editor==="metroidvania"){
  const world=source.layout,rooms=world.rooms||[];
  const coords=i=>[12+(i%6)*56,32+Math.floor(i/6)*47];
  ctx.fillText("Original connected progression · 6×4 room layout (max 24)",12,18);
  for(const edge of world.passages){
   const [x,y]=coords(edge.a),[xx,yy]=coords(edge.b);
   ctx.strokeStyle=edge.gate?"#d28b72":"#80b9a8";
   ctx.lineWidth=2;ctx.beginPath();ctx.moveTo(x+24,y+19);
   ctx.lineTo(xx+24,yy+19);ctx.stroke();
  }
  for(const r of rooms){
   const [x,y]=coords(r.id);
   ctx.fillStyle=r.id===world.entry?"#2c8069":
    r.id===world.guardian?"#96474e":"#284e63";
   ctx.fillRect(x,y,49,42);
   ctx.fillStyle="#eef5df";ctx.fillText(String(r.id)+
    (r.ability?"*":"")+(r.anchor?" A":""),x+4,y+16);
   ctx.fillStyle="#c5e3e1";
   ctx.fillText(r.biome.slice(0,5),x+4,y+30);
  }
  ctx.fillStyle="#ccdfdf";
  ctx.fillText("Green = entry · red = boss · * = relic · A = fast shrine",355,57);
  ctx.fillText("Red links require a real collected traversal relic",355,84);
  ctx.fillText("Paint rooms; amend portal gate requirements only after review",355,111);
  ctx.fillText("No imported maps, scripts or unverifiable assets",355,137);
  return;
 }
 if(source.editor==="stealth"){
  const layout=source.layout;
  const step=23,ox=12,oy=31;
  const tile=(cell,color,label="")=>{
   const x=ox+cell[0]*step,y=oy+cell[1]*step;
   ctx.fillStyle=color;ctx.fillRect(x+1,y+1,step-2,step-2);
   if(label){ctx.fillStyle="#102637";ctx.fillText(label,x+5,y+16);}
  };
  ctx.fillText("Draw original 10×8 stealth terrain · review changes before playing",12,17);
  for(let y=0;y<8;y++)for(let x=0;x<10;x++)tile([x,y],"#284555");
  for(const p of layout.shadows)tile(p,"#3e6478");
  for(const p of layout.vents)tile(p,"#699bb0","v");
  for(const p of layout.walls)tile(p,"#7d8490");
  for(const p of layout.doors)tile(p,"#d09a83","D");
  for(const p of layout.cameras)tile(p,"#d8c17f","C");
  for(const p of layout.keycards)tile(p,"#f2d66f","K");
  for(const p of layout.intel)tile(p,"#b3a0e3","I");
  for(const r of layout.guard_routes)for(const p of r)tile(p,"#c88783","G");
  tile(layout.spawn,"#83ebc2","P");
  tile(layout.extraction,"#9cbfda","E");
  tile(layout.objective,"#e7c783","A");
  tile(layout.terminal,"#77b5db","T");
  ctx.fillStyle="#d5e7e8";
  ctx.fillText("Patrols "+layout.guard_routes.length+
    " · lighting "+layout.lighting+" · alarm budget "+layout.alarm_budget,256,57);
  ctx.fillText("Shadows, vents, guards, doors, intel and cameras are authored.",256,82);
  ctx.fillText("A revised grid is UNSIGNED until exact digest validation.",256,108);
  return;
 }
 if(source.editor==="city_builder"){
  const terrain=source.layout.terrain||[];
  const ink={plain:"#395c4b",forest:"#327b51",hill:"#837653",
   wetland:"#367a86",water:"#2662a5"};
  ctx.fillText("Original urban terrain 4×4 · select tool and click an authored cell",12,18);
  terrain.forEach((kind,i)=>{
   const x=16+(i%4)*108,y=34+Math.floor(i/4)*48;
   ctx.fillStyle=ink[kind]||"#555b66";
   ctx.fillRect(x,y,102,43);
   ctx.fillStyle="#f3f4ea";
   ctx.fillText((i===source.layout.road_hub?"★ ":"")+
    i+" "+kind.slice(0,8),x+6,y+23);
  });
  ctx.fillStyle="#bedbec";
  ctx.fillText("Aquifer "+source.layout.aquifer+
   " · lumber "+source.layout.timber_reserve+
   " · stone "+source.layout.stone_reserve+
   " · flood "+source.layout.flood_risk,12,245);
  return;
 }
 if(source.editor==="colony"){
  const zones=source.layout.districts||[];
  ctx.fillText("Colony geography draft · select a district and paint a resource rule",12,17);
  zones.forEach((d,i)=>{
   const x=12+(i%2)*230,y=33+Math.floor(i/2)*67;
   const start=i===source.layout.starting_district;
   ctx.fillStyle=start?"#236678":"#2d4556";
   ctx.fillRect(x,y,218,61);
   ctx.fillStyle="#ecf6f4";
   ctx.fillText((i+1)+" · "+d.biome+(start?" · START":""),x+7,y+17);
   ctx.fillStyle="#aee0c2";
   ctx.fillRect(x+7,y+22,Math.min(203,(d.food+d.water+d.wood+d.stone)/2),5);
   ctx.fillStyle="#e8dec4";
   ctx.fillText("wood "+d.wood+" · stone "+d.stone+
    " · food "+d.food+" · water "+d.water,x+7,y+45);
  });
  ctx.fillStyle="#b7cbd9";
  ctx.fillText("Raid "+source.layout.threat_level+
   " · caravan "+source.layout.caravan_stock+
   " · Validate edited layout before gameplay",12,245);
  return;
 }
 if(!shape){ctx.fillText("This system uses the detailed typed source editor.",12,24);return;}
 const [cols,rows]=shape;
 const step=Math.max(2,Math.min(23,Math.floor(448/cols),Math.floor(240/rows)));
 const ox=12,oy=31;const layout=source.layout;
 ctx.fillText("Draft scene grid · "+cols+"×"+rows+" · validate before staging",12,18);
 ctx.strokeStyle="#31586b";ctx.lineWidth=1;
 for(let x=0;x<=cols;x++){
  ctx.beginPath();ctx.moveTo(ox+x*step,oy);
  ctx.lineTo(ox+x*step,oy+rows*step);ctx.stroke();
 }
 for(let y=0;y<=rows;y++){
  ctx.beginPath();ctx.moveTo(ox,oy+y*step);
  ctx.lineTo(ox+cols*step,oy+y*step);ctx.stroke();
 }
 const draw=(value,kind)=>{
  if(!Array.isArray(value)||value.length!==2||!Number.isInteger(value[0])
     ||!Number.isInteger(value[1]))return;
  if(value[0]<0||value[1]<0||value[0]>=cols||value[1]>=rows)return;
  ctx.fillStyle=GRID_COLORS[kind]||"#cde6e1";
  ctx.fillRect(ox+value[0]*step+2,oy+value[1]*step+2,
               Math.max(1,step-4),Math.max(1,step-4));
 };
 if(source.editor==="shooter"){
  (layout.cover||[]).forEach(p=>draw(p,"cover"));
  (layout.medkits||[]).forEach(p=>draw(p,"medkits"));
  (layout.enemy_spawns||[]).forEach(p=>draw(p,"enemy_spawns"));
  draw(layout.extraction,"extraction");
  draw(layout.player_spawn,"player_spawn");
 }else if(source.editor==="tactics"){
  (layout.obstacles||[]).forEach(p=>draw(p,"obstacles"));
  (layout.enemy_spawns||[]).forEach(p=>draw(p,"enemy_spawns"));
  (layout.squad_spawns||[]).forEach(p=>draw(p,"squad_spawns"));
  draw(layout.objective,"objective");
 }else if(source.editor==="puzzle"){
  for(const kind of ["walls","targets","switches","doors","crates",
    "nodes","phase_gates"])(layout[kind]||[]).forEach(p=>draw(p,kind));
  (layout.portals||[]).forEach(pair=>pair.forEach(p=>draw(p,"portal_a")));
  draw(layout.exit,"exit");draw(layout.spawn,"spawn");
 }
}

function paintQuestDirectorCell(cell){
 const doc=JSON.parse($("advanced-scene-json").value);
 if(doc.editor!=="quest_director"||systemEditor().id!=="quest_director")
  throw Error("Original NPC quest scene must match current editor");
 if(!Number.isInteger(cell)||cell<0||cell>=49)
  throw Error("Original world paint coordinate must be inside 7×7");
 selectedQuestCell=cell;
 const m=doc.layout,tool=$("advanced-paint-tool").value,cfg=systemSettings();
 const site=m.sites.find(s=>s.cell===selectedQuestSite);
 const npc=m.npcs.find(n=>n.cell===selectedQuestNPC);
 if(tool==="obstacle_toggle"){
  m.obstacles=m.obstacles.includes(cell)?
     m.obstacles.filter(p=>p!==cell):[...m.obstacles,cell].sort((a,b)=>a-b);
 }else if(tool==="site_move"){
  const clicked=m.sites.find(s=>s.cell===cell);
  if(clicked)selectedQuestSite=clicked.id;
  else if(site)site.cell=cell;
  else throw Error("Select an authored site first");
 }else if(tool==="npc_move"){
  const clicked=m.npcs.find(n=>n.cell===cell);
  if(clicked)selectedQuestNPC=clicked.id;
  else if(npc)npc.cell=cell;
  else throw Error("Select an authored NPC first");
 }else if(tool==="player_spawn")m.player_spawn=cell;
 else if(tool==="site_integrity_up"){
  if(!site)throw Error("Select authored original site");
  site.integrity=Math.min(cfg.site_integrity,site.integrity+1);
 }else if(tool==="site_stock_up"){
  if(!site)throw Error("Select authored original finite site");
  site.stock=Math.min(cfg.site_stock,site.stock+1);
 }else if(tool==="npc_trust_up"){
  if(!npc)throw Error("Select authored original eyewitness");
  npc.trust=Math.min(cfg.starting_trust,npc.trust+1);
 }else if(tool==="npc_perception_up"){
  if(!npc)throw Error("Select authored original NPC");
  npc.perception=Math.min(cfg.npc_perception,npc.perception+1);
 }else if(tool==="site_kind_next"){
  if(!site)throw Error("Select original site");
  const kinds=["settlement","bridge","grove","archive"];
  site.kind=kinds[(kinds.indexOf(site.kind)+1)%kinds.length];
 }else if(tool==="npc_role_next"){
  if(!npc)throw Error("Select original resident");
  const kinds=["caretaker","scout","merchant","scribe"];
  npc.role=kinds[(kinds.indexOf(npc.role)+1)%kinds.length];
 }else if(tool==="climate_next"){
  const kinds=["temperate","rainforest","highland","steppe"];
  m.climate=kinds[(kinds.indexOf(m.climate)+1)%kinds.length];
 }else if(tool==="day_phase_next"){
  m.day_phase=(m.day_phase+1)%cfg.day_ticks;
 }else throw Error("Unregistered original world source change");
 $("advanced-scene-json").value=JSON.stringify(doc,null,2);
 renderSceneAuthoring();
 status("Original witnessed world changed. Validate all NPC identities, LOS, budgets, reachability and new source digest before play.");
}
function paintFightingCell(column,lane){
 const doc=JSON.parse($("advanced-scene-json").value);
 if(doc.editor!=="fighting"||systemEditor().id!=="fighting")
  throw Error("Signed original arena editing requires matching fighting document");
 const arena=doc.layout,tool=$("advanced-paint-tool").value;
 const cfg=systemSettings();
 if(column<0||column>=arena.width||lane<0||lane>=3)
  throw Error("Selected arena geometry lies outside authored bounds");
 const find=(array)=>array.findIndex(o=>o.x===column&&o.lane===lane);
 if(tool==="hazard_toggle"){
  const i=find(arena.hazards);
  if(i>=0)arena.hazards.splice(i,1);
  else arena.hazards.push({x:column,lane,damage:cfg.hazard_damage});
 }else if(tool==="hazard_damage_up"){
  const i=find(arena.hazards);
  if(i<0)throw Error("Author a real physical hazard before changing its damage");
  arena.hazards[i].damage=Math.min(cfg.hazard_damage,
                                  arena.hazards[i].damage+1);
 }else if(tool==="cover_toggle"){
  const i=find(arena.cover);
  if(i>=0)arena.cover.splice(i,1);
  else arena.cover.push({x:column,lane,hp:cfg.cover_health});
 }else if(tool==="cover_hp_up"){
  const i=find(arena.cover);
  if(i<0)throw Error("Author a real physical cover before modifying durability");
  arena.cover[i].hp=Math.min(cfg.cover_health,arena.cover[i].hp+1);
 }else if(tool==="player_spawn")arena.player_spawn=[column,lane];
 else if(tool==="enemy_spawn")arena.enemy_spawn=[column,lane];
 else if(tool==="theme_next"){
  const names=["tournament","sky_garden","industrial","mountain"];
  arena.theme=names[(names.indexOf(arena.theme)+1)%names.length];
 }else if(tool==="weather_next"){
  const names=["clear","rain","fog"];
  arena.weather=names[(names.indexOf(arena.weather)+1)%names.length];
 }else throw Error("Unregistered physical arena source tool");
 $("advanced-scene-json").value=JSON.stringify(doc,null,2);
 renderSceneAuthoring();
 status("Original fighting stage edited. Validate signed arena collisions, configured budgets, and precise source digest before play.");
}
function paintRhythmBeat(noteIndex){
 const scene=JSON.parse($("advanced-scene-json").value);
 if(scene.editor!=="rhythm"||systemEditor().id!=="rhythm")
  throw Error("Only matching original rhythm scene may be changed");
 const layout=scene.layout,settings=systemSettings();
 const n=layout.notes[noteIndex],tool=$("advanced-paint-tool").value;
 if(!n)throw Error("Beat selection is outside original authored chart");
 const kinds=["tap",...(settings.hold_notes?["hold"]:[]),
              ...(settings.slides?["slide"]:[]),
              ...(settings.chords?["chord"]:[]),
              ...(settings.mines?["mine"]:[])];
 if(tool==="lane_next"){
  n.lane=(n.lane+1)%layout.lanes;
  if(n.kind==="chord"&&n.partner===n.lane)
   n.partner=(n.lane+1)%layout.lanes;
 }else if(tool==="kind_next"){
  n.kind=kinds[(kinds.indexOf(n.kind)+1)%kinds.length];
  n.partner=n.kind==="chord"?(n.lane+1)%layout.lanes:null;
  n.duration=n.kind==="hold"?
    Math.round(settings.hold_length_beats*60000/layout.bpm):0;
 }else if(tool==="partner_next"){
  if(n.kind!=="chord")throw Error("Only real chords can modify a second lane");
  n.partner=(n.partner+1)%layout.lanes;
  if(n.partner===n.lane)n.partner=(n.partner+1)%layout.lanes;
 }else if(tool==="accent_toggle")n.accent=!n.accent;
 else if(tool==="timestamp_earlier"||tool==="timestamp_later"){
  n.at=Math.max(0,Math.round(Math.min(600000,n.at+
    (tool==="timestamp_earlier"?-5:5))));
 }else if(tool==="title_next"){
  layout.title="Original Rhythm Study "+String(noteIndex);
 }else if(tool==="original_meter_remark"){
  layout.title="Original "+layout.meter+"-meter Chart "+String(noteIndex);
 }else throw Error("Unsupported original beat-painting mode");
 $("advanced-scene-json").value=JSON.stringify(scene,null,2);
 renderSceneAuthoring();
 status("Original rhythm source edited. Validate lane, meter, note windows and content digest before replay.");
}
function paintRTSCell(cell){
 const doc=JSON.parse($("advanced-scene-json").value);
 if(doc.editor!=="rts"||systemEditor().id!=="rts")
  throw Error("Original RTS source painter requires matching editor");
 const m=doc.layout,tool=$("advanced-paint-tool").value,settings=systemSettings();
 if(!Number.isInteger(cell)||cell<0||cell>=64)
  throw Error("Original battlefield target must be a real bounded tile");
 const toggle=(rows)=>rows.includes(cell)?rows.filter(i=>i!==cell):
  [...rows,cell].sort((a,b)=>a-b);
 const bound=(v,step,max)=>Math.max(0,Math.min(max,v+step));
 if(tool==="obstacle_toggle")m.obstacles=toggle(m.obstacles);
 else if(["wood_node","ore_node","energy_node"].includes(tool)){
  let node=m.nodes.find(n=>n.cell===cell);
  const type=tool.split("_")[0];
  if(node){node.type=type;}
  else m.nodes.push({id:0,cell,type,stock:25});
  m.nodes.forEach((n,i)=>n.id=i);
 }else if(tool==="remove_node"){
  m.nodes=m.nodes.filter(n=>n.cell!==cell);
  m.nodes.forEach((n,i)=>n.id=i);
 }else if(["wood_plus","ore_plus","energy_plus"].includes(tool)){
  const type=tool.split("_")[0];
  const node=m.nodes.find(n=>n.cell===cell&&n.type===type);
  if(!node)throw Error("Original stock increase requires matching actual map node");
  node.stock=bound(node.stock,1,10000);
 }else if(["friendly_base","enemy_base","relay"].includes(tool))
  m[tool]=cell;
 else if(tool==="friendly_spawn")m.friendly_spawns=toggle(m.friendly_spawns);
 else if(tool==="enemy_spawn")m.enemy_spawns=toggle(m.enemy_spawns);
 else if(tool==="erase_spawn"){
  m.friendly_spawns=m.friendly_spawns.filter(i=>i!==cell);
  m.enemy_spawns=m.enemy_spawns.filter(i=>i!==cell);
 }else if(tool==="environment_next"){
  const a=["forest","desert","highland","rain"];
  m.environment=a[(a.indexOf(m.environment)+1)%a.length];
 }else if(tool==="starting_wood_up")m.starting_wood=bound(
  m.starting_wood,1,settings.starting_wood);
 else if(tool==="starting_ore_up")m.starting_ore=bound(
  m.starting_ore,1,settings.starting_ore);
 else if(tool==="starting_energy_up")m.starting_energy=bound(
  m.starting_energy,1,settings.starting_energy);
 else if(tool==="enemy_base_hp_up")m.enemy_base_health=bound(
  m.enemy_base_health,1,settings.enemy_base_health);
 else throw Error("Unregistered original authored strategy map operation");
 $("advanced-scene-json").value=JSON.stringify(doc,null,2);
 renderSceneAuthoring();
 status("Original strategy source mutated. Validate resource custody, route connectivity and scene digest before approval.");
}
function paintRoguelikeCell(index){
 const doc=JSON.parse($("advanced-scene-json").value);
 if(doc.editor!=="roguelike"||systemEditor().id!=="roguelike")
  throw Error("Original dungeon source must match the selected game");
 const map=doc.layout,tool=$("advanced-paint-tool").value;
 if(!Number.isInteger(index)||index<0||index>=36)
  throw Error("Authoring outside original dungeon grid denied");
 const toggle=(arr)=>arr.includes(index)?arr.filter(i=>i!==index):
   [...arr,index].sort((a,b)=>a-b);
 if(tool==="wall_toggle"){
  map.terrain[index]=map.terrain[index]==="wall"?"floor":"wall";
 }else if(tool==="trap_toggle")map.traps=toggle(map.traps);
 else if(tool==="chest_toggle")map.chests=toggle(map.chests);
 else if(["spawn","exit","shop","shrine"].includes(tool)){
  map[tool==="spawn"?"entry":tool]=index;
 }else if(tool==="enemy_toggle"){
  const current=map.enemies.find(e=>e.cell===index);
  if(current)map.enemies=map.enemies.filter(e=>e!==current);
  else{
   const cfg=systemSettings();
   map.enemies.push({id:0,kind:"sentinel",cell:index,
    hp:cfg.foe_health,max_hp:cfg.foe_health,
    attack:cfg.foe_attack,ranged:false,armor:0,
    status:"active",poison:0,stun:0,rewarded:false,is_boss:false});
  }
  map.enemies.forEach((e,i)=>e.id=i);
 }else if(tool.startsWith("enemy_")){
  const foe=map.enemies.find(e=>e.cell===index);
  if(!foe)throw Error("Select an existing authored opponent first");
  const health=tool.startsWith("enemy_health");
  const delta=tool.endsWith("_up")?1:-1;
  if(health){
   foe.hp=Math.max(1,Math.min(1000,foe.hp+delta));
   foe.max_hp=foe.hp;
  }else foe.attack=Math.max(0,Math.min(100,foe.attack+delta));
 }else if(tool==="toggle_elite"){
  const foe=map.enemies.find(e=>e.cell===index);
  if(!foe)throw Error("An original opponent is required");
  foe.is_boss=!foe.is_boss;
  foe.kind=foe.is_boss?"guardian":"sentinel";
 }else if(tool==="ambient_next"){
  const a=["crypt","glade","foundry","temple"];
  map.ambient=a[(a.indexOf(map.ambient)+1)%a.length];
 }else if(tool==="light_next"){
  const a=["torch","moon","mist"];
  map.light=a[(a.indexOf(map.light)+1)%a.length];
 }else if(tool==="trap_damage_up"||tool==="trap_damage_down"){
  map.hazard_damage=Math.max(0,Math.min(
   systemSettings().trap_damage,map.hazard_damage+
   (tool.endsWith("up")?1:-1)));
 }else if(tool==="reserve_up"||tool==="reserve_down"){
  map.reserve=Math.max(0,Math.min(
   systemSettings().encounters_per_floor,map.reserve+
   (tool.endsWith("up")?1:-1)));
 }else throw Error("Unregistered original roguelike scene operation");
 $("advanced-scene-json").value=JSON.stringify(doc,null,2);
 renderSceneAuthoring();
 status("Dungeon source changed. Validate original enemies, connected route and scene digest before approval.");
}
function paintSandboxCell(index){
 const doc=JSON.parse($("advanced-scene-json").value);
 if(doc.editor!=="sandbox"||systemEditor().id!=="sandbox")
  throw Error("Sandbox palette requires an original matching scene document");
 const layout=doc.layout,tile=layout.tiles[index],tool=$("advanced-paint-tool").value;
 if(!tile||!Number.isInteger(index)||index<0||index>=64)
  throw Error("Original geographic index outside authored 8×8 bounds");
 const limit=(key,delta,max=1000)=>tile[key]=Math.max(0,Math.min(max,tile[key]+delta));
 if(tool==="terrain_next"){
  const terrain=["grass","forest","ridge","sand","marsh","lake"];
  tile.terrain=terrain[(terrain.indexOf(tile.terrain)+1)%terrain.length];
  for(const k of ["wood","stone","clay","ore","water","fish","forage"])
   tile[k]=0;
  tile.sapling=0;
  if(tile.terrain==="forest"){tile.wood=6;tile.forage=2;}
  else if(tile.terrain==="ridge"){tile.stone=6;tile.ore=3;}
  else if(["marsh","lake"].includes(tile.terrain)){
   tile.water=9;tile.fish=5;tile.clay=tile.terrain==="marsh"?3:0;
  }else if(tile.terrain==="sand")tile.clay=3;
  else if(tile.terrain==="grass")tile.forage=3;
 }else if(/^(wood|stone|clay|ore|water|fish|forage)_(plus|minus)$/.test(tool)){
  const [key,mode]=tool.split("_");
  limit(key,mode==="plus"?1:-1);
 }else if(tool==="soil_toggle")tile.soil=tile.soil?0:1;
 else if(tool==="crop_up"||tool==="crop_down"){
  limit("crop",tool==="crop_up"?1:-1,8);
 }else if(tool==="moisture_plus")limit("moisture",1,10);
 else if(tool==="sapling_toggle"){
  tile.sapling=tile.sapling?0:1;
  if(tile.sapling){tile.terrain="forest";tile.wood=0;tile.crop=0;}
 }else if(tool==="animal_toggle"){
  tile.animal=tile.animal?0:1;if(!tile.animal)tile.tamed=false;
 }else if(tool==="tamed_toggle")tile.tamed=!tile.tamed;
 else if(tool==="fire_up"||tool==="fire_down"){
  limit("fire",tool==="fire_up"?1:-1,8);
 }else if(tool==="pollution_down")limit("pollution",-1);
 else if(tool==="structure_next"){
  const buildings=[null,"house","road","bridge","farm","well",
   "workshop","kiln","fence","beacon","generator","storehouse"];
  const next=buildings[(buildings.indexOf(tile.building)+1)%buildings.length];
  tile.building=next;tile.level=next?1:0;
 }else if(tool==="spawn")layout.spawn=index;
 else if(tool==="settler_toggle"){
  layout.settler_spawns=layout.settler_spawns.includes(index)?
   layout.settler_spawns.filter(p=>p!==index):
   [...layout.settler_spawns,index].sort((a,b)=>a-b);
 }else if(tool==="weather_next"){
  const modes=["clear","rain","drought","storm"];
  layout.starting_weather=modes[(modes.indexOf(layout.starting_weather)+1)%4];
 }else if(tool==="credits_plus"||tool==="credits_minus"){
  layout.starting_credits=Math.max(0,Math.min(
   systemSettings().build_budget,layout.starting_credits+
   (tool==="credits_plus"?10:-10)));
 }else throw Error("Unregistered original sandbox terrain authoring tool");
 layout.wildlife_population=layout.tiles.reduce((n,t)=>n+t.animal,0);
 $("advanced-scene-json").value=JSON.stringify(doc,null,2);
 renderSceneAuthoring();
 status("Sandbox source changed. Validate geography, stock identity and full original world digest before playable approval.");
}
function paintExplorationRoom(index){
 const source=JSON.parse($("advanced-scene-json").value);
 if(source.editor!=="metroidvania"||systemEditor().id!=="metroidvania")
  throw Error("Review an original authored world scene first");
 const world=source.layout,rooms=world.rooms||[],room=rooms[index];
 if(!room)throw Error("Requested original world room is not in authored graph");
 const tool=$("advanced-paint-tool").value;
 const bound=(value,step,low,high)=>Math.max(low,Math.min(high,value+step));
 if(tool==="biome_next"){
  const biomes=["moss","ruins","canopy","cavern","water","spire","ash"];
  room.biome=biomes[(biomes.indexOf(room.biome)+1)%biomes.length];
 }else if(tool==="foe_plus"||tool==="foe_minus")
  room.foe=bound(room.foe,tool==="foe_plus"?1:-1,0,1000);
 else if(tool==="hazard_up"||tool==="hazard_down")
  room.hazard=bound(room.hazard,tool==="hazard_up"?1:-1,0,20);
 else if(tool==="cache_plus"||tool==="cache_minus")
  room.cache=bound(room.cache,tool==="cache_plus"?1:-1,0,100);
 else if(tool==="ability_next"){
  const powers=[null,"dash","grapple","phase","swim","resonance"];
  const next=powers[(powers.indexOf(room.ability)+1)%powers.length];
  if(next)for(const r of rooms)if(r.id!==room.id&&r.ability===next)r.ability=null;
  room.ability=next;
 }else if(tool==="toggle_anchor")
  room.anchor=!room.anchor;
 else if(tool==="toggle_secret")
  room.secret=!room.secret;
 else if(tool==="set_entry")
  world.entry=index;
 else if(tool==="set_guardian")
  world.guardian=index;
 else if(tool==="gate_next"||tool==="toggle_break"){
  const passage=world.passages.find(e=>e.a===index-1&&e.b===index);
  if(!passage)throw Error("Choose a room with a sequential authored passage");
  if(tool==="toggle_break")passage.breakable=!passage.breakable;
  else{
   const powers=[null,...new Set(rooms.map(r=>r.ability).filter(Boolean))];
   passage.gate=powers[(powers.indexOf(passage.gate)+1)%powers.length];
  }
 }else throw Error("Unsupported original interconnected-world authoring tool");
 $("advanced-scene-json").value=JSON.stringify(source,null,2);
 renderSceneAuthoring();
 status("Original world edited. Validate full graph reachability, ability cycles, budget and digest before playing.");
}
function paintStealthCell([x,y]){
 const doc=JSON.parse($("advanced-scene-json").value);
 if(doc.editor!=="stealth"||doc.editor!==systemEditor().id)
  throw Error("Stealth scene must belong to the selected editor");
 const layout=doc.layout,tool=$("advanced-paint-tool").value,p=[x,y];
 const eq=q=>Array.isArray(q)&&q[0]===x&&q[1]===y;
 const arrays=["walls","shadows","vents","doors","cameras","keycards","intel"];
 if(arrays.includes(tool)||tool==="erase"||tool==="patrol_route")
  for(const key of arrays)layout[key]=layout[key].filter(q=>!eq(q));
 if(tool==="erase"){
  layout.guard_routes=layout.guard_routes.filter(r=>!r.some(eq));
 }else if(arrays.includes(tool)){
  layout[tool].push(p);
 }else if(["spawn","extraction","objective","terminal"].includes(tool)){
  layout[tool]=p;
 }else if(tool==="patrol_route"){
  const second=[x<9?x+1:x-1,y];
  layout.guard_routes=layout.guard_routes.filter(r=>!r.some(eq));
  layout.guard_routes.push([p,second]);
 }else if(tool==="lighting_next"){
  const choices=["day","night","storm"];
  layout.lighting=choices[(choices.indexOf(layout.lighting)+1)%choices.length];
 }else if(tool==="alarm_up"||tool==="alarm_down"){
  layout.alarm_budget=Math.min(30,Math.max(1,layout.alarm_budget+
   (tool==="alarm_up"?1:-1)));
 }else throw Error("Unknown original stealth scene painter tool");
 $("advanced-scene-json").value=JSON.stringify(doc,null,2);
 renderSceneAuthoring();
 status("Stealth geography changed. Validate entire route and scene digest before play.");
}
function paintCityCell(index){
 const document=JSON.parse($("advanced-scene-json").value);
 if(document.editor!=="city_builder"||document.editor!==systemEditor().id)
  throw Error("City terrain editing needs a matching source document");
 const layout=document.layout,tool=$("advanced-paint-tool").value;
 if(!Number.isInteger(index)||index<0||index>=16)
  throw Error("Original city cell must be within the reviewed 4×4 grid");
 if(tool.startsWith("terrain_")){
  layout.terrain[index]=tool.slice(8);
 }else if(tool==="road_hub"){
  if(["water","wetland"].includes(layout.terrain[index]))
   throw Error("Cannot relocate origin road hub onto water/wetland");
  layout.road_hub=index;
 }else if(tool==="aquifer_plus"||tool==="aquifer_minus"){
  layout.aquifer=Math.max(0,Math.min(100000,
   layout.aquifer+(tool.endsWith("plus")?10:-10)));
 }else if(tool==="flood_up"||tool==="flood_down"){
  layout.flood_risk=Math.max(0,Math.min(8,
   layout.flood_risk+(tool==="flood_up"?1:-1)));
 }else if(tool==="timber_plus"||tool==="stone_plus"){
  const field=tool==="timber_plus"?"timber_reserve":"stone_reserve";
  layout[field]=Math.min(100000,layout[field]+5);
 }else throw Error("Unknown registered original city map tool");
 // Source stays deliberately unapproved until exact backend revalidation.
 $("advanced-scene-json").value=JSON.stringify(document,null,2);
 renderSceneAuthoring();
 status("City geography changed: revalidate, inspect diff and authorize source before play.");
}
function paintColonyDistrict(index){
 const document=JSON.parse($("advanced-scene-json").value);
 if(document.editor!=="colony"||document.editor!==systemEditor().id)
  throw Error("Colony geography tool requires the matching editor");
 const layout=document.layout,sector=layout.districts[index];
 if(!sector)throw Error("Select one of the authored finite districts");
 const tool=$("advanced-paint-tool").value;
 const stocks=["wood","stone","food","water"];
 if(stocks.some(key=>tool===key+"_plus"||tool===key+"_minus")){
  const key=stocks.find(k=>tool.startsWith(k+"_"));
  const delta=tool.endsWith("_plus")?5:-5;
  sector[key]=Math.max(0,Math.min(100000,sector[key]+delta));
 }else if(tool==="biome_next"){
  const biomes=["river","forest","ridge","grassland","wetland","highland"];
  sector.biome=biomes[(biomes.indexOf(sector.biome)+1)%biomes.length];
 }else if(tool==="make_start"){
  layout.starting_district=index;
 }else if(tool==="threat_up"||tool==="threat_down"){
  layout.threat_level=Math.max(0,Math.min(8,
   layout.threat_level+(tool==="threat_up"?1:-1)));
 }else if(tool==="caravan_plus"||tool==="caravan_minus"){
  layout.caravan_stock=Math.max(0,Math.min(100000,
   layout.caravan_stock+(tool==="caravan_plus"?5:-5)));
 }else throw Error("Unknown original colony geography edit");
 // Deliberately retain stale digest until backend schema + rights review.
 $("advanced-scene-json").value=JSON.stringify(document,null,2);
 renderSceneAuthoring();
 status("Changed local colony source; Create / validate authored scene before playing or staging.");
}
function paintSceneCell(point){
 const text=$("advanced-scene-json").value.trim();
 const source=JSON.parse(text);
 if(source.editor!==systemEditor().id)throw Error("Scene identity differs from editor");
 const layout=source.layout,tool=$("advanced-paint-tool").value;
 const arrayKeys={
  shooter:["cover","medkits"],
  tactics:["obstacles"],puzzle:["walls","doors","switches","crates",
                               "targets","nodes","phase_gates"],
 };
 const arrays=arrayKeys[source.editor]||[];
 if(tool==="erase"){
  for(const key of arrays)layout[key]=layout[key].filter(
   cell=>cell[0]!==point[0]||cell[1]!==point[1]);
 }else if(tool==="medkit"||tool==="cover"||arrays.includes(tool)){
  const key=tool==="medkit"?"medkits":tool;
  const old=layout[key].findIndex(p=>p[0]===point[0]&&p[1]===point[1]);
  if(old>=0)layout[key].splice(old,1);
  else layout[key].push(point);
 }else if(tool==="player_spawn"||tool==="extraction"||
          tool==="spawn"||tool==="exit"||tool==="objective"){
  layout[tool]=point;
 }else if(tool.startsWith("enemy_spawn_")){
  layout.enemy_spawns[Number(tool.slice(-1))]=point;
 }else if(tool.startsWith("squad_")){
  layout.squad_spawns[Number(tool.slice(-1))]=point;
 }else if(tool.startsWith("enemy_")){
  layout.enemy_spawns[Number(tool.slice(-1))]=point;
 }else if(tool==="portal_a"||tool==="portal_b"){
  if(!layout.portals.length)
   layout.portals=[[[1,0],[Math.max(2,point[0]),point[1]]]];
  layout.portals[0][tool==="portal_a"?0:1]=point;
 }else throw Error("Select a supported paint action");
 // Keep stale checksum intentionally until canonical server validation:
 // gameplay and project source reviewer must reject unapproved modifications.
 $("advanced-scene-json").value=JSON.stringify(source,null,2);
 renderSceneAuthoring();
 status("Edited local scene cells. Use Create / validate authored scene to recalculate the reviewed digest.");
}
$("advanced-scene-grid").addEventListener("click",event=>{
 try{
  const text=$("advanced-scene-json").value.trim();
  if(!text)throw Error("Generate a scene document first");
  const doc=JSON.parse(text),shape=sceneGridShape(doc);
  const canvas=$("advanced-scene-grid"),rect=canvas.getBoundingClientRect();
  if(doc.editor==="quest_director"){
   const px=(event.clientX-rect.left)*canvas.width/rect.width;
   const py=(event.clientY-rect.top)*canvas.height/rect.height;
   const x=Math.floor((px-13)/29),y=Math.floor((py-39)/28);
   if(x<0||x>=7||y<0||y>=7||
      px>13+x*29+27||py>39+y*28+26)return;
   paintQuestDirectorCell(y*7+x);return;
  }
  if(doc.editor==="fighting"){
   const px=(event.clientX-rect.left)*canvas.width/rect.width;
   const py=(event.clientY-rect.top)*canvas.height/rect.height;
   const x=Math.floor((px-12)/23),y=Math.floor((py-41)/52);
   if(x<0||x>=doc.layout.width||y<0||y>=3||
     px>12+x*23+21||py>41+y*52+49)return;
   paintFightingCell(x,y);return;
  }
  if(doc.editor==="rhythm"){
   const px=(event.clientX-rect.left)*canvas.width/rect.width;
   const index=Math.floor((px-38)/28);
   if(index<0||index>=16)return;
   const absolute=Math.floor(selectedRhythmNote/16)*16+index;
   if(absolute>=doc.layout.notes.length)return;
   selectedRhythmNote=absolute;
   paintRhythmBeat(selectedRhythmNote);
   return;
  }
  if(doc.editor==="rts"){
   const px=(event.clientX-rect.left)*canvas.width/rect.width;
   const py=(event.clientY-rect.top)*canvas.height/rect.height;
   const x=Math.floor((px-14)/27),y=Math.floor((py-31)/25);
   if(x<0||x>=8||y<0||y>=8||
      px>14+x*27+25||py>31+y*25+23)return;
   paintRTSCell(y*8+x);
   return;
  }
  if(doc.editor==="roguelike"){
   const px=(event.clientX-rect.left)*canvas.width/rect.width;
   const py=(event.clientY-rect.top)*canvas.height/rect.height;
   const x=Math.floor((px-15)/34),y=Math.floor((py-32)/32);
   if(x<0||x>=6||y<0||y>=6||
      px>15+x*34+32||py>32+y*32+30)return;
   paintRoguelikeCell(y*6+x);
   return;
  }
  if(doc.editor==="sandbox"){
   const px=(event.clientX-rect.left)*canvas.width/rect.width;
   const py=(event.clientY-rect.top)*canvas.height/rect.height;
   const col=Math.floor((px-12)/27),row=Math.floor((py-32)/24);
   if(col<0||col>=8||row<0||row>=8||
      px>12+col*27+25||py>32+row*24+22)return;
   paintSandboxCell(row*8+col);
   return;
  }
  if(doc.editor==="metroidvania"){
   const px=(event.clientX-rect.left)*canvas.width/rect.width;
   const py=(event.clientY-rect.top)*canvas.height/rect.height;
   const col=Math.floor((px-12)/56),row=Math.floor((py-32)/47);
   if(col<0||col>=6||row<0||row>=4||
      px>12+col*56+49||py>32+row*47+42)return;
   const index=row*6+col;
   if(index>=doc.layout.rooms.length)return;
   paintExplorationRoom(index);
   return;
  }
  if(doc.editor==="stealth"){
   const px=(event.clientX-rect.left)*canvas.width/rect.width;
   const py=(event.clientY-rect.top)*canvas.height/rect.height;
   const x=Math.floor((px-12)/23),y=Math.floor((py-31)/23);
   if(x<0||x>=10||y<0||y>=8||
      px>12+x*23+23||py>31+y*23+23)return;
   paintStealthCell([x,y]);
   return;
  }
  if(doc.editor==="city_builder"){
   const px=(event.clientX-rect.left)*canvas.width/rect.width;
   const py=(event.clientY-rect.top)*canvas.height/rect.height;
   const col=Math.floor((px-16)/108),row=Math.floor((py-34)/48);
   if(col<0||col>3||row<0||row>3||px>16+col*108+102
      ||py>34+row*48+43)return;
   paintCityCell(row*4+col);
   return;
  }
  if(doc.editor==="colony"){
   const px=(event.clientX-rect.left)*canvas.width/rect.width;
   const py=(event.clientY-rect.top)*canvas.height/rect.height;
   const col=Math.floor((px-12)/230),row=Math.floor((py-33)/67);
   const index=row*2+col;
   if(col<0||col>1||row<0||row>2||px>12+col*230+218
      ||py>33+row*67+61||index>=doc.layout.districts.length)return;
   paintColonyDistrict(index);
   return;
  }
  if(!shape)throw Error("Graphical scene painting supports shooter, tactics and puzzles; colony uses the district designer");
  const [cols,rows]=shape;
  const scaleX=canvas.width/rect.width,scaleY=canvas.height/rect.height;
  const step=Math.max(2,Math.min(23,Math.floor(448/cols),Math.floor(240/rows)));
  const x=Math.floor(((event.clientX-rect.left)*scaleX-12)/step);
  const y=Math.floor(((event.clientY-rect.top)*scaleY-31)/step);
  if(x<0||x>=cols||y<0||y>=rows)return;
  paintSceneCell([x,y]);
 }catch(error){status("Visual authored-scene edit rejected: "+error.message);}
});
$("advanced-scene-json").addEventListener("input",renderSceneAuthoring);

async function reviewedSceneTemplate(){
 const editor=systemEditor().id,settings=systemSettings();
 const input=$("advanced-scene-json").value.trim();
 const authored=input?JSON.parse(input):null;
 const seedText=$("advanced-seed").value;
 if(!/^[0-9]+$/.test(seedText))throw Error("Advanced seed must be an integer");
 const values={
  editor,settings,seed:Number(seedText),
  scene_id:$("advanced-scene-id").value,
  layout:authored?authored.layout:null,
 };
 return api("/api/advanced-scene-template",values);
}
$("advanced-scene-template").addEventListener("click",async()=>{
 try{
  const template=await reviewedSceneTemplate();
  $("advanced-scene-json").value=JSON.stringify(template.scene,null,2);
  renderSceneAuthoring();
  status("Authored scene template validated. Modify terrain/regions, then validate again.");
 }catch(error){status("Authored scene rejected: "+error.message);}
});


$("world-progression-plan").addEventListener("click",async()=>{
 try{
  if(systemEditor().id!=="metroidvania")
   throw Error("Ability progression planning supports original interconnected worlds only");
  const json=$("advanced-scene-json").value.trim();
  if(!json)throw Error("Generate and validate an authored original world first");
  const response=await api("/api/world-plan",{
   scene:JSON.parse(json),settings:systemSettings(),
   max_states:50000,max_actions:128
  });
  const plan=response.plan;
  $("world-progression-proof").textContent=JSON.stringify({
   world_rooms:plan.regions,feasibility:plan.feasibility,
   route:plan.route,turns:plan.route_turn_count,
   nodes_visited:plan.search_nodes_explored,
   rehearsal_verified:plan.rehearsal_verified,
   source_mutated:plan.source_mutated,
   original_play_survivability_verified:plan.original_play_survivability_verified,
   native_execution_verified:plan.native_execution_verified,
   proof:plan.digest,
  },null,2);
  status(plan.rehearsal_verified?
   "Original world route reproduced against combat/ability rules with damage disabled. This is a diagnostic itinerary, not a guarantee of survival.":
   "No verified world route within current action and node budgets; adjust authored passages and validate again.");
 }catch(error){
  $("world-progression-proof").textContent="";
  status("Original world planner rejected: "+error.message);
 }
});
$("stealth-mission-plan").addEventListener("click",async()=>{
 try{
  if(systemEditor().id!=="stealth")
   throw Error("Spatial route planning supports the original stealth editor only");
  const raw=$("advanced-scene-json").value.trim();
  if(!raw)throw Error("Generate and validate an authored stealth scene first");
  const source=JSON.parse(raw);
  const output=await api("/api/stealth-plan",{
   scene:source,settings:systemSettings(),max_states:30000,max_depth:96
  });
  const plan=output.plan;
  $("stealth-plan-proof").textContent=JSON.stringify({
   mission:plan.mission,feasibility:plan.feasibility,
   route:plan.route,route_turn_count:plan.route_turn_count,
   states_explored:plan.states_explored,
   rehearsal_verified:plan.rehearsal_verified,
   original_source_mutated:plan.source_mutated,
   actual_security_evasion_verified:plan.actual_security_evasion_verified,
   proof_digest:plan.digest
  },null,2);
  status(plan.rehearsal_verified?
   "A bounded original route passed threat-free gameplay replay. Guards and cameras can still defeat it; review before use.":
   "No safe spatial feasibility proof within the bounded search. Improve original map or budget and revalidate.");
 }catch(error){
  $("stealth-plan-proof").textContent="";
  status("Stealth route planner rejected: "+error.message);
 }
});
$("advanced-puzzle-solve").addEventListener("click",async()=>{
 try{
  if(systemEditor().id!=="puzzle")
   throw Error("Proof search currently supports the advanced puzzle editor only");
  const template=await reviewedSceneTemplate();
  $("advanced-scene-json").value=JSON.stringify(template.scene,null,2);
  renderSceneAuthoring();
  const result=await api("/api/advanced-puzzle-solve",{
   scene:template.scene,settings:systemSettings(),
   max_states:12000,max_depth:96});
  const proof=result.proof;
  $("advanced-puzzle-proof").textContent=JSON.stringify({
   status:proof.status,states:proof.search_state_count,
   solution_steps:proof.shortest_steps,actions:proof.commands,
   proof_digest:proof.digest,
   authoritative_replay:proof.verified_by_authoritative_replay,
   hardware_certified:proof.hardware_certified,
  },null,2);
  status(proof.status==="solved"?
   "Puzzle solvability proved by actual gameplay replay":
   proof.status==="unsatisfiable_exhaustive"?
   "Exhaustive bounded puzzle state graph shows no solution":
   "Puzzle solvability remains unproven within bounded search");
 }catch(error){status("Original puzzle proof rejected: "+error.message);}
});
$("advanced-scene-stage").addEventListener("click",async()=>{
 try{
  if(!model||selectedTree!=="current"||selectedProject!==model.active)
   throw Error("An active current original project is required");
  const validated=await reviewedSceneTemplate();
  const file=validated.path;
  $("advanced-scene-json").value=JSON.stringify(validated.scene,null,2);
  renderSceneAuthoring();
  let prior={content:"",version:{
   sha256:"e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
   editable:true}};
  const list=await api("/api/files?tree=current&project="+encodeURIComponent(selectedProject));
  if(list.files.some(x=>x.path===file))
   prior=await api("/api/file?tree=current&project="+encodeURIComponent(selectedProject)+
                   "&path="+encodeURIComponent(file));
  loaded=prior;selectedFile=file;proposal=null;
  $("editor").value=validated.content;$("editor").readOnly=false;
  $("file-name").textContent="AUTHORED SCENE: current/"+selectedProject+"/"+file;
  $("hash").textContent="SHA-256 "+prior.version.sha256;
  $("reason").value="Review authored "+validated.scene.editor+
   " geometry and resource layout before local original-game commit";
  $("propose").disabled=false;$("commit").disabled=true;
  $("proposal").textContent="";
  diff();
  status("Authored scene staged: review source and commit. Its system configuration must already be approved.");
 }catch(error){status("Scene staging blocked: "+error.message);}
});
$("advanced-godot-export").addEventListener("click",async()=>{
 try{
  if(!advancedSession||(!["puzzle","platformer","deck_battler","shooter","tactics","tower_defense","racing","survival","farming","factory"].includes(advancedSession.editor)&&advancedSession.editor!=="colony"&&advancedSession.editor!=="physics"))
   throw Error("Native Godot export requires a verified advanced gameplay session in one of the supported playable native genres");
  if(!advancedSettings)
   throw Error("Original authored game settings must be available");
  const response=await api("/api/advanced-godot-package",{
   session:advancedSession,settings:advancedSettings});
  if(response.engine!==advancedSession.editor||response.gameplay_native_verified_by_this_request)
   throw Error("Unexpected native package certification claims");
  const raw=atob(response.zip_base64);
  if(raw.length>512000)throw Error("Native archive exceeds the offline source budget");
  const bytes=Uint8Array.from(raw,character=>character.charCodeAt(0));
  const blob=new Blob([bytes],{type:"application/zip"});
  const url=URL.createObjectURL(blob),link=document.createElement("a");
  link.href=url;link.download=response.file_name;
  document.body.append(link);link.click();link.remove();
  setTimeout(()=>URL.revokeObjectURL(url),0);
  status("Original Godot 4 project downloaded with verified Python gameplay proof. "+
   "Run Godot's native replay check before distribution.");
 }catch(error){status("Original Godot project export rejected: "+error.message);}
});
$("advanced-save").addEventListener("click",async()=>{
 try{
  if(!advancedSession)throw Error("Start a game to create a savegame");
  const result=await api("/api/advanced-save",{
   session:advancedSession,settings:advancedSettings});
  const source=JSON.stringify(result.savegame,null,2)+"\n";
  const blob=new Blob([source],{type:"application/json"});
  const url=URL.createObjectURL(blob),link=document.createElement("a");
  link.href=url;link.download="original-"+advancedSession.editor+"-game-save.json";
  document.body.append(link);link.click();link.remove();
  setTimeout(()=>URL.revokeObjectURL(url),0);
  status("Exported replay-verified portable savegame; it contains no executable source.");
 }catch(error){status("Savegame export rejected: "+error.message);}
});
$("advanced-load").addEventListener("change",async()=>{
 try{
  const file=$("advanced-load").files[0];
  if(!file)return;
  if(file.size>280000)throw Error("Game save file exceeds bounded import size");
  const data=JSON.parse(await file.text());
  const restored=await api("/api/advanced-load",{savegame:data});
  const session=restored.session;
  const select=$("system-kind");
  if(!systemCatalog.some(x=>x.id===session.editor))
   throw Error("Savegame editor is not available in this studio");
  select.value=session.editor;renderSystemControls();
  for(const field of systemEditor().fields){
   const input=[...$("system-fields").querySelectorAll("[data-system-field]")]
    .find(x=>x.dataset.systemField===field.key);
   if(field.kind==="bool")input.checked=restored.settings[field.key];
   else input.value=String(restored.settings[field.key]);
  }
  advancedEditor=session.editor;advancedSettings=restored.settings;
  advancedScene=session.scene;advancedCommands=session.actions.slice();
  $("advanced-seed").value=String(session.seed);
  $("advanced-scene-json").value=session.scene?JSON.stringify(session.scene,null,2):"";
  if(session.scene)$("advanced-scene-id").value=session.scene.scene_id;
  paintPalette();
  showAdvanced({session,available_actions:restored.available_actions});
  status("Savegame replay verified; exact original settings and command history restored.");
 }catch(error){status("Savegame import blocked: "+error.message);}
 finally{$("advanced-load").value="";}
});
$("advanced-start").addEventListener("click",startAdvanced);
$("advanced-physics-native").addEventListener("click",async()=>{
 try{
  // A local convenience flow; source validation remains entirely on the server.
  if($("system-kind").value!=="physics"){
   $("system-kind").value="physics";renderSystemControls();
  }
  if(systemEditor()?.id!=="physics")throw Error("Physics editor is not loaded");
  const preset={dimension:"2d",collision_geometry:"aabb",
                max_bodies:1,substeps:1,initial_battery:0};
  for(const [key,value] of Object.entries(preset)){
   const input=[...$("system-fields").querySelectorAll("[data-system-field]")]
    .find(node=>node.dataset.systemField===key);
   if(!input)throw Error("Missing native profile control "+key);
   if(input.type==="checkbox")input.checked=value;
   else input.value=String(value);
  }
  const settings=systemSettings();
  const seedRaw=$("advanced-seed").value;
  if(!/^[0-9]+$/.test(seedRaw))throw Error("Valid integer seed required");
  const seed=Number(seedRaw);
  const template=await api("/api/advanced-scene-template",{
   editor:"physics",settings,seed,scene_id:"native_physics_demo"
  });
  const layout=JSON.parse(JSON.stringify(template.scene.layout));
  layout.fixtures=[{"position":[430,900,0],
                    "half_size":[10,100,40],"layer":3}];
  const approved=await api("/api/advanced-scene-template",{
   editor:"physics",settings,seed,layout,scene_id:"native_physics_demo"
  });
  $("advanced-scene-json").value=JSON.stringify(approved.scene,null,2);
  advancedSession=null;
  await startAdvanced();
  if(!advancedSession || advancedSession.scene_digest!==approved.scene.digest)
   throw Error("Authenticated authored native profile was not replayed");
  status("Original native physics demo prepared and replayed. Export stays supervised; device validation is separate.");
 }catch(error){status("Native physics preparation blocked: "+error.message);}
});
let linkedCampaignTurns=[];
let linkedCampaignKey=null;
$("advanced-linked-reset").addEventListener("click",()=>{
 linkedCampaignTurns=[];linkedCampaignKey=null;
 $("advanced-linked-state").textContent="";
 status("Started a fresh opt-in physics-linked campaign");
});
$("advanced-linked-step").addEventListener("click",async()=>{
 try{
  if(!advancedSession || !advancedSession.scene ||
     !["platformer","racing","sandbox"].includes(advancedSession.editor))
   throw Error("A signed original platformer, racing or sandbox scene is required");
  const key=advancedSession.editor+":"+advancedSession.scene.digest+
            ":"+advancedSession.seed+":"+JSON.stringify(advancedSettings);
  if(linkedCampaignKey!==null && linkedCampaignKey!==key)
   throw Error("Original authored source changed; reset linked campaign first");
  const movement=$("advanced-linked-physical").value==="impact"?
   Array(8).fill("push:east"):["inspect"];
  const next=[...linkedCampaignTurns,{
   source_action:$("advanced-linked-action").value,
   physical_actions:movement,
   ability:$("advanced-linked-ability").value
  }];
  const answer=await api("/api/advanced-physics-linked",{
   editor:advancedSession.editor,scene:advancedSession.scene,
   settings:advancedSettings,turns:next
  });
  if(!answer.game || answer.source_file_mutated ||
     answer.game.source_scene_digest!==advancedSession.scene.digest)
   throw Error("Linked gameplay source receipt did not match signed original");
  linkedCampaignTurns=next;linkedCampaignKey=key;
  $("advanced-linked-state").textContent=JSON.stringify({
   mode:answer.game.editor,
   health_or_durability:answer.game.linked_state.vital,
   physical_impacts:answer.game.linked_state.physical_impacts,
   repairs:answer.game.linked_state.repair_kits,
   braces:answer.game.linked_state.brace_charges,
   outcome:answer.game.linked_state.game_status,
   source_gameplay_digest:answer.game.source_gameplay_digest,
   linked_head:answer.game.head_hash,
   original_save_unchanged:true,
  },null,2);
  if(answer.game.linked_state.terminal)
   $("advanced-linked-step").disabled=true;
  status("Played source and physical commands under separate audited authorities");
 }catch(error){status("Linked physical campaign blocked: "+error.message);}
});
$("advanced-interop-godot").addEventListener("click",async()=>{
 try{
  if(!advancedSession || !advancedSession.scene ||
     !["platformer","racing","sandbox"].includes(advancedSession.editor))
   throw Error("Signed source game required for native physics encounter");
  const response=await api("/api/advanced-interoperable-physics-godot",{
   session:advancedSession,settings:advancedSettings,
   physics_actions:Array(8).fill("push:east")
  });
  if(response.native_hardware_verified || response.native_renowned_genre_completed ||
     response.source_files_modified || response.publish_approved ||
     response.source_scene_digest!==advancedSession.scene.digest ||
     response.source_session_digest!==advancedSession.digest)
   throw Error("Native original physics source custody or release status mismatch");
  const raw=atob(response.zip_base64);
  if(raw.length>512000)throw Error("Reviewed original-game archive exceeds size budget");
  const bytes=Uint8Array.from(raw,c=>c.charCodeAt(0));
  const blob=new Blob([bytes],{type:"application/zip"});
  const url=URL.createObjectURL(blob),anchor=document.createElement("a");
  anchor.href=url;anchor.download=response.file_name;
  document.body.append(anchor);anchor.click();anchor.remove();
  setTimeout(()=>URL.revokeObjectURL(url),0);
  status("Signed original "+advancedSession.editor+
   " physical Godot encounter exported. It independently plays Physics only; native genre release requires a separate gate.");
 }catch(error){status("Native original physical encounter export blocked: "+error.message);}
});
$("advanced-npc-rule-editor").value=JSON.stringify([{
 id:"relief_when_witnessed",quest_id:0,
 when:{all:[
  {fact:"external_physical_origin",op:"eq",value:1},
  {fact:"source_eyewitnesses",op:"gte",value:1},
  {fact:"player_supplies",op:"gte",value:1},
  {any:[
   {fact:"site_integrity",op:"lte",value:11},
   {fact:"quest_active",op:"eq",value:1}
  ]}
 ]},
 do:"aid"
}],null,2);
async function runNPCConditionalRules(mode){
 if(!episodicLastProof || !episodicLastScene || !verifiedSourceEpisodes.length)
  throw Error("A signed original episodic NPC world must be replayed first");
 const authored=JSON.parse($("advanced-npc-rule-editor").value);
 if(!Array.isArray(authored) || !authored.length || authored.length>12)
  throw Error("Only one to twelve reviewed source NPC rules are permitted");
 const before=episodicLastProof.digest;
 const reply=await api("/api/advanced-npc-conditional-world",{
  episodes:verifiedSourceEpisodes,world_scene:episodicLastScene,
  rules:authored,mode
 });
 const proof=reply.report;
 if(!proof || reply.original_project_files_modified ||
    reply.native_hardware_verified || reply.automatic_promotion_approved ||
    proof.mode!==mode || proof.source_campaign_digest!==before ||
    proof.world_scene_digest!==episodicLastScene.digest ||
    proof.source_game_files_mutated || proof.unearned_npc_rewards_granted)
  throw Error("Typed original NPC conditional replay cannot be trusted");
 $("advanced-npc-rule-proof").textContent=JSON.stringify({
  mode:proof.mode,rule_evaluations:proof.rule_results,
  applied_earned_actions:proof.applied_effects,
  world_receipt:proof.final_campaign_digest,
  original_source_files_unchanged:true,
  no_automatic_ai_promotion:true
 },null,2);
 if(mode==="commit" && proof.applied_effects>0){
  verifiedSourceEpisodes=proof.episodes;
  episodicLastProof=null;
  verifiedInvestigationRoute=null;
  $("advanced-episodic-play").click();
  status("Reviewed original NPC rules committed earned commands and requested full world replay");
 }else{
  status(mode==="preview"?"Typed original NPC conditions evaluated without mutation":
    "No independently earned original world commands were applied");
 }
}
function refreshUnifiedGenreQueue(){
 $("advanced-genre-queue-list").textContent=JSON.stringify(
  verifiedGenreEvents.map((entry,index)=>({
   sequence:index+1,original_editor:entry.source_session.editor,
   source_session_digest:entry.source_session.digest,
   actual_action_indices:entry.bindings.map(b=>b.trace_index),
   mapped_sites:entry.bindings.map(b=>b.site_id)
  })),null,2);
}
$("advanced-unified-save-export").addEventListener("click",async()=>{
 try{
  if(!lastUnifiedGenreProof || !episodicLastScene ||
     !verifiedSourceEpisodes.length || !verifiedGenreEvents.length)
   throw Error("Replay a unified original multi-engine NPC world before saving");
  const reply=await api("/api/advanced-unified-genre-save-export",{
   physical_episodes:verifiedSourceEpisodes,
   genre_sessions:verifiedGenreEvents,
   world_scene:episodicLastScene,
   world_actions:unifiedWorldFollowups
  });
  const saved=reply.save;
  if(!saved || reply.original_project_mutated || reply.native_device_certified ||
     reply.automatic_publication ||
     saved.campaign_digest!==lastUnifiedGenreProof.digest)
   throw Error("Combined original source save identity mismatch");
  const json=JSON.stringify(saved);
  if(new TextEncoder().encode(json).length>3000000)
   throw Error("Combined source campaign exceeds 3 MB portable save budget");
  const blob=URL.createObjectURL(new Blob([json],{type:"application/json"}));
  const link=document.createElement("a");
  link.href=blob;
  link.download="original-unified-game-"+saved.digest.slice(0,12)+".json";
  document.body.append(link);link.click();link.remove();
  setTimeout(()=>URL.revokeObjectURL(blob),0);
  $("advanced-unified-save-receipt").textContent=JSON.stringify({
   verified_source_save_digest:saved.digest,
   physics_episodes:saved.physical_episode_count,
   original_genre_sessions:saved.genre_session_count,
   genuine_cross_genre_events:saved.genre_event_count,
   world_quest_actions:saved.world_actions.length,
   complete_replay_required:true,
   no_original_project_write:true
  },null,2);
  status("Portable combined original game/NPC source history exported without gameplay-state trust");
 }catch(error){status("Mixed original game save export rejected: "+error.message);}
});
$("advanced-unified-save-import").addEventListener("change",async()=>{
 try{
  const input=$("advanced-unified-save-import");
  const file=input.files?.[0];if(!file)return;
  if(file.size>3000000)throw Error("Oversized original combined save refused");
  const text=await file.text();
  if(new TextEncoder().encode(text).length>3000000)
   throw Error("Oversized source document rejected");
  const authored=JSON.parse(text);
  const imported=await api("/api/advanced-unified-genre-save-import",{
   save:authored
  });
  const verified=imported.restored;
  if(!verified?.verified || verified.save_digest!==authored.digest ||
     imported.original_project_mutated || imported.native_device_certified ||
     imported.automatic_publication ||
     verified.replayed_campaign.world_scene_digest!==verified.world_scene.digest)
   throw Error("Combined original physical and genre campaign could not independently replay");
  // Physical-world investigator routines need the authenticated PHYSICAL
  // prefix, not a forged or mis-typed unified genre-world state.
  const physical=await api("/api/advanced-physics-episodic-npc",{
   episodes:verified.physical_episodes,world_scene:verified.world_scene,
   world_settings:verified.world_settings
  });
  if(!physical.proof ||
     physical.proof.digest!==verified.replayed_campaign.physical_campaign_digest)
   throw Error("Restored original physical world prefix identity mismatch");
  verifiedSourceEpisodes=verified.physical_episodes;
  verifiedGenreEvents=verified.genre_sessions;
  episodicLastScene=verified.world_scene;
  episodicLastProof=physical.proof;
  unifiedWorldFollowups=verified.world_actions;
  lastUnifiedGenreProof=verified.replayed_campaign;
  verifiedInvestigationRoute=null;
  refreshUnifiedGenreQueue();
  refreshNPCQuestRouteChoices(episodicLastProof);
  drawNPCForensicMap(lastUnifiedGenreProof.world_state);
  $("advanced-unified-proof").textContent=JSON.stringify({
   verified_original_world:lastUnifiedGenreProof.world_state,
   genre_events:lastUnifiedGenreProof.genre_history,
   world_replay_digest:lastUnifiedGenreProof.digest,
   original_files_unchanged:true
  },null,2);
  $("advanced-unified-save-receipt").textContent=JSON.stringify({
   verified:true,save_digest:verified.save_digest,
   original_genre_sessions:verified.genre_sessions.length,
   remaining_genre_sessions:verified.remaining_genre_sessions,
   remaining_world_commands:verified.remaining_world_actions,
   reexecuted_all_original_games:true
  },null,2);
  status("Original physical and multi-genre NPC campaign independently restored from source inputs");
 }catch(error){status("Untrusted mixed original world save rejected: "+error.message);}
 finally{$("advanced-unified-save-import").value="";}
});
$("advanced-robustness-run").addEventListener("click",async()=>{
 try{
  if(!lastWorldWhatIfProof || !episodicLastScene ||
      !verifiedSourceEpisodes.length || !verifiedGenreEvents.length)
   throw Error("Replay an independently verified source-world what-if laboratory first");
  const count=Number($("advanced-robustness-contexts").value);
  if(!Number.isSafeInteger(count) || count<2 || count>3)
   throw Error("Only two or three independently signed world contexts allowed");
  const originalScene=episodicLastScene;
  const scenes=[originalScene];
  for(let offset=1;offset<count;offset++){
   const nextSeed=(Number(originalScene.seed)+offset)%2147483647;
   const result=await api("/api/advanced-scene-template",{
    editor:"quest_director",seed:nextSeed,
    scene_id:"robust_world_"+offset+"_"+lastWorldWhatIfProof.digest.slice(0,8)
   });
   if(!result.scene || result.scene.seed!==nextSeed ||
      result.scene.digest===originalScene.digest ||
      scenes.some(scene=>scene.digest===result.scene.digest))
    throw Error("Independent original world scene custody failed");
   scenes.push(result.scene);
  }
  const response=await api("/api/advanced-world-robustness",{
   physical_episodes:verifiedSourceEpisodes,
   genre_sessions:verifiedGenreEvents,
   world_scenes:scenes,
   whatif:lastWorldWhatIfProof,
   world_settings:interleavedWorldSettings,
   max_candidates:2
  });
  const proof=response.proof;
  if(!proof || response.original_games_mutated ||
     response.automatic_scenario_adopted ||
     response.population_generalization_proven ||
     response.native_hardware_certified ||
     proof.source_whatif_digest!==lastWorldWhatIfProof.digest ||
     proof.world_scenes.length!==scenes.length ||
     proof.world_scenes.some((id,i)=>id!==scenes[i].digest) ||
     proof.automatic_ai_weights_promoted ||
     proof.population_generalization_claimed)
   throw Error("Cross-context world comparison or original gameplay source invalid");
  lastWorldRobustnessProof=proof;
  $("advanced-robustness-proof").textContent=JSON.stringify({
    objective:proof.objective,
    actual_world_contexts:proof.world_scenes,
    measured_baselines:proof.baseline_worlds,
    fully_replayed_alternatives:proof.fully_replayed_candidates,
    rejected_alternatives:proof.rejected_candidates,
    best_bounded_worst_context_score:proof.selected_worst_observed_score,
    better_than_worst_baseline:proof.selected_beats_worst_baseline,
    not_worse_any_tested_world:proof.selected_is_noninferior_in_all_contexts,
    strictly_better_every_tested_world:
      proof.selected_strictly_improves_every_context,
    no_claim_about_other_worlds:true,
    no_automatic_gameplay_or_ai_promotion:true,
    replay_digest:proof.digest
  },null,2);
  status("Authenticated original NPC worlds compared across climate, source scene and witnessed outcomes");
 }catch(error){status("Cross-context NPC gameplay mirror refused: "+error.message);}
});
$("advanced-robustness-copy").addEventListener("click",()=>{
 try{
  const proof=lastWorldRobustnessProof;
  if(!proof || !proof.selected_scenario_id)
   throw Error("No cross-context authenticated candidate was observed");
  const scenario=proof.fully_replayed_candidates.find(
    x=>x.scenario_id===proof.selected_scenario_id);
  if(!scenario || !scenario.all_world_sources_independently_replayed ||
     !scenario.not_worse_in_any_authored_context)
   throw Error("Candidate worsened an authored context; explicit alternate review is required");
  $("advanced-interleave-editor").value=JSON.stringify(scenario.timeline,null,2);
  lastInterleavedProof=null;lastInterleavedTimeline=null;
  status("Non-inferior cross-context candidate copied only to authored editor; independently replay before use");
 }catch(error){status("Robust world scenario cannot be applied: "+error.message);}
});
$("advanced-whatif-run").addEventListener("click",async()=>{
 try{
  if(!episodicLastScene || !verifiedSourceEpisodes.length ||
     !verifiedGenreEvents.length)
   throw Error("Original physical and genre source sessions are required");
  const sourceTimeline=JSON.parse($("advanced-interleave-editor").value);
  if(!Array.isArray(sourceTimeline) ||
     sourceTimeline.length<2 || sourceTimeline.length>96)
   throw Error("An existing finite canonical interleaved event clock is required");
  const response=await api("/api/advanced-world-whatif-lab",{
   physical_episodes:verifiedSourceEpisodes,
   genre_sessions:verifiedGenreEvents,
   world_scene:episodicLastScene,
   timeline:sourceTimeline,
   world_settings:interleavedWorldSettings,
   objective:$("advanced-whatif-objective").value,
   max_depth:Number($("advanced-whatif-depth").value),
   max_attempts:12,max_accepted:6
  });
  const report=response.report;
  if(!report || response.original_game_files_mutated ||
     response.automatic_scenario_committed ||
     response.native_hardware_certified ||
     response.model_weight_promotion_approved ||
     report.source_games_changed || report.automatic_authoring_committed ||
     report.source_world_scene_digest!==episodicLastScene.digest ||
     report.objective!==$("advanced-whatif-objective").value ||
     report.baseline.timeline.length!==sourceTimeline.length)
   throw Error("Counterfactual source identity or original game proof rejected");
  lastWorldWhatIfProof=report;
  const select=$("advanced-whatif-select");
  select.replaceChildren();
  for(const alternative of report.accepted_scenarios){
   const item=document.createElement("option");
   item.value=alternative.scenario_id;
   item.textContent="Depth "+alternative.depth+" · "+
      alternative.scenario_id.slice(0,10)+
      (alternative.outperforms_baseline_on_selected_objective?
        " · measured better":" · valid alternative");
   select.append(item);
  }
  $("advanced-whatif-proof").textContent=JSON.stringify({
   authored_objective:report.objective,
   attempted:report.attempted_permutations,
   accepted:report.accepted_count,
   rejected:report.rejected_count,
   baseline_real_npc_world:report.baseline,
   actual_replayed_alternatives:report.accepted_scenarios,
   source_rejections:report.rejected_scenarios,
   selected_better_on_this_metric:
      report.selected_is_measurably_better_than_baseline,
   no_automatic_commit:true,
   no_automatic_model_promotion:true,
   original_source_digest:report.digest
  },null,2);
  status("Original-world adversarial alternatives independently replayed with bounded resource use");
 }catch(error){status("Adversarial original-game mirror refused: "+error.message);}
});
$("advanced-whatif-use").addEventListener("click",()=>{
 try{
  const value=$("advanced-whatif-select").value;
  if(!lastWorldWhatIfProof || !value)
   throw Error("Run an independently replayed source-world mirror first");
  const selected=lastWorldWhatIfProof.accepted_scenarios.find(
    scenario=>scenario.scenario_id===value);
  if(!selected || !selected.actually_replayed)
   throw Error("Cannot use an unverified hypothetical outcome");
  if(lastWorldWhatIfProof.baseline.timeline.length!==selected.timeline.length)
   throw Error("Authored source event capacity cannot change");
  // Applying means only editing the reviewable schedule. The canonical
  // game state changes ONLY after pressing the ordinary replay control.
  $("advanced-interleave-editor").value=JSON.stringify(selected.timeline,null,2);
  lastInterleavedProof=null;
  lastInterleavedTimeline=null;
  status("Source-authenticated candidate copied to editable timeline; independently replay it before use");
 }catch(error){status("Original-world candidate not applied: "+error.message);}
});
$("advanced-objective-goals").value=JSON.stringify([
 "credible_eyewitness_reach",
 "earned_quest_completions",
 "original_site_restoration",
 "finite_material_resilience"
],null,2);
$("advanced-objective-run").addEventListener("click",async()=>{
 try{
  if(!episodicLastScene || !verifiedSourceEpisodes.length ||
      !verifiedGenreEvents.length)
   throw Error("Review a real original physical and multi-genre source campaign first");
  const goalList=JSON.parse($("advanced-objective-goals").value);
  if(!Array.isArray(goalList) || goalList.length<1 ||
     goalList.length>4 || new Set(goalList).size!==goalList.length)
   throw Error("Choose one to four unique source-measurable original-game objectives");
  const timeline=JSON.parse($("advanced-interleave-editor").value);
  const maxCandidates=Number($("advanced-whatif-trial-limit").value);
  if(!Array.isArray(timeline) || timeline.length<2 || timeline.length>96 ||
     !Number.isSafeInteger(maxCandidates) ||
     maxCandidates<1 || maxCandidates>12)
   throw Error("The signed timeline and finite original experiment budget are required");
  const result=await api("/api/advanced-interleaved-objectives",{
   physical_episodes:verifiedSourceEpisodes,
   genre_sessions:verifiedGenreEvents,
   world_scene:episodicLastScene,
   timeline,world_settings:interleavedWorldSettings,
   goals:goalList,max_candidates:maxCandidates
  });
  const matrix=result.matrix;
  if(!matrix || result.source_project_files_mutated ||
     result.objective_ranking_auto_applied ||
     result.ai_model_promotion_approved ||
     matrix.original_project_files_changed ||
     matrix.automatic_game_event_application ||
     matrix.automatic_ai_weight_promotion ||
     JSON.stringify(matrix.goals)!==JSON.stringify(goalList) ||
     matrix.max_candidates!==maxCandidates ||
     matrix.candidate_count!==matrix.candidate_results.length)
   throw Error("Actual game objectives were not independently measured and replayed");
  $("advanced-objective-proof").textContent=JSON.stringify({
   original_baseline_source:matrix.baseline_campaign_digest,
   ordered_authored_goals:matrix.goals,
   real_baseline_stats:matrix.baseline_metrics,
   source_replayed_cases:matrix.verified_valid_candidates,
   independently_better_cases:matrix.verified_strict_improvements,
   actual_story_tradeoffs:matrix.observed_tradeoffs,
   invalid_trials_excluded:matrix.rejected_source_timelines,
   measured_alternatives:matrix.candidate_results.map(c=>({
    index:c.candidate_index,
    source_replay_valid:c.valid,
    objective_classification:c.classification,
    independently_measured_metrics:c.measured_metrics,
    strict_baseline_deltas:c.goal_deltas,
    pareto_nondominated:c.pareto_frontier
   })),
   suggested_only_if_strictly_better:matrix.suggested_candidate_index,
   candidate_selection_requires_separate_manual_whatif_review:true,
   auto_promotion:false,
   original_source_files_untouched:true
  },null,2);
  status("Original NPC game objectives measured against independently re-executed worlds; ranking does not alter game state");
 }catch(error){status("Source-measured NPC design goals rejected: "+error.message);}
});
$("advanced-whatif-run").addEventListener("click",async()=>{
 try{
  if(!episodicLastScene || !verifiedSourceEpisodes.length ||
     !verifiedGenreEvents.length)
   throw Error("Adversarial world comparisons need real original physics and genre source sessions");
  const authored=JSON.parse($("advanced-interleave-editor").value);
  const maxCandidates=Number($("advanced-whatif-trial-limit").value);
  if(!Array.isArray(authored) || authored.length<2 || authored.length>96 ||
     !Number.isSafeInteger(maxCandidates) || maxCandidates<1 ||
     maxCandidates>12)
   throw Error("Two to 96 source events and one to 12 trials are required");
  const response=await api("/api/advanced-interleaved-counterfactual",{
   physical_episodes:verifiedSourceEpisodes,
   genre_sessions:verifiedGenreEvents,
   world_scene:episodicLastScene,
   timeline:authored,
   world_settings:interleavedWorldSettings,
   max_candidates:maxCandidates
  });
  const proof=response.analysis;
  if(!proof || response.original_project_files_mutated ||
     response.counterfactuals_promoted || response.native_all_engines_certified ||
     proof.source_game_files_modified ||
     proof.unearned_world_rewards_applied ||
     proof.automatic_ai_weight_promotion ||
     proof.max_candidates!==maxCandidates ||
     proof.total_trials!==proof.candidates.length)
   throw Error("Counterfactual original game proof was not source-authorized");
  lastWhatIfReport=proof;
  const select=$("advanced-whatif-candidate");
  select.replaceChildren();
  for(const candidate of proof.candidates){
   const option=document.createElement("option");
   option.value=String(candidate.candidate_index);
   option.textContent="Trial "+candidate.candidate_index+
    " · "+(candidate.valid?"Replay passed":"Invalid source order")+
    " · "+candidate.changed_dimension_count+" changed dimensions";
   option.disabled=!candidate.valid;
   select.append(option);
  }
  $("advanced-whatif-proof").textContent=JSON.stringify({
   baseline_game:proof.baseline_campaign_digest,
   actual_world_tick:proof.baseline_world_tick,
   independently_replayed:proof.valid_replayed_trials,
   rejected_invalid_timelines:proof.invalid_trials,
   materially_different_worlds:proof.causally_changed_trials,
   actual_verified_differences:proof.candidates.map(x=>({
    id:x.candidate_index,valid:x.valid,
    edited_positions:x.swapped_original_positions,
    actual_world_dimensions_changed:x.changed_dimensions,
    original_resource_memory_quest_deltas:x.verified_deltas,
    unique_replay_digest:x.candidate_digest
   })),
   source_inputs_untouched:true,
   automatic_ai_learning_promotion:false
  },null,2);
  status("Independent original game world what-if trials completed; invalid source orders never earn advancement");
 }catch(error){lastWhatIfReport=null;
  status("Original causal world comparison rejected: "+error.message);}
});
$("advanced-whatif-use").addEventListener("click",()=>{
 try{
  if(!lastWhatIfReport)throw Error("Run a new independent what-if comparison");
  const chosen=Number($("advanced-whatif-candidate").value);
  if(!Number.isSafeInteger(chosen))throw Error("Choose a verified original game scenario");
  const candidate=lastWhatIfReport.candidates.find(x=>
   x.candidate_index===chosen && x.valid);
  if(!candidate || !candidate.candidate_digest)
   throw Error("Invalid alternative cannot be authored as a real game-world success");
  $("advanced-interleave-editor").value=JSON.stringify(
   candidate.authored_timeline,null,2);
  lastInterleavedProof=null;
  lastInterleavedTimeline=null;
  $("advanced-interleave-save-proof").textContent="";
  status("Authenticated what-if source order copied for review; run the complete original game timeline to approve it");
 }catch(error){status("Unverified game counterfactual not applied: "+error.message);}
});
$("advanced-mirror-build").addEventListener("click",()=>{
 try{
  if(!lastInterleavedTimeline || !lastInterleavedProof)
   throw Error("Replay a source-authenticated original world clock first");
  const original=JSON.parse(JSON.stringify(lastInterleavedTimeline));
  if(original.length<2 || original.some((event,index)=>event.at!==index))
   throw Error("Automatic counterfactual draft only supports single-tick entries; author other schedules manually");
  const alternate=JSON.parse(JSON.stringify(original));
  let swapped=false;
  for(let i=0;i<alternate.length-1;i++){
   const a=alternate[i],b=alternate[i+1];
   if((a.lane==="physical"&&b.lane==="genre") ||
      (a.lane==="genre"&&b.lane==="physical")){
    alternate[i]=b;alternate[i+1]=a;
    swapped=true;break;
   }
  }
  if(!swapped)throw Error("Need neighboring original physical and genre events to form a valid comparison");
  alternate.forEach((event,index)=>{event.at=index;});
  const candidates=[
   {name:"original_order",timeline:original},
   {name:"alternate_order",timeline:alternate}
  ];
  $("advanced-mirror-scenarios").value=JSON.stringify(candidates,null,2);
  status("Two independent, source-identical event orders ready for reviewed adversarial replay");
 }catch(error){status("Original counterfactual proposal blocked: "+error.message);}
});
$("advanced-mirror-run").addEventListener("click",async()=>{
 try{
  if(!episodicLastScene || !verifiedSourceEpisodes.length ||
     !verifiedGenreEvents.length)
   throw Error("Signed original physical plus genre sources are required");
  const candidates=JSON.parse($("advanced-mirror-scenarios").value);
  if(!Array.isArray(candidates) || candidates.length<2 || candidates.length>6)
   throw Error("Compare two to six bounded authored source schedules");
  const goal=$("advanced-mirror-objective").value;
  const response=await api("/api/advanced-interleaved-counterfactuals",{
   physical_episodes:verifiedSourceEpisodes,
   genre_sessions:verifiedGenreEvents,
   world_scene:episodicLastScene,
   world_settings:interleavedWorldSettings,
   scenarios:candidates,objective:goal
  });
  const proof=response.report;
  if(!proof || response.original_files_changed ||
     response.automatic_ai_promotion || response.native_full_world_certified ||
     response.universal_game_quality_approved ||
     proof.source_world_scene_digest!==episodicLastScene.digest ||
     proof.objective!==goal || proof.scenario_count!==candidates.length ||
     proof.original_project_mutated || proof.automatic_model_training_approved ||
     proof.universal_game_quality_claimed)
   throw Error("Counterfactual world or precise objective failed independent custody");
  $("advanced-mirror-proof").textContent=JSON.stringify({
   comparison_objective:proof.objective,
   baseline:proof.baseline_scenario,
   objective_only_ranking:proof.ranking_for_this_metric_only,
   source_verified_scenarios:proof.scenarios.map(x=>({
    scenario:x.scenario,
    signed_original_world:x.verified_campaign_digest,
    metric:x.metric,
    factual_change_from_baseline:x.difference_from_first,
    independently_replayed_source_counts:{
     physics:x.physical_event_count,genre:x.genre_event_count,
     world_commands:x.world_command_count
    }
   })),
   final_evidence_digest:proof.digest,
   universal_quality_or_ai_model_improvement_proven:false,
   original_project_files_unchanged:true
  },null,2);
  status("Verified original counterfactual outcomes compared for a narrow explicit world metric");
 }catch(error){status("Adversarial original-world mirror rejected: "+error.message);}
});
$("advanced-interleave-save-export").addEventListener("click",async()=>{
 try{
  if(!lastInterleavedProof || !lastInterleavedTimeline || !episodicLastScene)
   throw Error("Run an authenticated original world clock before exporting");
  const response=await api("/api/advanced-interleaved-save-export",{
   physical_episodes:verifiedSourceEpisodes,
   genre_sessions:verifiedGenreEvents,
   world_scene:episodicLastScene,
   timeline:lastInterleavedTimeline,
   world_settings:interleavedWorldSettings
  });
  const saved=response.save;
  if(!saved || saved.campaign_digest!==lastInterleavedProof.digest ||
     response.original_files_changed || response.native_full_world_certified ||
     response.automatic_publishing_approved)
   throw Error("World clock save does not match independently verified source game");
  const encoded=JSON.stringify(saved);
  if(new TextEncoder().encode(encoded).length>4000000)
   throw Error("Original world clock exceeds the portable save limit");
  const url=URL.createObjectURL(new Blob([encoded],{type:"application/json"}));
  const link=document.createElement("a");
  link.href=url;
  link.download="original-interleaved-game-"+saved.digest.slice(0,12)+".json";
  document.body.append(link);link.click();link.remove();
  setTimeout(()=>URL.revokeObjectURL(url),0);
  $("advanced-interleave-save-proof").textContent=JSON.stringify({
   verified_save_digest:saved.digest,
   original_world_clock:saved.world_tick,
   physics_incidents:saved.true_physics_event_count,
   genre_achievements:saved.true_genre_event_count,
   world_action_count:saved.world_actions,
   complete_original_source_replay_required:true,
   original_files_unchanged:true
  },null,2);
  status("Interleaved original source game saved; mutable rewards and eyewitnesses must be reconstructed");
 }catch(error){status("Interleaved source save export blocked: "+error.message);}
});
$("advanced-interleave-save-import").addEventListener("change",async()=>{
 try{
  const control=$("advanced-interleave-save-import");
  const file=control.files?.[0];if(!file)return;
  if(file.size>4000000)throw Error("Original source save exceeds 4 MB");
  const raw=await file.text();
  if(new TextEncoder().encode(raw).length>4000000)
   throw Error("Original source save too large");
  const authored=JSON.parse(raw);
  const response=await api("/api/advanced-interleaved-save-import",{save:authored});
  const restored=response.restored;
  if(!restored?.verified || restored.save_digest!==authored.digest ||
     response.original_files_changed || response.native_full_world_certified ||
     response.automatic_publishing_approved ||
     restored.replayed_world.world_scene_digest!==restored.world_scene.digest)
   throw Error("Interleaved NPC world could not be independently source-replayed");
  // Do not impersonate a stand-alone physical-only NPC-world proof:
  // this source includes extra independently earned genre interventions.
  verifiedSourceEpisodes=restored.physical_episodes;
  verifiedGenreEvents=restored.genre_sessions;
  episodicLastScene=restored.world_scene;
  interleavedWorldSettings=restored.world_settings;
  episodicLastProof=null;
  lastUnifiedGenreProof=null;
  verifiedInvestigationRoute=null;
  lastInterleavedProof=restored.replayed_world;
  lastInterleavedTimeline=restored.timeline;
  $("advanced-interleave-editor").value=JSON.stringify(restored.timeline,null,2);
  $("advanced-interleave-proof").textContent=JSON.stringify({
   source_clock:restored.replayed_world.timeline,
   current_world_state:restored.replayed_world.world_state,
   verified_campaign_digest:restored.replayed_world.digest
  },null,2);
  $("advanced-interleave-save-proof").textContent=JSON.stringify({
   verified:true,
   complete_original_game_replay:true,
   save_digest:restored.save_digest,
   remaining_clock_entries:restored.remaining_timeline_entries,
   source_games_untouched:true
  },null,2);
  refreshUnifiedGenreQueue();
  drawNPCForensicMap(restored.replayed_world.world_state);
  status("Authentic original multi-engine NPC world and event clock fully reconstructed from imported source inputs");
 }catch(error){status("Untrusted interleaved original source save rejected: "+error.message);}
 finally{$("advanced-interleave-save-import").value="";}
});
function clearWorldCounterfactuals(){
 lastCounterfactualReport=null;
 $("advanced-counterfactual-choice").replaceChildren();
 $("advanced-counterfactual-report").textContent="";
}
$("advanced-counterfactual-generate").addEventListener("click",()=>{
 try{
  if(!lastInterleavedProof || !lastInterleavedTimeline)
   throw Error("Independently replay an original world-clock baseline first");
  const authored=JSON.parse($("advanced-interleave-editor").value);
  if(JSON.stringify(authored)!==JSON.stringify(lastInterleavedTimeline))
   throw Error("Replay changed world-clock baseline before researching variants");
  const cases=[],known=new Set([JSON.stringify(authored)]);
  for(let i=0;i<authored.length-1 && cases.length<10;i++){
   const left=authored[i],right=authored[i+1];
   if(left.lane==="world" && right.lane==="world")continue;
   if(left.lane===right.lane && left.lane!=="world" &&
      left.source_index===right.source_index)continue;
   const candidate=JSON.parse(JSON.stringify(authored));
   const a=candidate[i];candidate[i]=candidate[i+1];candidate[i+1]=a;
   candidate[i].at=i;candidate[i+1].at=i+1;
   const key=JSON.stringify(candidate);
   if(known.has(key))continue;
   known.add(key);
   cases.push({id:"adjacent_"+String(i).padStart(2,"0")+"_"+
                    String(i+1).padStart(2,"0"),timeline:candidate});
  }
  if(!cases.length)throw Error("There are no reviewable adjacent alternative source orders");
  $("advanced-counterfactual-cases").value=JSON.stringify(cases,null,2);
  clearWorldCounterfactuals();
  status("Authored original source event alternatives prepared; no world state changed");
 }catch(error){status("What-if source generation blocked: "+error.message);}
});
$("advanced-counterfactual-run").addEventListener("click",async()=>{
 try{
  if(!lastInterleavedProof || !lastInterleavedTimeline ||
     !episodicLastScene)
   throw Error("Original interleaved baseline requires signed independent replay");
  if(JSON.stringify(JSON.parse($("advanced-interleave-editor").value))!==
     JSON.stringify(lastInterleavedTimeline))
   throw Error("Original baseline changed; run the world clock again before comparison");
  const variants=JSON.parse($("advanced-counterfactual-cases").value);
  if(!Array.isArray(variants)||!variants.length||variants.length>10)
   throw Error("Only one to ten bounded authored game alternatives are accepted");
  const response=await api("/api/advanced-world-counterfactuals",{
   physical_episodes:verifiedSourceEpisodes,
   genre_sessions:verifiedGenreEvents,
   world_scene:episodicLastScene,
   timeline:lastInterleavedTimeline,
   world_settings:interleavedWorldSettings,
   cases:variants,
   objective:$("advanced-counterfactual-objective").value
  });
  const proof=response.report;
  if(!proof || response.original_source_projects_changed ||
     response.automatic_scenario_accepted ||
     response.native_hardware_certified ||
     response.automatic_ai_weight_promotion ||
     proof.baseline_world_digest!==lastInterleavedProof.digest ||
     proof.candidate_count!==variants.length ||
     proof.original_game_files_changed ||
     proof.automatic_world_promotion_approved)
   throw Error("Independent world what-if source and outcome proof rejected");
  lastCounterfactualReport=proof;
  const choice=$("advanced-counterfactual-choice");
  choice.replaceChildren();
  for(const trial of proof.experiments){
   if(trial.status!=="valid")continue;
   const opt=document.createElement("option");
   opt.value=trial.id;
   opt.textContent=trial.id+" · "+proof.objective+
     "="+trial.measured_score;
   choice.append(opt);
  }
  $("advanced-counterfactual-report").textContent=JSON.stringify({
   original_baseline:proof.baseline_world,
   author_objective:proof.objective,
   objective_favorite:proof.objective_favorite,
   confirmed_candidates:proof.valid_count,
   rejected_by_original_rules:proof.rejected_count,
   actual_world_comparisons:proof.experiments.map(e=>({
    id:e.id,status:e.status,reason:e.reason,
    measured_score:e.measured_score,
    differences:e.difference_from_baseline,
    original_world_digest:e.actual_world_digest
   })),
   no_automatic_selection:true,source_replay_digest:proof.digest
  },null,2);
  status("Actual original world outcomes compared; all rejected hypotheses remain rejected");
 }catch(error){status("Original world counterfactual review failed: "+error.message);}
});
$("advanced-counterfactual-select").addEventListener("click",()=>{
 try{
  if(!lastCounterfactualReport || !lastInterleavedProof ||
     lastCounterfactualReport.baseline_world_digest!==lastInterleavedProof.digest)
   throw Error("Replay a fresh authenticated source comparison before selecting");
  const id=$("advanced-counterfactual-choice").value;
  const trial=lastCounterfactualReport.experiments.find(
    e=>e.id===id && e.status==="valid" && e.actual_world_digest);
  if(!trial)throw Error("Only an independently replayed valid original world may be selected");
  $("advanced-interleave-editor").value=JSON.stringify(trial.timeline,null,2);
  // Selection edits the authored plan, NOT actual NPC memories or rewards.
  // The creator must explicitly execute the canonical world-clock replay.
  lastInterleavedProof=null;
  lastInterleavedTimeline=null;
  clearWorldCounterfactuals();
  status("Valid alternative selected as draft only; replay the original world clock to enact it");
 }catch(error){status("Counterfactual source selection rejected: "+error.message);}
});
$("advanced-interleave-build").addEventListener("click",async()=>{
 try{
  if(!episodicLastScene || !verifiedSourceEpisodes.length ||
     !verifiedGenreEvents.length)
   throw Error("Requires a signed physical campaign and verified source genre sessions");
  if(verifiedSourceEpisodes.some(e=>e.world_actions.length))
   throw Error("Interleaving requires new source episodes without already-played NPC actions");
  const physical=[],genre=[];
  for(const [index,spec] of verifiedSourceEpisodes.entries()){
   const response=await api("/api/advanced-physics-multi-npc",{
    session:spec.source_session,
    settings:spec.source_settings,
    world_scene:episodicLastScene,
    physics_actions:spec.physics_actions,
    bindings:spec.bindings,
    world_actions:[]
   });
   if(!response.proof || response.proof.source_session_digest!==spec.source_session.digest ||
      response.proof.quest_scene_digest!==episodicLastScene.digest)
    throw Error("Unverified original physics episode "+index);
   physical.push(response.proof.incidents.map((_,event_index)=>({
    lane:"physical",source_index:index,event_index
   })));
  }
  for(const [index,spec] of verifiedGenreEvents.entries()){
   const response=await api("/api/advanced-cross-genre-npc-world",{
    session:spec.source_session,source_settings:spec.source_settings,
    world_scene:episodicLastScene,bindings:spec.bindings,world_actions:[]
   });
   if(!response.report ||
      response.report.source_session_digest!==spec.source_session.digest ||
      response.report.world_scene_digest!==episodicLastScene.digest)
    throw Error("Unverified original genre session "+index);
   genre.push(response.report.earned_events.map((_,event_index)=>({
    lane:"genre",source_index:index,event_index
   })));
  }
  const schedule=[];
  let remaining=true;
  while(remaining){
   remaining=false;
   for(const queue of [...physical,...genre]){
    if(queue.length){
     schedule.push({at:schedule.length,...queue.shift()});remaining=true;
    }
   }
  }
  if(!schedule.length || schedule.length>96)
   throw Error("No original causal game events or timeline source budget exceeded");
  $("advanced-interleave-editor").value=JSON.stringify(schedule,null,2);
  $("advanced-interleave-proof").textContent=JSON.stringify({
   original_physical_episodes:physical.length,
   original_genre_sessions:genre.length,
   authored_entries:schedule.length,
   clock:"source-verified NPC world ticks",
   edits:"Each scheduled event consumes one true game-world tick; insert world wait actions to advance time"
  },null,2);
  status("Authenticated cross-engine source events prepared for reviewed timeline authoring");
 }catch(error){status("Interleaved original game draft rejected: "+error.message);}
});
function showParetoWorldWhatIfQueue(){
 $("advanced-pareto-whatif-queue").textContent=JSON.stringify(
  reviewedParetoWorldWhatIfScenarios.map((s,index)=>({
   sequence:index,source_name:s.id,authored_events:s.timeline.length,
   first_lanes:s.timeline.slice(0,6).map(e=>e.lane)
  })),null,2);
}
$("advanced-pareto-whatif-baseline").addEventListener("click",()=>{
 try{
  if(!lastInterleavedProof || !lastInterleavedTimeline)
   throw Error("Replay the original world clock before authoring a mirror baseline");
  reviewedParetoWorldWhatIfScenarios=[{
   id:"baseline",
   timeline:JSON.parse(JSON.stringify(lastInterleavedTimeline))
  }];
  $("advanced-pareto-whatif-results").textContent="";
  showParetoWorldWhatIfQueue();
  status("Authenticated baseline captured. All alternatives must reuse the same source events and world actions.");
 }catch(error){status("World what-if baseline blocked: "+error.message);}
});
$("advanced-pareto-whatif-swap").addEventListener("click",()=>{
 try{
  if(!reviewedParetoWorldWhatIfScenarios.length)
   throw Error("Capture the original source baseline first");
  const current=JSON.parse(JSON.stringify(
   JSON.parse($("advanced-interleave-editor").value)));
  if(!Array.isArray(current) || current.length<2)
   throw Error("At least two authentic events are required for an order variation");
  let changed=false;
  for(let i=0;i<current.length-1;i++){
   const x=current[i],y=current[i+1];
   if(x.lane!==y.lane && (x.lane==="world" || y.lane==="world" ||
      x.lane==="physical" && y.lane==="genre" ||
      x.lane==="genre" && y.lane==="physical")){
    current[i]=y;current[i+1]=x;changed=true;break;
   }
  }
  if(!changed)throw Error("No safe neighboring cross-engine events available to exchange");
  current.forEach((entry,i)=>{entry.at=i;});
  $("advanced-interleave-editor").value=JSON.stringify(current,null,2);
  status("Alternative authored: adjacent cross-engine events exchanged without inventing original source actions");
 }catch(error){status("World order variation rejected: "+error.message);}
});
$("advanced-pareto-whatif-capture").addEventListener("click",()=>{
 try{
  if(!reviewedParetoWorldWhatIfScenarios.length)
   throw Error("Capture source-verified baseline first");
  if(reviewedParetoWorldWhatIfScenarios.length>=8)
   throw Error("At most eight fully replayed original world variants");
  const timeline=JSON.parse($("advanced-interleave-editor").value);
  if(!Array.isArray(timeline)||!timeline.length||timeline.length>96)
   throw Error("Authored world clock needs one to 96 bounded real events");
  const digest=JSON.stringify(timeline);
  if(reviewedParetoWorldWhatIfScenarios.some(x=>JSON.stringify(x.timeline)===digest))
   throw Error("An identical event schedule is already captured");
  reviewedParetoWorldWhatIfScenarios.push({
   id:"alternative_"+reviewedParetoWorldWhatIfScenarios.length,
   timeline:JSON.parse(JSON.stringify(timeline))
  });
  showParetoWorldWhatIfQueue();
  status("Distinct authored counterfactual added; server must prove both share precisely the same original inputs");
 }catch(error){status("Original world what-if capture rejected: "+error.message);}
});
$("advanced-pareto-whatif-run").addEventListener("click",async()=>{
 try{
  if(!episodicLastScene || !verifiedSourceEpisodes.length ||
     !verifiedGenreEvents.length || reviewedParetoWorldWhatIfScenarios.length<2)
   throw Error("Two authored original world-clock schedules and genuine source engines required");
  const response=await api("/api/advanced-world-whatif-pareto",{
   physical_episodes:verifiedSourceEpisodes,
   genre_sessions:verifiedGenreEvents,
   world_scene:episodicLastScene,
   world_settings:interleavedWorldSettings,
   scenarios:reviewedParetoWorldWhatIfScenarios
  });
  const proof=response.report;
  if(!proof || response.source_games_mutated ||
     response.automatic_model_training || response.native_hardware_certified ||
     proof.world_scene_digest!==episodicLastScene.digest ||
     proof.scenarios.length!==reviewedParetoWorldWhatIfScenarios.length ||
     !proof.same_source_and_action_inputs ||
     !proof.comparison_has_no_automatic_winner ||
     !proof.original_game_saves_unchanged ||
     proof.automatic_model_training_approved ||
     proof.native_full_campaign_certified)
   throw Error("Counterfactual source-event provenance or fairness proof failed");
  $("advanced-pareto-whatif-results").textContent=JSON.stringify({
   source_fairness:proof.same_source_and_action_inputs,
   comparison_axes:proof.selected_axes,
   actual_game_event_variations:proof.scenarios,
   non_dominated_candidate_indices:proof.pareto_frontier_indices,
   strictly_dominant_over_baseline:proof.strict_baseline_dominators,
   no_automatic_winner:true,
   original_game_files_unchanged:true,
   verified_replay_digest:proof.digest
  },null,2);
  status("Original NPC world counterfactuals independently replayed and compared; tradeoffs remain explicit");
 }catch(error){status("Game-world counterfactual rejected: "+error.message);}
});
$("advanced-interleave-run").addEventListener("click",async()=>{
 try{
  if(!episodicLastScene || !verifiedSourceEpisodes.length ||
     !verifiedGenreEvents.length)
   throw Error("Original game scene and physical/genre sources are required");
  const timeline=JSON.parse($("advanced-interleave-editor").value);
  if(!Array.isArray(timeline)||!timeline.length||timeline.length>96)
   throw Error("One to 96 reviewed source-clock entries are required");
  const result=await api("/api/advanced-interleaved-world",{
   physical_episodes:verifiedSourceEpisodes,
   genre_sessions:verifiedGenreEvents,
   world_scene:episodicLastScene,timeline,
   world_settings:interleavedWorldSettings
  });
  const proof=result.proof;
  if(!proof || result.source_project_files_changed ||
     result.automatic_rewards_granted || result.native_hardware_certified ||
     proof.world_scene_digest!==episodicLastScene.digest ||
     proof.physical_source_count!==verifiedSourceEpisodes.length ||
     proof.genre_source_count!==verifiedGenreEvents.length ||
     proof.original_projects_modified || proof.free_rewards_granted)
   throw Error("Cross-engine NPC world event replay evidence did not authenticate");
  lastInterleavedProof=proof;
  lastInterleavedTimeline=JSON.parse(JSON.stringify(timeline));
  drawNPCForensicMap(proof.world_state);
  $("advanced-interleave-proof").textContent=JSON.stringify({
   source_event_clock:proof.timeline,
   authentic_physical_collisions:proof.authentic_physical_event_count,
   earned_genre_achievements:proof.authentic_genre_event_count,
   actually_played_npc_actions:proof.scheduled_world_actions,
   real_world_sites:proof.world_state.sites,
   real_npc_memories:proof.world_state.npcs.map(n=>({
    id:n.id,cell:n.cell,direct:n.memories,rumors:n.heard
   })),
   quests:proof.world_state.quests,
   world_time:proof.world_state.tick,
   audited_replay_digest:proof.digest,
   original_source_files_unchanged:true
  },null,2);
  status("Original physics, genre achievements and NPC actions actually replayed on one world clock");
 }catch(error){status("Interleaved original game source rejected: "+error.message);}
});
$("advanced-genre-queue-clear").addEventListener("click",()=>{
 verifiedGenreEvents=[];lastUnifiedGenreProof=null;unifiedWorldFollowups=[];
 lastInterleavedProof=null;lastInterleavedTimeline=null;interleavedWorldSettings=null;
 lastWorldWhatIfProof=null;
 lastWorldRobustnessProof=null;
 clearWorldCounterfactuals();
 reviewedParetoWorldWhatIfScenarios=[];
 $("advanced-pareto-whatif-queue").textContent="";
 $("advanced-pareto-whatif-results").textContent="";
 $("advanced-genre-queue-list").textContent="";
 $("advanced-unified-proof").textContent="";
 status("Unpublished genre source acquisitions cleared without modifying original saves");
});
$("advanced-genre-queue").addEventListener("click",async()=>{
 try{
  if(!episodicLastScene || !episodicLastProof ||
     !verifiedSourceEpisodes.length)
   throw Error("Replay the original physical NPC campaign before adding genre achievements");
  if(!advancedSession?.scene ||
      !["farming","sailing","flight"].includes(advancedSession.editor))
   throw Error("A signed original farming/sailing/flight session is required");
  if(verifiedGenreEvents.length>=4)
   throw Error("Maximum four independent original genre achievement sessions");
  const idx=Number($("advanced-genre-event-index").value);
  if(!Number.isSafeInteger(idx)||idx<0||idx>=advancedSession.trace.length)
   throw Error("Inspect and choose a real source event action first");
  if(verifiedGenreEvents.some(entry=>
      entry.source_session.digest===advancedSession.digest))
   throw Error("Original genre session already in persistent NPC campaign");
  const bindings=[{trace_index:idx,
                   site_id:Number($("advanced-genre-event-site").value)}];
  const verified=await api("/api/advanced-cross-genre-npc-world",{
   session:advancedSession,source_settings:advancedSettings,
   world_scene:episodicLastScene,bindings,world_actions:[]
  });
  if(!verified.report || verified.report.source_session_digest!==advancedSession.digest ||
      verified.report.world_scene_digest!==episodicLastScene.digest ||
      verified.original_project_files_modified || verified.native_hardware_certified ||
      verified.automatic_rewards_or_promotion ||
      verified.report.earned_events.length!==1)
   throw Error("Original gameplay genre receipt cannot be independently attributed");
  verifiedGenreEvents.push({
   source_session:JSON.parse(JSON.stringify(advancedSession)),
   source_settings:JSON.parse(JSON.stringify(advancedSettings)),
   bindings
  });
  lastUnifiedGenreProof=null;
  refreshUnifiedGenreQueue();
  status("One independently earned original genre event queued for persistent NPC replay");
 }catch(error){status("Original genre campaign addition rejected: "+error.message);}
});
$("advanced-unified-run").addEventListener("click",async()=>{
 try{
  if(!episodicLastScene || !episodicLastProof ||
     !verifiedSourceEpisodes.length || !verifiedGenreEvents.length)
   throw Error("Requires an original physical campaign plus independently earned genre achievements");
  const result=await api("/api/advanced-unified-genre-campaign",{
   physical_episodes:verifiedSourceEpisodes,
   genre_sessions:verifiedGenreEvents,
   world_scene:episodicLastScene,
   world_actions:unifiedWorldFollowups
  });
  const proof=result.proof;
  if(!proof || result.source_project_files_modified ||
      result.automatic_game_rewards || result.native_hardware_verified ||
      proof.physical_campaign_digest!==episodicLastProof.digest ||
      proof.world_scene_digest!==episodicLastScene.digest ||
      proof.genre_session_count!==verifiedGenreEvents.length ||
      proof.original_game_files_mutated || proof.free_game_rewards_minted)
   throw Error("Unified physical/genre NPC source chronology is not authenticated");
  lastUnifiedGenreProof=proof;
  drawNPCForensicMap(proof.world_state);
  $("advanced-unified-proof").textContent=JSON.stringify({
   physical_episodes:proof.physical_episode_count,
   real_genre_achievements:proof.verified_genre_event_count,
   ordered_source_incidents:proof.genre_history,
   authentic_npc_positions:proof.world_state.npcs.map(n=>({
    id:n.id,cell:n.cell,direct:n.memories,rumors:n.heard
   })),
   actual_world_sites:proof.world_state.sites,
   continuing_quests:proof.world_state.quests,
   full_replayed_world_digest:proof.digest,
   original_project_files_unchanged:true
  },null,2);
  status("Unified real physical and multi-genre NPC world independently replayed with original source custody");
 }catch(error){status("Unified genre NPC campaign blocked: "+error.message);}
});
$("advanced-genre-event-inspect").addEventListener("click",()=>{
 try{
  if(!advancedSession?.scene ||
     !["farming","sailing","flight"].includes(advancedSession.editor))
   throw Error("A signed farming, sailing or flight source scene is needed");
  const approved={
   farming:"mature_crop_harvested",
   sailing:"original_cargo_delivered",
   flight:"runway_landing_confirmed"
  }[advancedSession.editor];
  const optionList=$("advanced-genre-event-index");
  optionList.replaceChildren();
  for(let index=0;index<advancedSession.trace.length;index++){
   const item=advancedSession.trace[index];
   if(!item.events.includes(approved))continue;
   const choice=document.createElement("option");
   choice.value=String(index);
   choice.textContent="Source action "+index+" · "+item.action+" · "+approved;
   optionList.append(choice);
  }
  if(!optionList.options.length)
   throw Error("The original source engine has not earned that gameplay event");
  status("Candidate original genre events listed; server will independently replay their source");
 }catch(error){status("Original genre source inspection rejected: "+error.message);}
});
$("advanced-genre-event-play").addEventListener("click",async()=>{
 try{
  if(!advancedSession?.scene ||
     !["farming","sailing","flight"].includes(advancedSession.editor))
   throw Error("Original genre action source not available");
  const index=Number($("advanced-genre-event-index").value);
  if(!Number.isSafeInteger(index) || index<0 ||
      index>=advancedSession.trace.length)
   throw Error("Inspect one actually earned original source event first");
  const world=await api("/api/advanced-scene-template",{
   editor:"quest_director",seed:0,scene_id:"cross_genre_source_world"
  });
  const reply=await api("/api/advanced-cross-genre-npc-world",{
   session:advancedSession,world_scene:world.scene,
   source_settings:advancedSettings,
   bindings:[{trace_index:index,
              site_id:Number($("advanced-genre-event-site").value)}],
   world_actions:[]
  });
  const proof=reply.report;
  if(!proof || reply.original_project_files_modified ||
     reply.native_hardware_certified || reply.automatic_rewards_or_promotion ||
     proof.source_session_digest!==advancedSession.digest ||
     proof.world_scene_digest!==world.scene.digest ||
     proof.source_game_files_changed || proof.automatic_rewards_approved)
   throw Error("Source/eyewitness custody denied cross-genre world event");
  $("advanced-genre-event-proof").textContent=JSON.stringify({
    real_source_engine:proof.source_editor,
    original_action_events:proof.earned_events,
    direct_witness_memories:proof.world_state.npcs.map(n=>({
      id:n.id,cell:n.cell,direct:n.memories,rumors:n.heard
    })),
    actual_source_quests:proof.world_state.quests,
    finite_npc_site_stock:proof.world_state.sites,
    original_game_not_mutated:true,
    replay_digest:proof.digest
  },null,2);
  status("Earned original genre achievement independently replayed into NPC world with actual eyewitnesses");
 }catch(error){status("Cross-genre original gameplay event rejected: "+error.message);}
});
$("advanced-npc-rule-preview").addEventListener("click",async()=>{
 try{await runNPCConditionalRules("preview");}
 catch(error){status("NPC rule preview rejected: "+error.message);}
});
$("advanced-npc-rule-commit").addEventListener("click",async()=>{
 try{await runNPCConditionalRules("commit");}
 catch(error){status("NPC rule application rejected: "+error.message);}
});
let verifiedGenreEvents=[];
let lastUnifiedGenreProof=null;
let unifiedWorldFollowups=[];
let lastWhatIfReport=null;
let lastInterleavedProof=null;
let lastInterleavedTimeline=null;
let lastWorldWhatIfProof=null;
let lastWorldRobustnessProof=null;
let lastCounterfactualReport=null;
let reviewedParetoWorldWhatIfScenarios=[];
let interleavedWorldSettings=null;
let verifiedSourceEpisodes=[];
let episodicLastProof=null,episodicLastScene=null;
let verifiedInvestigationRoute=null;

function drawNPCForensicMap(world){
 const canvas=$("advanced-npc-world-canvas");
 const ctx=canvas.getContext("2d");
 const w=canvas.width,h=canvas.height;
 ctx.fillStyle="#0c2230";ctx.fillRect(0,0,w,h);
 ctx.font="12px system-ui";ctx.fillStyle="#d5e7ec";
 if(!world){ctx.fillText("Run an original NPC campaign to inspect its world",14,22);return;}
 const pad=18,step=42,side=7;
 const center=(cell)=>[pad+(cell%side)*step+step/2,
                       pad+Math.floor(cell/side)*step+step/2];
 const obstacles=new Set(world.world.obstacles);
 for(let id=0;id<49;id++){
  const [x,y]=center(id);
  ctx.fillStyle=obstacles.has(id)?"#394858":"#173747";
  ctx.fillRect(x-step/2+1,y-step/2+1,step-2,step-2);
  ctx.strokeStyle="#547582";ctx.strokeRect(x-step/2+1,y-step/2+1,step-2,step-2);
 }
 for(const site of world.sites){
  const [x,y]=center(site.cell);
  ctx.fillStyle=site.integrity>0?"#e3af5b":"#bc4f5a";
  ctx.fillRect(x-14,y-14,28,28);
  ctx.fillStyle="#142633";ctx.textAlign="center";
  ctx.fillText("S"+site.id,x,y+4);
 }
 for(const npc of world.npcs){
  const [x,y]=center(npc.cell);
  ctx.beginPath();ctx.arc(x,y,11,0,Math.PI*2);
  ctx.fillStyle=npc.memories.length?"#a5e69f":
    npc.heard.length?"#b4a5ef":"#a8bbc4";
  ctx.fill();
  ctx.fillStyle="#132433";ctx.textAlign="center";
  ctx.fillText("N"+npc.id,x,y+4);
 }
 const [px,py]=center(world.player);
 ctx.beginPath();ctx.arc(px,py,8,0,Math.PI*2);
 ctx.fillStyle="#f8f5e8";ctx.fill();ctx.strokeStyle="#163545";
 ctx.lineWidth=2;ctx.stroke();
 ctx.fillStyle="#dce8ee";ctx.textAlign="left";
 ctx.fillText("Day "+world.day+" · tick "+world.tick,14,336);
 ctx.fillText("S: sites · N: NPC",312,32);
 ctx.fillText("Green: saw",312,50);
 ctx.fillText("Purple: rumor",312,68);
 ctx.fillText("White: player",312,86);
}
function refreshNPCQuestRouteChoices(proof){
 const choice=$("advanced-npc-route-quest");
 const previous=choice.value;
 choice.replaceChildren();
 for(const q of proof.world_state.quests){
  if(q.origin_actor!=="external:physics" || q.status!=="active")continue;
  const item=document.createElement("option");
  item.value=String(q.id);
  item.textContent="Quest "+q.id+" · site "+q.site_id+
    " · testimony "+q.testimonies.length;
  choice.append(item);
 }
 if([...choice.options].some(opt=>opt.value===previous))choice.value=previous;
}

$("advanced-npc-route").addEventListener("click",async()=>{
 try{
  if(!episodicLastProof || !episodicLastScene)
   throw Error("Replay an original episodic NPC world before investigating");
  const value=$("advanced-npc-route-quest").value;
  if(!value)throw Error("No active original physical-source quest requires testimony");
  const answer=await api("/api/advanced-npc-evidence-navigation",{
   campaign:episodicLastProof,
   episodes:verifiedSourceEpisodes,world_scene:episodicLastScene,
   quest_id:Number(value),objective:$("advanced-npc-route-objective").value
  });
  const route=answer.navigation;
  if(!route || answer.original_game_changed ||
      answer.automatic_quest_reward_granted || answer.native_hardware_verified ||
      route.campaign_digest!==episodicLastProof.digest ||
      route.world_scene_digest!==episodicLastScene.digest)
   throw Error("Forensic navigation source custody mismatch");
  verifiedInvestigationRoute=route;
  $("advanced-npc-route-proof").textContent=JSON.stringify({
   objective:route.objective,
   original_quest_id:route.quest_id,
   actual_witness:route.target_npc_id,
   outcome:route.outcome,
   real_world_actions:route.planned_and_simulated_actions,
   original_world_steps:route.route_steps,
   proposed_quest_state:route.next_quest_state,
   player_after_route:route.end_world_state.player,
   stamina_after_route:route.end_world_state.stamina,
   actual_replay_digest:route.digest,
   source_campaign_unchanged:true
  },null,2);
  status("Investigative route simulated through real obstacles, NPC sight and physical stamina; apply only to replay.");
 }catch(error){status("Original eyewitness route blocked: "+error.message);}
});
$("advanced-npc-route-apply").addEventListener("click",()=>{
 try{
  if(!verifiedInvestigationRoute || !episodicLastProof ||
     verifiedInvestigationRoute.campaign_digest!==episodicLastProof.digest)
   throw Error("Run a fresh source-verified investigation route first");
  const realMoves=verifiedInvestigationRoute.planned_and_simulated_actions;
  if(!realMoves.length)throw Error("No earned world actions to apply");
  if(verifiedInvestigationRoute.outcome!=="firsthand_testimony_recorded" &&
     verifiedInvestigationRoute.outcome!=="real_site_repair_enacted" &&
     verifiedInvestigationRoute.outcome!=="finite_original_community_aid_delivered" &&
     verifiedInvestigationRoute.outcome!=="original_quest_resolved")
   throw Error("Route has not earned an original world objective");
  const latest=verifiedSourceEpisodes[verifiedSourceEpisodes.length-1];
  const total=verifiedSourceEpisodes.reduce((n,x)=>n+x.world_actions.length,0);
  if(latest.world_actions.length+realMoves.length>24 || total+realMoves.length>64)
   throw Error("Original authored world episode/total command budgets exceeded");
  latest.world_actions.push(...realMoves);
  verifiedInvestigationRoute=null;
  episodicLastProof=null;
  episodicLastScene=null;
  $("advanced-npc-route-proof").textContent="";
  $("advanced-episodic-play").click();
  status("Approved route actions added to original game episode; independent campaign replay requested.");
 }catch(error){status("Cannot commit forensic actions: "+error.message);}
});
$("advanced-npc-world-canvas").addEventListener("click",event=>{
 if(!episodicLastProof)return;
 const canvas=$("advanced-npc-world-canvas"),box=canvas.getBoundingClientRect();
 const x=(event.clientX-box.left)*canvas.width/box.width;
 const y=(event.clientY-box.top)*canvas.height/box.height;
 const col=Math.floor((x-18)/42),row=Math.floor((y-18)/42);
 if(col<0||col>=7||row<0||row>=7)return;
 const cell=row*7+col;
 const site=episodicLastProof.world_state.sites.find(x=>x.cell===cell);
 if(!site)return;
 const q=episodicLastProof.world_state.quests.find(q=>
   q.origin_actor==="external:physics" && q.status==="active" && q.site_id===site.id);
 if(q){
  $("advanced-npc-route-quest").value=String(q.id);
  status("Selected genuine physical quest "+q.id+" at authored site "+site.id);
 }
});
$("advanced-episodic-save-export").addEventListener("click",async()=>{
 try{
  if(!verifiedSourceEpisodes.length || !episodicLastScene)
   throw Error("Replay a source-verified original campaign before exporting");
  const reply=await api("/api/advanced-physics-episodic-save-export",{
   episodes:verifiedSourceEpisodes,world_scene:episodicLastScene
  });
  if(!reply.save || reply.original_source_modified ||
      reply.native_hardware_certified || reply.automatic_publication_approved ||
      reply.save.campaign_digest!==episodicLastProof?.digest)
   throw Error("Original source campaign save custody mismatch");
  const json=JSON.stringify(reply.save,null,2);
  if(new TextEncoder().encode(json).length>2000000)
   throw Error("Episodic save exceeds 2 MB browser export budget");
  const url=URL.createObjectURL(new Blob([json],{type:"application/json"}));
  const link=document.createElement("a");link.href=url;
  link.download="original-npc-physics-campaign-"+reply.save.digest.slice(0,12)+".json";
  document.body.append(link);link.click();link.remove();
  setTimeout(()=>URL.revokeObjectURL(url),0);
  $("advanced-episodic-save-receipt").textContent=JSON.stringify({
   source_save_digest:reply.save.digest,
   episode_count:reply.save.episode_count,
   original_world_actions:reply.save.total_world_actions,
   replay_required:true,original_game_files_modified:false
  },null,2);
  status("Portable original NPC campaign input log exported; all rewards remain replay-verified.");
 }catch(error){status("Original campaign export blocked: "+error.message);}
});
$("advanced-episodic-save-import").addEventListener("change",async()=>{
 try{
  const input=$("advanced-episodic-save-import"),file=input.files?.[0];
  if(!file) return;
  if(file.size>2000000)throw Error("Oversized original world save rejected");
  const raw=await file.text();
  if(new TextEncoder().encode(raw).length>2000000)throw Error("Oversized save rejected");
  const document=JSON.parse(raw);
  const response=await api("/api/advanced-physics-episodic-save-import",{
   save:document
  });
  const imported=response.restored;
  if(!imported?.verified || imported.save_digest!==document.digest ||
      response.original_source_modified || response.native_hardware_certified ||
      response.automatic_publication_approved ||
      imported.campaign.world_scene_digest!==imported.world_scene.digest)
   throw Error("Original episodic save failed independent source replay");
  verifiedSourceEpisodes=imported.episodes;
  episodicLastScene=imported.world_scene;
  episodicLastProof=imported.campaign;
  verifiedInvestigationRoute=null;
  $("advanced-npc-route-proof").textContent="";
  refreshNPCQuestRouteChoices(episodicLastProof);
  drawNPCForensicMap(episodicLastProof.world_state);
  $("advanced-episodic-proof").textContent=JSON.stringify({
   restored_world:episodicLastProof.world_state,
   source_episodes:verifiedSourceEpisodes.length,
   reconstructed_game_digest:episodicLastProof.digest,
   original_saves_untouched:true
  },null,2);
  $("advanced-episodic-save-receipt").textContent=JSON.stringify({
   verified:true,source_save_digest:imported.save_digest,
   remaining_episodes:imported.remaining_episode_budget,
   remaining_actions:imported.remaining_action_budget,
   independently_replayed:true
  },null,2);
  status("Episodic original game and NPC world independently reconstructed from imported action log.");
 }catch(error){status("Untrusted original save rejected: "+error.message);}
 finally{$("advanced-episodic-save-import").value="";}
});
$("advanced-episodic-clear").addEventListener("click",()=>{
 verifiedSourceEpisodes=[];
 verifiedGenreEvents=[];lastUnifiedGenreProof=null;unifiedWorldFollowups=[];
 $("advanced-genre-queue-list").textContent="";
 $("advanced-unified-proof").textContent="";
 episodicLastProof=null;episodicLastScene=null;verifiedInvestigationRoute=null;
 drawNPCForensicMap(null);
 $("advanced-npc-route-proof").textContent="";
 $("advanced-episodic-queue").textContent="";
 $("advanced-episodic-proof").textContent="";
 status("Unpublished original physical episodes cleared; no source game files changed");
});
$("advanced-episodic-add").addEventListener("click",async()=>{
 try{
  if(!advancedSession?.scene ||
     !["platformer","racing","sandbox"].includes(advancedSession.editor))
   throw Error("Source-authorized advanced game session required");
  if(verifiedSourceEpisodes.length>=6)throw Error("Maximum six original game episodes");
  const actions=$("advanced-linked-physical").value==="avoid"?
   ["inspect"]:Array(8).fill("push:east");
  const physical=await api("/api/advanced-physics-interop",{
   session:advancedSession,settings:advancedSettings,
   physics_actions:actions
  });
  if(!physical.proof || physical.proof.source_session_digest!==advancedSession.digest)
   throw Error("Original game source receipt could not be independently reconstructed");
  const struck=physical.proof.source_fixture_impacts[0];
  const candidate=struck?.source_id??physical.proof.witnesses[0]?.source_id;
  if(!Number.isSafeInteger(candidate))throw Error("Source lacks reviewable physical fixtures");
  const existing=verifiedSourceEpisodes.filter(ep=>
   ep.source_session.editor===advancedSession.editor &&
   ep.source_session.scene.digest===advancedSession.scene.digest);
  if(existing.length){
   const former=existing[existing.length-1].source_session.actions;
   const next=advancedSession.actions;
   if(next.length<=former.length || former.some((a,i)=>a!==next[i]))
    throw Error("The next source episode must extend the original authored game action transcript");
  }
  const raw=$("advanced-npc-followups").value.trim();
  const worldActions=raw?raw.split(",").map(x=>x.trim()):[];
  if(worldActions.length>24 || worldActions.some(x=>!x))
   throw Error("Per-episode investigation limit is 24 original-world actions");
  const episode={
    source_session:JSON.parse(JSON.stringify(advancedSession)),
    source_settings:JSON.parse(JSON.stringify(advancedSettings)),
    physics_actions:actions,
    bindings:[{source_id:candidate,site_id:Number($("advanced-npc-site").value)}],
    world_actions:worldActions
  };
  verifiedSourceEpisodes.push(episode);
  episodicLastProof=null;episodicLastScene=null;verifiedInvestigationRoute=null;
  $("advanced-npc-route-proof").textContent="";
  $("advanced-episodic-queue").textContent=JSON.stringify(
    verifiedSourceEpisodes.map((ep,i)=>({
     episode:i+1,source:ep.source_session.editor,
     action_count:ep.source_session.actions.length,
     source_digest:ep.source_session.digest,
     source_object:ep.bindings[0].source_id,site:ep.bindings[0].site_id,
     physics_commands:ep.physics_actions.length,
     authored_world_actions:ep.world_actions.length,
    })),null,2);
  status("Signed original episode added; physical impacts will be rechecked across the persistent world");
 }catch(error){status("Episodic original source rejected: "+error.message);}
});
$("advanced-episodic-play").addEventListener("click",async()=>{
 try{
  if(!verifiedSourceEpisodes.length)throw Error("Capture an authentic source episode first");
  const realWorld=await api("/api/advanced-scene-template",{
   editor:"quest_director",seed:0,scene_id:"episodic_original_world"
  });
  const response=await api("/api/advanced-physics-episodic-npc",{
   episodes:verifiedSourceEpisodes,world_scene:realWorld.scene
  });
  const proof=response.proof;
  if(!proof || response.source_saves_changed || response.native_hardware_verified ||
     response.automatic_promotion_approved ||
     proof.world_scene_digest!==realWorld.scene.digest ||
     proof.episode_count!==verifiedSourceEpisodes.length)
   throw Error("Persistent game and physical NPC replay receipt failed custody");
  episodicLastProof=proof;episodicLastScene=realWorld.scene;
  verifiedInvestigationRoute=null;
  refreshNPCQuestRouteChoices(proof);
  drawNPCForensicMap(proof.world_state);
  $("advanced-episodic-proof").textContent=JSON.stringify({
   episode_count:proof.episode_count,
   source_chronology:proof.episodes,
   true_source_incidents:proof.total_true_incidents,
   original_living_npc_positions:proof.world_state.npcs.map(n=>({
    id:n.id,cell:n.cell,eyewitness:n.memories,rumors:n.heard
   })),
   sites:proof.world_state.sites,
   original_relief_deliveries:proof.world_state.relief_deliveries,
   causal_quests:proof.world_state.quests,
   original_quests_completed:proof.world_state.quests_completed,
   rumor_edges:proof.world_state.rumor_edges,
   world_turn:proof.world_state.turn,
   world_day:proof.world_state.day,
   campaign_receipt:proof.digest,
   source_games_unchanged:true
  },null,2);
  status("Persistent original NPC living world executed and independently reconstructed over "+
    proof.episode_count+" signed game episodes");
 }catch(error){status("Persistent physical NPC campaign blocked: "+error.message);}
});
$("advanced-npc-multi").addEventListener("click",async()=>{
 try{
  if(!advancedSession?.scene ||
     !["platformer","racing","sandbox"].includes(advancedSession.editor))
   throw Error("Original source game and signed scene required");
  const physicsActions=Array(8).fill("push:east");
  const preview=await api("/api/advanced-physics-interop",{
   session:advancedSession,settings:advancedSettings,
   physics_actions:physicsActions
  });
  if(!preview.proof || preview.proof.source_session_digest!==advancedSession.digest)
   throw Error("Original physical source proof did not authenticate");
  const candidates=preview.proof.witnesses;
  const selected=candidates.slice(0,4);
  const panel=$("advanced-npc-bindings");
  panel.replaceChildren();
  for(let index=0;index<selected.length;index++){
   const item=selected[index];
   const line=document.createElement("label");
   line.textContent=item.source_type+" #"+item.source_id+
    (item.layer===2?" · passable":" · solid")+" → world site ";
   const picker=document.createElement("select");
   picker.dataset.sourceId=String(item.source_id);
   picker.dataset.incidentBinding="true";
   for(let j=0;j<4;j++){
    const option=document.createElement("option");
    option.value=String(j);
    option.textContent=["settlement","bridge","grove","archive"][j];
    picker.append(option);
   }
   picker.value=String(index);line.append(picker);panel.append(line);
  }
  if(!selected.length)throw Error("Original source has no physical world fixtures");
  // The authenticated server recomputes actual hits; UI selection is only
  // an authored identity-to-site mapping, never an incident entitlement.
  const bindings=[...panel.querySelectorAll('[data-incident-binding="true"]')]
   .map(item=>({source_id:Number(item.dataset.sourceId),
                site_id:Number(item.value)}));
  const followups=$("advanced-npc-followups").value.trim();
  const actions=followups?followups.split(",").map(a=>a.trim()):[];
  if(actions.length>24 || actions.some(a=>!a))
   throw Error("At most 24 complete authored NPC world commands are allowed");
  const world=await api("/api/advanced-scene-template",{
   editor:"quest_director",seed:advancedSession.seed,
   scene_id:"multi_incident_original_world"
  });
  const reply=await api("/api/advanced-physics-multi-npc",{
   session:advancedSession,settings:advancedSettings,
   world_scene:world.scene,physics_actions:physicsActions,
   bindings,world_actions:actions
  });
  const proof=reply.proof;
  if(!proof || reply.source_project_mutated || reply.native_certified ||
      reply.automatic_quest_rewards_granted ||
      proof.source_session_digest!==advancedSession.digest ||
      proof.quest_scene_digest!==world.scene.digest)
   throw Error("Source/NPC multi-incident replay or release custody failed");
  $("advanced-npc-multi-proof").textContent=JSON.stringify({
   ordered_physical_incidents:proof.incidents,
   actual_fixture_contacts:proof.source_fixture_impacts,
   witnessed_source_events:proof.world_state.events_log,
   eyewitnesses:proof.world_state.npcs.map(n=>({
    id:n.id,direct:n.memories,rumors:n.heard
   })),
   causal_quests:proof.world_state.quests,
   original_world_timeline:proof.world_timeline,
   source_game_unchanged:true,
   replay_digest:proof.digest
  },null,2);
  status("Actual multi-object collision investigation independently replayed with source chronology.");
 }catch(error){status("Multi-object witness investigation rejected: "+error.message);}
});
$("advanced-npc-observe").addEventListener("click",async()=>{
 try{
  if(!advancedSession || !advancedSession.scene ||
      !["platformer","racing","sandbox"].includes(advancedSession.editor))
   throw Error("Signed original Platformer, Racing or Sandbox scene required");
  const physicalActions=Array(8).fill("push:east");
  // The candidate list is evidence produced by independently replayed real
  // collisions; clients cannot mint a fixture event by selecting an object.
  const evidence=await api("/api/advanced-physics-interop",{
   session:advancedSession,settings:advancedSettings,
   physics_actions:physicalActions
  });
  if(!evidence.proof || evidence.proof.source_session_digest!==advancedSession.digest)
   throw Error("Unauthenticated source evidence");
  const selector=$("advanced-npc-source");
  const old=selector.value;
  selector.replaceChildren();
  for(const witness of evidence.proof.witnesses){
   const option=document.createElement("option");
   option.value=String(witness.source_id);
   option.textContent=witness.source_type+" #"+witness.source_id+
    " ("+(witness.layer===2?"passable":"solid")+")";
   selector.append(option);
  }
  if(!selector.options.length)throw Error("No original physics objects exist");
  if([...selector.options].some(option=>option.value===old))selector.value=old;
  else {
   const first=evidence.proof.source_fixture_impacts[0];
   if(first)selector.value=String(first.source_id);
  }
  const sourceId=Number(selector.value);
  const site=Number($("advanced-npc-site").value);
  const raw=$("advanced-npc-followups").value.trim();
  const followups=raw?raw.split(",").map(item=>item.trim()):[];
  if(followups.length>24 || followups.some(item=>!item))
   throw Error("A maximum of 24 complete original-world actions is permitted");
  const world=await api("/api/advanced-scene-template",{
    editor:"quest_director",seed:advancedSession.seed,
    scene_id:"npc_physics_world"
  });
  const reply=await api("/api/advanced-physics-npc-witness",{
   session:advancedSession,settings:advancedSettings,
   world_scene:world.scene,binding:{source_id:sourceId,site_id:site},
   physics_actions:physicalActions,world_actions:followups
  });
  if(!reply.proof || reply.source_project_mutated ||
     reply.native_certified || reply.automatic_quest_reward_granted_to_original_game ||
     reply.proof.source_session_digest!==advancedSession.digest ||
     reply.proof.world_scene_digest!==world.scene.digest)
   throw Error("Original scene or eyewitness custody did not pass");
  const report=reply.proof;
  $("advanced-npc-evidence").textContent=JSON.stringify({
   object_source:report.binding.source_id,
   bound_world_site:report.binding.site_id,
   actual_object_hits:report.actual_bound_impacts,
   source_collider_receipts:report.source_fixture_impacts,
   first_hand_witnesses:report.direct_witnesses,
   actual_incident:report.incident,
   original_causal_quests:report.physical_origin_quest_ids,
   followup_timeline:report.world_timeline,
   npc_memories:report.world_state.npcs.map(n=>({
    id:n.id,cell:n.cell,eyewitness:n.memories,rumors:n.heard
   })),
   original_project_mutated:false,
   source_replay_digest:report.source_session_digest,
  },null,2);
  status("Original physical NPC world independently reconstructed with line-of-sight and causal quest evidence.");
 }catch(error){status("Physics NPC world action rejected: "+error.message);}
});
$("advanced-physics-interop").addEventListener("click",async()=>{
 try{
  if(!advancedSession || !["platformer","racing","sandbox"].includes(advancedSession.editor)
      || !advancedSession.scene)
   throw Error("Use a signed authored Platformer, Racing or Sandbox scene first");
  const response=await api("/api/advanced-physics-interop",{
   session:advancedSession,settings:advancedSettings,
   physics_actions:Array(8).fill("push:east")
  });
  if(!response.proof || response.source_mutated ||
      response.proof.source_session_digest!==advancedSession.digest)
   throw Error("Cross-system source digest is not authenticated");
  $("advanced-physics-interop-proof").textContent=JSON.stringify({
   source:response.proof.source_editor,
   signed_source:response.proof.source_scene_digest,
   physical_witnesses:response.proof.witnesses,
   actual_fixture_impacts:response.proof.observed_fixture_impacts,
   physical_replay_digest:response.proof.physics_session.digest,
   source_files_mutated:false,hardware_verified:false,
  },null,2);
  status("Actual authored physics encounter independently replayed; original game state unchanged.");
 }catch(error){
  status("Physical source rehearsal blocked: "+error.message);
 }
});
$("advanced-verify").addEventListener("click",async()=>{
 try{
  if(!advancedSession)throw Error("Start an advanced reference game first");
  const result=await api("/api/advanced-verify",{
   session:advancedSession,settings:advancedSettings});
  if(!result.verified)throw Error("Reference replay did not validate");
  status("Advanced replay verified against full immutable action transcript.");
 }catch(error){status("Replay evidence rejected: "+error.message);}
});
drawAdvancedGame(null);
loadSystemEditors();
refresh();
"""
TEMPLATE="""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="__CSP__">
<title>Original Game AI Studio · supervised file trees</title>
<style>__STYLE__</style></head><body>
<header><h1>Original Game AI Studio</h1>
<p>Previous projects · Current game · Original demos · Targeted human-reviewed edits</p>
<p>Active: <strong id="active"></strong> · <span id="revision"></span></p></header>
<main><section><h2>1. Project lanes</h2>
<label>Source tree<select id="tree"><option value="current">Ongoing original project</option>
<option value="previous">Previous projects and genres</option>
<option value="demos">Demo library</option></select></label>
<label>Select project<select id="project-choice"></select></label>
<button id="refresh">Refresh tree</button>
<fieldset><legend>Create original game</legend>
<label>ID<input id="new-project" placeholder="original_world_01"></label>
<label>Genre<input id="new-genre" placeholder="rpg"></label>
<button id="create">Create current game</button></fieldset>
<fieldset><legend>Snapshot selected current game</legend>
<button id="archive">Archive to previous</button>
<button id="demo">Create immutable demo</button></fieldset>
<fieldset><legend>Autoload previous genre as new game</legend>
<label>Genre<input id="load-genre" placeholder="rpg"></label>
<label>New project ID<input id="load-project" placeholder="sequel_01"></label>
<button id="autoload">Fork prior genre to current</button></fieldset>
<fieldset><legend>Fork demo for full visual editing</legend>
<label>Demo reference (genre/project-snapshot)
<input id="demo-ref" placeholder="rpg/first_game-abcd1234"></label>
<label>New writable original game ID
<input id="demo-target" placeholder="demo_customization"></label>
<button id="fork-demo">Fork demo into current</button></fieldset>
<p id="readonly" class="readonly"></p></section>
<section><h2>2. Precise file and folder targeting</h2>
<label>Natural-language original game design prompt
<textarea id="user-prompt" rows="4" placeholder="Create a branching escort storyline with eyewitness reactions, alternative endings, NPC memories and cinematic staging..."></textarea></label>
<button id="plan">Plan affected modules and targets</button>
<pre id="plan-results"></pre>
<label>New exact source path (including subfolder)
<input id="new-path" placeholder="missions/original_rival_arc.json"></label>
<button id="new-file">Stage new source file</button>
<fieldset><legend>Model progression and adversarial learning</legend>
<p><small>Read-only model custody. Promotion requires separately reviewed CLI gates.</small></p>
<pre id="model-progress" role="status" aria-live="polite"></pre>
<button id="model-refresh" type="button">Refresh reviewer status</button>
</fieldset>
<fieldset><legend>Genre and system editors</legend>
<p id="system-count">Loading typed system catalog</p>
<label>Authoring system<select id="system-kind"></select></label>
<small id="system-description"></small>
<div id="system-fields" aria-label="System-specific design settings"></div>
<button id="system-try" type="button">Validate and simulate preview</button>
<button id="system-stage" type="button">Stage system into source review</button>
<button id="system-assembly" type="button">Review assembled current systems</button>
<canvas id="system-canvas" width="470" height="210" role="img"
 aria-label="Validated genre-system mechanics preview"></canvas>
<pre id="system-preview" role="status" aria-live="polite"></pre>
<fieldset><legend>Advanced playable scenario · reference engine</legend>
<p><small>Command-driven original gameplay in eight advanced reference engines: platformer, tactics, tower defense, racing, survival, shooter, deck battler and puzzle.
Other editor families remain authoring-only, not falsely certified engines.</small></p>
<label>Scenario seed<input id="advanced-seed" type="number" min="0" max="2147483647" value="0"></label>
<label>Original authored scene ID<input id="advanced-scene-id" value="scene_01"></label>
<button id="advanced-scene-template" type="button">Create / validate authored scene</button>
<button id="advanced-scene-stage" type="button">Stage authored scene for review</button>
<button id="advanced-puzzle-solve" type="button">Prove puzzle solution / detect impossible state</button>
<button id="stealth-mission-plan" type="button">AI: rehearse authored stealth mission route</button>
<button id="world-progression-plan" type="button">AI: rehearse world ability progression</button>
<pre id="world-progression-proof" role="status" aria-live="polite"></pre>
<pre id="stealth-plan-proof" role="status" aria-live="polite"></pre>
<pre id="advanced-puzzle-proof" role="status" aria-live="polite"></pre>
<label>Editable scene geometry and resource JSON
<textarea id="advanced-scene-json" rows="6" spellcheck="false"
 placeholder="Generate an advanced authored scene, then edit its layout."></textarea></label>
<label>Graphical scene painting tool<select id="advanced-paint-tool" aria-label="Scene cell paint operation"></select></label>
<canvas id="advanced-scene-grid" width="470" height="285" role="img"
 aria-label="Editable tactical scene cell grid"></canvas>
<p><small>Graphical cell painting: shooter, tactics, puzzle, Colony, City and Stealth. Scene edits stay
local until typed revalidation and an explicit human-approved file commit.</small></p>
<button id="advanced-start" type="button">Start advanced scenario</button>
<button id="advanced-physics-native" type="button">Prepare native physics demo</button>
<button id="advanced-physics-interop" type="button">Rehearse authored physical encounters</button>
<fieldset aria-label="Authored NPC physical witnesses">
 <legend>NPC-witnessed original physics and quests</legend>
 <label>Original physical object<select id="advanced-npc-source"></select></label>
 <label>Author-bound quest site
  <select id="advanced-npc-site">
   <option value="0">Site 0 · settlement</option>
   <option value="1">Site 1 · bridge</option>
   <option value="2">Site 2 · grove</option>
   <option value="3">Site 3 · archive</option>
  </select>
 </label>
 <label>NPC world follow-up commands (comma separated; max 24)
  <input id="advanced-npc-followups" value="" placeholder="wait, south, east, speak:0">
 </label>
 <button id="advanced-npc-observe" type="button">
  Reconstruct physical incident and NPC eyewitness quests
 </button>
 <pre id="advanced-npc-evidence" role="status" aria-live="polite"></pre>
 <button id="advanced-npc-multi" type="button">Run multi-object collision investigation</button>
 <div id="advanced-npc-bindings" role="group" aria-label="Original collider to site bindings"></div>
 <pre id="advanced-npc-multi-proof" role="status" aria-live="polite"></pre>
<fieldset aria-label="Persistent episodic living world">
  <legend>Persistent eyewitness campaign · source-verified episodes</legend>
  <button id="advanced-episodic-add" type="button">Capture signed original game episode</button>
  <button id="advanced-episodic-play" type="button">Run persistent living-world campaign</button>
  <button id="advanced-episodic-clear" type="button">Reset unpublished episodes</button>
  <pre id="advanced-episodic-queue" role="status" aria-live="polite"></pre>
  <pre id="advanced-episodic-proof" role="status" aria-live="polite"></pre>
  <fieldset aria-label="Replay-verifiable episodic campaign saves">
    <legend>Durable original campaign save / restore</legend>
    <button id="advanced-episodic-save-export" type="button">Export verified campaign save</button>
    <label>Import authored campaign save (2 MB maximum)
      <input id="advanced-episodic-save-import" type="file"
       accept=".json,application/json"/>
    </label>
    <pre id="advanced-episodic-save-receipt" role="status" aria-live="polite"></pre>
  <fieldset aria-label="Typed living-world condition rules">
    <legend>NPC world rules · source facts and earned actions</legend>
    <label>Original if / all / any / not rule JSON
      <textarea id="advanced-npc-rule-editor" rows="9"></textarea>
    </label>
    <button id="advanced-npc-rule-preview" type="button">
      Preview original world rule outcomes
    </button>
    <button id="advanced-npc-rule-commit" type="button">
      Commit verified source actions into current campaign
    </button>
    <pre id="advanced-npc-rule-proof" role="status" aria-live="polite"></pre>
    <fieldset aria-label="Original cross-genre NPC world">
      <legend>Original farming, sailing and flight event witnesses</legend>
      <button id="advanced-genre-event-inspect" type="button">
        Inspect earned original source events
      </button>
      <label>Real original gameplay event
        <select id="advanced-genre-event-index"></select>
      </label>
      <label>NPC world site
        <select id="advanced-genre-event-site">
          <option value="0">Settlement</option>
          <option value="1">Bridge</option>
          <option value="2">Grove</option>
          <option value="3">Archive</option>
        </select>
      </label>
      <button id="advanced-genre-event-play" type="button">
        Replay original achievement into NPC world
      </button>
      <pre id="advanced-genre-event-proof" role="status" aria-live="polite"></pre>
      <button id="advanced-genre-queue" type="button">
        Add reviewed original genre achievement to campaign
      </button>
      <button id="advanced-unified-run" type="button">
        Replay unified original physical and genre NPC world
      </button>
      <button id="advanced-genre-queue-clear" type="button">
        Clear unpublished genre achievements
      </button>
      <pre id="advanced-genre-queue-list" role="status" aria-live="polite"></pre>
      <pre id="advanced-unified-proof" role="status" aria-live="polite"></pre>
      <fieldset aria-label="One-clock interleaved authored worlds">
       <legend>Original cross-engine NPC event scheduler</legend>
       <button id="advanced-interleave-build" type="button">
        Derive authentic physics + genre event order
       </button>
       <label>Author world-clock event order JSON
        <textarea id="advanced-interleave-editor" rows="11"
         placeholder='[{"at":0,"lane":"physical","source_index":0,"event_index":0}]'></textarea>
       </label>
       <button id="advanced-interleave-run" type="button">
        Replay authored cross-engine event timeline
       </button>
       <pre id="advanced-interleave-proof" role="status" aria-live="polite"></pre>
       <fieldset aria-label="Adversarial source-authenticated what-if mirror">
        <legend>Original NPC world · counterfactual mirror laboratory</legend>
        <label>Author-selected world priority
         <select id="advanced-whatif-objective">
          <option value="eyewitness_coverage">Preserve actual eyewitness coverage</option>
          <option value="community_recovery">Protect original world sites and recovery</option>
          <option value="resource_stewardship">Conserve finite stocks and supplies</option>
          <option value="quest_progress">Compare earned causal quest progress</option>
         </select>
        </label>
        <label>Reordering depth
         <select id="advanced-whatif-depth">
          <option value="1">One causal swap</option>
          <option value="2" selected>Two causal swaps</option>
          <option value="3">Three causal swaps</option>
         </select>
        </label>
        <button id="advanced-whatif-run" type="button">
         Adversarially replay bounded original game alternatives
        </button>
        <label>Source-verified alternative
         <select id="advanced-whatif-select"></select>
        </label>
        <button id="advanced-whatif-use" type="button">
         Copy reviewed alternative into timeline editor
        </button>
        <pre id="advanced-whatif-proof" role="status" aria-live="polite"></pre>
        <fieldset aria-label="Multiple source-authored worlds robustness test">
         <legend>Adversarial world context and source-validity laboratory</legend>
         <label>Independent original world contexts
          <select id="advanced-robustness-contexts">
           <option value="2">Two separately signed NPC world scenes</option>
           <option value="3">Three separately signed NPC world scenes</option>
          </select>
         </label>
         <button id="advanced-robustness-run" type="button">
          Replay candidates across authentic NPC world contexts
         </button>
         <button id="advanced-robustness-copy" type="button">
          Copy best observed cross-context candidate to editor
         </button>
         <pre id="advanced-robustness-proof" role="status" aria-live="polite"></pre>
        </fieldset>
       </fieldset>
       <fieldset aria-label="Adversarial game world what-if research">
        <legend>Mirror laboratory · causal NPC game world alternatives</legend>
        <label>Maximum independently replayed what-if trials
          <input id="advanced-whatif-trial-limit" type="number"
           min="1" max="12" step="1" value="8"/>
        </label>
        <button id="advanced-whatif-run" type="button">
          Compare source-verified world event orders
        </button>
        <label>Authenticated alternative scenario
          <select id="advanced-whatif-candidate"></select>
        </label>
        <button id="advanced-whatif-use" type="button">
          Copy verified alternate order to timeline editor
        </button>
        <pre id="advanced-whatif-proof" role="status" aria-live="polite"></pre>
        <fieldset aria-label="Measurable narrative game objectives">
         <legend>Adversarial NPC game design objective comparison</legend>
         <label>Ordered review goals (JSON list, maximum four)
          <textarea id="advanced-objective-goals" rows="5"></textarea>
         </label>
         <button id="advanced-objective-run" type="button">
          Compare verified playable game outcomes, not just event order
         </button>
         <pre id="advanced-objective-proof" role="status" aria-live="polite"></pre>
        </fieldset>
       </fieldset>
       <fieldset aria-label="Cross-engine adversarial what-if research">
         <legend>Verified alternative world histories</legend>
         <label>Compare actual game-world objective
           <select id="advanced-counterfactual-objective">
             <option value="preserve_sites">Preserve real site integrity</option>
             <option value="retain_supplies">Retain actual player supplies</option>
             <option value="maximize_earned_quests">Maximize earned quest completions</option>
             <option value="maximize_firsthand_memories">Maximize firsthand NPC memories</option>
           </select>
         </label>
         <button id="advanced-counterfactual-generate" type="button">
           Generate alternate original source event orders
         </button>
         <label>Review alternate source clock timelines (JSON)
           <textarea id="advanced-counterfactual-cases" rows="11"></textarea>
         </label>
         <button id="advanced-counterfactual-run" type="button">
           Independently replay and compare real NPC worlds
         </button>
         <label>Verified alternative
           <select id="advanced-counterfactual-choice"></select>
         </label>
         <button id="advanced-counterfactual-select" type="button">
           Select tested alternative for explicit world-clock replay
         </button>
         <pre id="advanced-counterfactual-report" role="status" aria-live="polite"></pre>
       </fieldset>
       <fieldset aria-label="Source-verified NPC what-if mirror laboratory">
         <legend>Original world event-order counterfactuals</legend>
         <button id="advanced-pareto-whatif-baseline" type="button">
           Capture verified timeline as baseline
         </button>
         <button id="advanced-pareto-whatif-swap" type="button">
           Derive a distinct neighboring event-order variant
         </button>
         <button id="advanced-pareto-whatif-capture" type="button">
           Capture authored alternative for comparison
         </button>
         <button id="advanced-pareto-whatif-run" type="button">
           Replay and compare the original worlds
         </button>
         <pre id="advanced-pareto-whatif-queue" role="status" aria-live="polite"></pre>
         <pre id="advanced-pareto-whatif-results" role="status" aria-live="polite"></pre>
       </fieldset>
       <fieldset aria-label="Portable original multi-engine world clock">
        <legend>Save and restore authored interleaved gameplay</legend>
        <button id="advanced-interleave-save-export" type="button">
         Export independently replayed world-clock save
        </button>
        <label>Import interleaved source save (4 MB max)
         <input id="advanced-interleave-save-import" type="file"
          accept=".json,application/json"/>
        </label>
        <pre id="advanced-interleave-save-proof" role="status" aria-live="polite"></pre>
       <fieldset aria-label="Counterfactual original game simulation">
        <legend>Adversarial original-world timeline mirror</legend>
        <button id="advanced-mirror-build" type="button">
         Prepare authentic alternate event-order comparison
        </button>
        <label>Explicit verified world objective
         <select id="advanced-mirror-objective">
          <option value="site_integrity">Total original site integrity</option>
          <option value="direct_memories">Recorded firsthand NPC memories</option>
          <option value="supplies">Remaining world supplies</option>
          <option value="quests_completed">Actually completed NPC quests</option>
         </select>
        </label>
        <label>Counterfactual reviewed timelines (2–6)
         <textarea id="advanced-mirror-scenarios" rows="11"></textarea>
        </label>
        <button id="advanced-mirror-run" type="button">
         Independently replay and compare actual NPC outcomes
        </button>
        <pre id="advanced-mirror-proof" role="status" aria-live="polite"></pre>
       </fieldset>
       </fieldset>
      </fieldset>
      <fieldset aria-label="Portable mixed-source campaign save">
        <legend>Save / restore combined physical + genre NPC world</legend>
        <button id="advanced-unified-save-export" type="button">
          Export replay-verified unified campaign
        </button>
        <label>Import source-verified unified save (3 MB maximum)
          <input id="advanced-unified-save-import" type="file"
            accept=".json,application/json"/>
        </label>
        <pre id="advanced-unified-save-receipt" role="status" aria-live="polite"></pre>
      </fieldset>
    </fieldset>
  </fieldset>
  </fieldset>
  <fieldset aria-label="Forensic NPC route navigator">
   <legend>Playable eyewitness and physical investigation routes</legend>
   <canvas id="advanced-npc-world-canvas" width="380" height="350"
    aria-label="Current authored seven by seven NPC world map"></canvas>
   <label>Source-verified causal quest<select id="advanced-npc-route-quest"></select></label>
   <label>Original gameplay objective<select id="advanced-npc-route-objective">
    <option value="testimony">Reach and interview a real eyewitness</option>
    <option value="repair">Walk to and repair actual damage</option>
    <option value="aid">Deliver finite relief supplies for recovery quests</option>
    <option value="resolve">Resolve proven material quest outcome</option>
   </select></label>
   <button id="advanced-npc-route" type="button">Compute and replay investigation route</button>
   <button id="advanced-npc-route-apply" type="button">
    Add verified route actions to campaign and replay
   </button>
   <pre id="advanced-npc-route-proof" role="status" aria-live="polite"></pre>
  </fieldset>
</fieldset>
</fieldset>
<button id="advanced-interop-godot" type="button">Download original physical encounter for Godot 4</button>
<fieldset aria-label="Opt-in linked physical campaign">
 <legend>Linked physical campaign · real health and durability</legend>
 <label>Original game action<select id="advanced-linked-action"></select></label>
 <label>Physics maneuver<select id="advanced-linked-physical">
  <option value="impact">Impact route</option>
  <option value="avoid">Avoid collision (inspect)</option>
 </select></label>
 <label>Mitigation<select id="advanced-linked-ability">
  <option value="none">None</option><option value="brace">Brace</option>
  <option value="repair">Use repair kit</option>
 </select></label>
 <button id="advanced-linked-step" type="button">Play linked turn</button>
 <button id="advanced-linked-reset" type="button">Reset linked campaign</button>
 <pre id="advanced-linked-state" role="status" aria-live="polite"></pre>
</fieldset>
<button id="advanced-save" type="button">Download verified savegame</button>
<button id="advanced-godot-export" type="button">Download playable Godot 4 game project</button>
<label>Restore portable savegame<input id="advanced-load" type="file" accept=".json,application/json"></label>
<button id="advanced-verify" type="button">Independently verify replay</button>
<div id="advanced-actions" aria-label="Advanced gameplay actions"></div>
<canvas id="advanced-canvas" width="470" height="250" role="img"
 aria-label="Reference gameplay map and telemetry"></canvas>
<pre id="advanced-state" role="status" aria-live="polite"></pre>
<pre id="advanced-physics-interop-proof" role="status" aria-live="polite"></pre>
<p><small>Advanced is the minimum design tier. Reference gameplay is not hardware certification.</small></p>
</fieldset>
<p><small>Playable preview where implemented; other editors validate authored system settings.
All writes still require exact-file review and human approval.</small></p>
</fieldset>
<p><small>Choose exact relative file location. Previous and demo entries stay read-only.</small></p>
<div id="files" aria-label="Project file tree"></div>
<p class="status" id="status" role="status"></p></section>
<section><h2>3. Source editor and review</h2><h3 id="file-name">Select a source file</h3>
<p><small id="hash"></small></p>
<textarea id="editor" spellcheck="false" aria-label="Original game source editor"></textarea>
<button id="download">Download edited source</button>
<h3>Targeted diff</h3><pre id="diff"></pre>
<label>Reason and supervised AI/user instruction
<textarea id="reason" rows="3" placeholder="Explain exactly why this game component needs changing."></textarea></label>
<button id="propose" disabled>Review proposed edit</button>
<p>Proposal: <code id="proposal"></code></p>
<label><input type="checkbox" id="approval"> I reviewed this exact file change</label>
<button id="commit" disabled>Commit reviewed edit to current game</button>
<p><small>No remote uploads, generated model execution, store publishing or hidden file-tree rewrites.</small></p>
</section></main><script>__SCRIPT__</script></body></html>
"""
def render_workspace_html(token: str)->bytes:
    from hashlib import sha256
    import base64,html,json,re
    if not re.fullmatch(r"[A-Za-z0-9_-]{20,150}",token):
        raise ValueError("locally secret session token required")
    script=SCRIPT.replace("__TOKEN__",json.dumps(token))
    def csp_digest(s):
        return "'sha256-"+base64.b64encode(sha256(s.encode()).digest()).decode()+"'"
    policy=("default-src 'none'; script-src "+csp_digest(script)+
            "; style-src "+csp_digest(STYLE)+
            "; connect-src 'self'; base-uri 'none'; object-src 'none'; "+
            "frame-src 'none'; img-src 'none'; form-action 'none'")
    return (TEMPLATE.replace("__CSP__",html.escape(policy,quote=True))
                    .replace("__STYLE__",STYLE)
                    .replace("__SCRIPT__",script)).encode()

__all__=["render_workspace_html"]
