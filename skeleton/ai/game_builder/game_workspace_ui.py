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
 if(state.finished||state.failed){
  c.fillStyle=state.finished?"#a2f5cb":"#ffaba6";
  c.fillText(state.finished?"Completed":"Defeat",W-100,20);
 }
}

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
let selectedCityParcel=0;
function renderAdvancedActions(actions){
 const target=$("advanced-actions");target.replaceChildren();
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
 const nativeSourceFamilies=new Set(["puzzle","platformer","deck_battler",
  "shooter","tactics","tower_defense","racing","survival","farming",
  "factory","colony"]);
 $("advanced-godot-export").disabled=!nativeSourceFamilies.has(advancedSession.editor);
 $("advanced-godot-export").title=nativeSourceFamilies.has(advancedSession.editor)?
  "Package original Godot source; native hardware verification is a separate CI gate":
  "This original editor has reference gameplay only; an independent native source engine is not implemented";
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
  advancedCommands=[];showAdvanced(reply);
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
  if(!advancedSession||(!["puzzle","platformer","deck_battler","shooter","tactics","tower_defense","racing","survival","farming","factory"].includes(advancedSession.editor)&&advancedSession.editor!=="colony"))
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
<button id="advanced-save" type="button">Download verified savegame</button>
<button id="advanced-godot-export" type="button">Download playable Godot 4 game project</button>
<label>Restore portable savegame<input id="advanced-load" type="file" accept=".json,application/json"></label>
<button id="advanced-verify" type="button">Independently verify replay</button>
<div id="advanced-actions" aria-label="Advanced gameplay actions"></div>
<canvas id="advanced-canvas" width="470" height="250" role="img"
 aria-label="Reference gameplay map and telemetry"></canvas>
<pre id="advanced-state" role="status" aria-live="polite"></pre>
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
