"""Offline, self-contained side-by-side game-study viewer for user and Jeeves.

Renders only actual emulator screenshots supplied by the native study runner.
The viewer never loads or transfers ROM data. User notes are exported to JSON
and must be re-imported through the reviewed manifest/CLI; the HTML is not a
database or a direct write path into Dragon's verified almanac.
"""
from __future__ import annotations

import json
from collections.abc import Mapping

MAX_HTML = 28 * 1024 * 1024


def render_comparison_html(report: Mapping[str, object]) -> str:
    if not isinstance(report, dict) or report.get("schema_version") != "skeleton.game.comparative_study_result.v1":
        raise ValueError("Viewer requires an actual comparative study result")
    data = json.dumps(report, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    if len(data) > 24 * 1024 * 1024:
        raise ValueError("Viewable comparative report exceeds bounded HTML evidence budget")
    # Script bodies must not treat untrusted game/note text as HTML or a closing
    # script tag. JSON content is parsed and inserted solely using textContent.
    safe = data.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    html = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Jeeves • Comparative Game Studio</title>
<style>
:root{color-scheme:dark;background:#111827;color:#edf2f7;font:15px system-ui,sans-serif}
*{box-sizing:border-box}body{margin:0;max-width:1600px;margin-inline:auto;padding:24px}
h1{font-size:25px;letter-spacing:-.5px;margin-bottom:6px}h2{font-size:18px}p{line-height:1.55}
small,.muted{color:#aab5c7}header{display:flex;flex-wrap:wrap;gap:16px;align-items:end;justify-content:space-between;margin-bottom:20px}
main{display:grid;grid-template-columns:minmax(0,1fr) 325px;gap:20px}
.panel{background:#192332;border:1px solid #354155;border-radius:12px;padding:18px;min-width:0}
.controls{display:flex;flex-wrap:wrap;align-items:center;gap:12px;margin-bottom:16px}
label{font-size:13px;color:#d8e2f0}select,input,textarea,button{background:#101827;color:#fff;border:1px solid #4b5a70;border-radius:8px;padding:9px;font:inherit;max-width:100%}
button{cursor:pointer;background:#294969;border-color:#386488}button:hover{background:#345b80}
textarea{width:100%;min-height:100px;resize:vertical}select{max-width:100%;min-width:130px}
.compare{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}
.scene{background:#111827;border:1px solid #364455;border-radius:10px;padding:12px}
.scene img{display:block;width:100%;height:auto;max-height:360px;object-fit:contain;image-rendering:auto;background:#000;border-radius:7px;margin:12px auto}
.scene h3{margin:0;font-size:17px;overflow-wrap:anywhere}.meta{font-size:12px;color:#bfcede;overflow-wrap:anywhere;line-height:1.6}
.stats{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;margin-top:12px}
.stat{padding:10px;background:#111827;border-radius:8px}.stat strong{display:block}
ol{padding-left:20px}li{margin-bottom:7px;overflow-wrap:anywhere}
.note{padding:10px;border-bottom:1px solid #374154;font-size:13px;overflow-wrap:anywhere}
.note strong{display:block;margin-bottom:5px}
.success{color:#8be2c3}.warning{color:#ffd29c}
pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px}
footer{margin-top:20px;color:#bbc6d5;font-size:12px}
@media(max-width:900px){main{grid-template-columns:1fr}}
@media(max-width:580px){.compare{grid-template-columns:1fr};body{padding:12px}}
</style>
</head>
<body>
<header>
<div><h1>Comparative Game Studio</h1><div class="muted">Jeeves + Dragon • observed native evidence / reviewable hypotheses</div></div>
<div id="overview" class="muted"></div>
</header>
<main>
<section class="panel">
<div class="controls">
<label>Compare games <select id="pair"></select></label>
<label>Checkpoint <select id="phase"><option>earlier</option><option>middle</option><option>after</option></select></label>
<label>Series <select id="series"><option value="all">All series</option></select></label>
</div>
<div id="question" class="muted"></div>
<div class="compare" id="comparison"></div>
<h2>Objective observations, not quality rankings</h2>
<div class="stats" id="stats"></div>
<h2>Series / evolution</h2><div id="timeline"></div>
<h2>Research synthesis &amp; ten-game curriculum proposals</h2>
<div id="synthesis"></div>
</section>
<aside class="panel">
<h2>Viewer & Dragon notes</h2>
<p class="muted">Notes remain attributed and linked to game-stage evidence. They do not change weights or approve legal reuse.</p>
<div id="notes"></div>
<h2>Write an observation</h2>
<label>Category <select id="dimension"></select></label>
<label>Claim type <select id="claim"><option>observation</option><option>interpretation</option><option>hypothesis</option></select></label>
<label>Apply to <select id="apply"><option value="pair">Both compared games</option><option value="left">Left game</option><option value="right">Right game</option></select></label>
<label>Note <textarea id="comment" maxlength="1000" placeholder="Evidence-based comparison, camera/movement/ambience observation, or a design hypothesis..."></textarea></label>
<div class="controls"><button id="add">Add to local draft</button><button id="export">Export notes JSON</button></div>
<div class="muted" id="noteStatus">Drafts remain in this page until exported; they are not submitted to Dragon automatically.</div>
</aside>
</main>
<footer>Image panels display only bounded previews from real approved native emulator runs; missing preview or failed core is shown as unavailable. No original ROM, BIOS, secret, model weights, or copied game data is distributed in this report.</footer>
<script type="application/json" id="report-data">__JSON_DATA__</script>
<script>
"use strict";
const report=JSON.parse(document.getElementById("report-data").textContent);
const gameMap=report.games||{};
const pairList=report.pairs||[];
const $=id=>document.getElementById(id);
const txt=(tag,content,cls)=>{const e=document.createElement(tag);e.textContent=String(content==null?"":content);if(cls)e.className=cls;return e};
const localNotes=[];
let activePairs=pairList;
const categories=["movement","input","combat","navigation","story","dialogue","camera","cutscene","character","npc","environment","pacing","challenge","reward","audio","music","ambience","visuals","interface","accessibility","emergence","economy","physics","mission","level_design","consequence","world_design","other"];
for(const category of categories){const o=txt("option",category);o.value=category;$("dimension").append(o)}
function option(label,value){const o=txt("option",label);o.value=value;return o}
function updatePairs(){
 const series=$("series").value;
 activePairs=pairList.filter(p=>series==="all"||[p.left_id,p.right_id].some(id=>gameMap[id]&&gameMap[id].series_id===series));
 const drop=$("pair");drop.replaceChildren();
 activePairs.forEach((p,i)=>{const a=gameMap[p.left_id],b=gameMap[p.right_id];drop.append(option((a?a.title:p.left_id)+" ↔ "+(b?b.title:p.right_id),String(i)))});
 render()
}
function stageFor(game,phase){return game&&game.status==="actual_native_observations_captured"&&game.phases?game.phases[phase]:null}
function card(id,phase){
 const g=gameMap[id],p=stageFor(g,phase),c=txt("article","", "scene");
 c.append(txt("h3",g?g.title:id),txt("div",g?(g.series_id+" • series #"+g.release_order+" • "+g.series_phase+" installment • "+g.core_id+" • "+g.target_id):"Not executed","meta"));
 if(!p){c.append(txt("p",g?g.status:"Unavailable or batch not selected","warning"));return c}
 if(typeof p.image_data_uri==="string"&&/^data:image\/png;base64,[a-zA-Z0-9+/=]+$/.test(p.image_data_uri)){
  const image=document.createElement("img");image.src=p.image_data_uri;image.alt="Actual bounded native screenshot for "+g.title+" at "+phase+" checkpoint";c.append(image);
 }else{c.append(txt("p","No native preview stored; raw frame SHA-256 remains available.","muted"))}
 c.append(txt("div","Step "+p.step+" • "+p.width+"×"+p.height+" • audio frames "+p.audio_frames,"meta"));
 if(g.study_local_tabular_training){c.append(txt("div","Study-local Q updates: "+g.study_local_tabular_training.updates_applied+" • policy "+g.study_local_tabular_training.trained_policy_sha256+" • NOT production LLM weights","meta"))}
 c.append(txt("div","Frame "+p.frame_sha256+" • evidence "+p.evidence_sha256,"meta"));
 c.append(txt("div","Mean pixel brightness "+Number(p.observations.screen_mean).toFixed(4)+" • Audio RMS "+Number(p.observations.audio_rms).toFixed(4),"meta"));
 if(p.signal_features){
  const v=p.signal_features.video||{},a=p.signal_features.audio||{};
  c.append(txt("div","Visual structure: luminance entropy "+Number(v.luminance_entropy_bits||0).toFixed(3)+" bits • edge ratio "+Number(v.scan_edge_ratio||0).toFixed(4)+" • mean color spread "+Number(v.mean_channel_range||0).toFixed(4),"meta"));
  c.append(txt("div","Audio texture: silence fraction "+Number(a.silence_fraction||0).toFixed(4)+" • zero crossings "+Number(a.zero_crossing_fraction||0).toFixed(4)+" • stereo difference "+Number(a.stereo_energy_imbalance||0).toFixed(4),"meta"));
 }
 return c
}
function renderSynthesis(){
 const dest=$("synthesis"),s=report.synthesis||{};
 dest.replaceChildren();
 dest.append(txt("p","Only independently captured video/audio metrics and attributed notes are surfaced. Proposed parameters are not actual trained weights.","muted"));
 (s.training_cohorts||[]).forEach(c=>{
  const p=txt("div","Cohort "+(c.cohort_index+1)+" • "+c.game_count+" observed games • "+c.game_ids.join(", ")+" • training pending rights + held-out evaluation","note");dest.append(p)
 });
 (s.build_parameter_hypotheses||[]).slice(0,30).forEach(p=>{
  dest.append(txt("div","Parameter hypothesis: "+p.parameter_name+" • "+p.proposal_count+" proposals • "+(p.conflicting_values_or_units?"conflicting values; independent review required":"not experimentally verified"),"note"))
 });
}
function currentPair(){return activePairs[Number($("pair").value)||0]||null}
function render(){
 const p=currentPair(),phase=$("phase").value;
 $("comparison").replaceChildren();$("stats").replaceChildren();$("question").replaceChildren();$("timeline").replaceChildren();$("notes").replaceChildren();
 if(!p){$("comparison").append(txt("p","No comparison matches this series. Select another series."));return}
 $("comparison").append(card(p.left_id,phase),card(p.right_id,phase));
 $("question").append(txt("p",(p.questions&&p.questions.length?p.questions.join(" • "):"Choose a stage to compare native observations and write your own evidence-grounded notes.")));
 const phaseMatch=(p.phase_comparisons||[]).find(x=>x.phase===phase);
 if(phaseMatch){
  for(const [label,value] of [
    ["Exact frame hashes equal",phaseMatch.same_exact_frame_sha256],
    ["Exact PCM hashes equal",phaseMatch.same_exact_audio_sha256],
    ["Brightness absolute difference",Number(phaseMatch.screen_mean_absolute_difference).toFixed(6)],
    ["Audio RMS absolute difference",Number(phaseMatch.audio_rms_absolute_difference).toFixed(6)]
  ]){const box=txt("div","", "stat");box.append(txt("small",label),txt("strong",value));$("stats").append(box)}
  const texture=phaseMatch.non_reconstructive_signal_texture_differences||{};
  for(const [name,label] of [
   ["video_luminance_entropy_bits_absolute_difference","Luminance entropy difference"],
   ["video_scan_edge_ratio_absolute_difference","Visual edge difference"],
   ["audio_zero_crossing_fraction_absolute_difference","Audio texture zero-crossing difference"],
   ["audio_silence_fraction_absolute_difference","Audio silence difference"]
  ]){
   if(Number.isFinite(texture[name])){
    const box=txt("div","", "stat");
    box.append(txt("small",label),txt("strong",Number(texture[name]).toFixed(6)));
    $("stats").append(box);
   }
  }
 }else{$("stats").append(txt("p","One or both games have no qualified native observations in this report.","warning"))}
 const ids=new Set([p.left_id,p.right_id]);
 const relevant=(report.series||[]).filter(row=>row.ordered_installments.some(item=>ids.has(item.game_id)));
 for(const s of relevant){
  const box=txt("section","");box.append(txt("h3",s.series_id));
  const list=document.createElement("ol");
  s.ordered_installments.forEach(g=>list.append(txt("li",(gameMap[g.game_id]?.title||g.game_id)+" • "+g.era+" • "+(g.release_year??"undated")+" • "+g.native_evidence_status)));
  box.append(list);$("timeline").append(box)
 }
 const notes=[...(report.observer_notes||[]),...localNotes].filter(n=>n.game_ids.some(id=>ids.has(id)));
 notes.forEach(n=>{const box=txt("div","", "note");box.append(txt("strong",n.author+" • "+n.dimension+" • "+n.claim_type+" • "+n.review_status),txt("div",n.text),txt("small","Referenced: "+n.game_ids.join(", ")+" / "+n.checkpoint+" • "+(n.knowledge_status||"viewer draft pending review")));if(n.build_parameter_candidate){box.append(txt("small"," Build parameter: "+n.build_parameter_candidate.name+"="+n.build_parameter_candidate.value+" "+n.build_parameter_candidate.units+" (unverified hypothesis)"))};$("notes").append(box)});
 if(!notes.length)$("notes").append(txt("p","No viewer/Dragon notes recorded for this pair yet.","muted"))
}
function addNote(){
 const p=currentPair();if(!p)return;
 const text=$("comment").value.trim(),apply=$("apply").value;
 if(!text||text.length>1000){$("noteStatus").textContent="Enter a 1–1000 character observation.";return}
 const id=apply==="left"?[p.left_id]:apply==="right"?[p.right_id]:[p.left_id,p.right_id];
 const n={
  note_id:"viewer_"+Date.now().toString(36)+"_"+String(localNotes.length),
  author:"viewer",game_ids:id,checkpoint:$("phase").value,
  dimension:$("dimension").value,claim_type:$("claim").value,
  text,review_status:"pending",build_parameter:null
 };
 localNotes.push(n);$("comment").value="";$("noteStatus").textContent=localNotes.length+" local notes drafted. Export JSON to preserve them.";render()
}
function exportNotes(){
 const all=(report.observer_notes||[]).map(n=>({
  note_id:n.note_id,author:n.author,game_ids:n.game_ids,checkpoint:n.checkpoint,
  dimension:n.dimension,claim_type:n.claim_type,text:n.text,
  review_status:n.review_status,build_parameter:n.build_parameter
 })).concat(localNotes);
 const payload={schema_version:"skeleton.game.comparison_notes.v1",study_id:report.study_id,notes:all};
 const url=URL.createObjectURL(new Blob([JSON.stringify(payload,null,2)],{type:"application/json"}));
 const a=document.createElement("a");a.href=url;a.download=report.study_id+"_viewer_notes.json";document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),5000);
 $("noteStatus").textContent="Notes JSON exported. Re-import through the operator CLI for review; nothing was sent over the network."
}
const seen=new Set();
(report.series||[]).forEach(s=>{if(!seen.has(s.series_id)){seen.add(s.series_id);$("series").append(option(s.series_id,s.series_id))}});
$("overview").textContent=report.game_observations_completed+" / "+report.planned_total_game_count+" game observations • "+pairList.length+" pairs • ≤"+report.maximum_parallel_native_game_sessions+" native sessions • "+(report.games_with_study_local_q_updates||0)+" locally trained game Q-policies";
$("series").addEventListener("change",updatePairs);
$("phase").addEventListener("change",render);
$("pair").addEventListener("change",render);
$("add").addEventListener("click",addNote);
$("export").addEventListener("click",exportNotes);
renderSynthesis();
updatePairs();
</script>
</body>
</html>
""".replace("__JSON_DATA__", safe)
    if len(html.encode("utf-8")) > MAX_HTML:
        raise ValueError("Comparative viewer exceeds 28 MiB; omit native screenshots or render one batch")
    return html
