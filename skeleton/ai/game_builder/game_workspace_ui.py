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
