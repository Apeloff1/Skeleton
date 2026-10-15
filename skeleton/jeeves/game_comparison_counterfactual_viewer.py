"""Offline user/Dragon scientific A/B emulator experiment dashboard.

Accepts only fully hash-verified native study receipts and outputs no source
game pixels, ROM bytes or music. All page values use textContent; embedded
JSON is script-escaped. Does not use a network service or update AI weights.
"""
from __future__ import annotations

import json
from collections.abc import Mapping

from .game_comparison_counterfactual import verify_counterfactual_input_result


def render_counterfactual_game_dashboard(report: Mapping[str, object]) -> str:
    verified=verify_counterfactual_input_result(report)
    # Only include bounded objective evidence and SHA references, not raw ROM,
    # PCM, screenshots, executable source paths or source game characters.
    games=[]
    for game in report["games"]:
        tracks=[]
        for kind,field in (("baseline","baseline_fresh_native_runs"),
                           ("perturbed","perturbed_fresh_native_runs")):
            for run in game[field]:
                tracks.append({
                    "arm":kind,"repeat":run["repeat"],
                    "step_points":[
                        {
                            "step":r["step"],"action":r["action"],
                            "screen_mean":r["observations"]["screen_mean"],
                            "audio_rms":r["observations"]["audio_rms"],
                            "visual_change":r["observations"]["visual_change"],
                            "native_frame_sha256":r["native_frame_sha256"],
                            "native_pcm_sha256":r["native_pcm_sha256"],
                            "receipt_chain_sha256":r["receipt_chain_sha256"],
                        } for r in run["receipts"]
                    ],
                    "last_evidence_sha256":run["last_evidence_sha256"],
                })
        games.append({
            "game_id":game["game_id"],"core_id":game["core_id"],
            "target_id":game["target_id"],
            "source_sha256":game["source_sha256"],
            "baseline_action":game["baseline_action"],
            "alternative_action":game["alternative_action"],
            "perturbation_step":game["perturbation_step"],
            "analysis":game["measured_analysis"],"tracks":tracks,
        })
    data={
        "source_study_id":report["source_study_id"],
        "result_sha256":report["result_sha256"],
        "verified_receipt_sha256":verified["verification_sha256"],
        "verified_native_actions":verified["native_action_observations_hash_checked"],
        "verified_fresh_worker_runs":verified["fresh_native_runs_hash_checked"],
        "games":games,
        "heldout_performance_improvement_established":False,
        "llm_weights_or_dragon_custody_promoted":False,
    }
    embedded=json.dumps(data,sort_keys=True,separators=(",",":"),ensure_ascii=True,
                        allow_nan=False).replace("<",r"\u003c").replace(">",r"\u003e").replace("&",r"\u0026")
    template=r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Jeeves/Dragon · Controlled Game Experiments</title>
<style>
:root{color-scheme:dark;background:#101827;color:#e8f2ff;font:14px system-ui,sans-serif}
body{max-width:1440px;margin:auto;padding:20px}
h1{font-size:23px}h2{font-size:18px}h3{font-size:15px}
p{line-height:1.4;color:#becce0}small{color:#b6c9d9}
header{display:flex;justify-content:space-between;flex-wrap:wrap;align-items:center;gap:12px}
.panel{padding:16px;border:1px solid #40546c;border-radius:12px;background:#1c2b40;margin:12px 0}
.metrics{display:grid;grid-template-columns:repeat(auto-fit,minmax(145px,1fr));gap:10px}
.metric{background:#152239;border-radius:8px;padding:10px;display:flex;flex-direction:column;gap:5px}
.metric strong{font-size:19px;overflow-wrap:anywhere}
select,button{background:#193650;color:#f3f8fe;border:1px solid #557998;border-radius:8px;padding:9px;font:inherit;cursor:pointer}
select{max-width:100%}
.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}
canvas{width:100%;height:180px;border-radius:8px;background:#0d1828;display:block}
details{margin-top:10px}summary{cursor:pointer}
table{width:100%;border-collapse:collapse}td,th{text-align:left;padding:8px;border-bottom:1px solid #465976;font-size:12px}
.scroll{max-height:340px;overflow:auto}code{font-size:11px;overflow-wrap:anywhere}
.legend{display:flex;flex-wrap:wrap;gap:16px;margin:8px 0}
.warning{color:#f0d497} .good{color:#bae4c1}
@media(max-width:900px){body{padding:12px}.grid{grid-template-columns:1fr}}
</style></head><body>
<header><div><h1>Controlled native game experiments</h1>
<small>Real worker A/B observations · no game content embedded · no training promotion</small></div>
<select id="game" aria-label="Select a studied game"></select></header>
<p>Each game was replayed with the same source media and core, changing precisely
one controller action. Audio/video changes and repeat consistency are <b>measurements</b>,
not a claim of game intelligence, causality of a specific mechanic, or improved LLM weights.</p>
<section id="summary" class="metrics"></section>
<section id="trial" class="panel"></section>
<div class="grid">
<section class="panel"><h2>Native visual-change evidence</h2>
<canvas id="visual" width="650" height="180" role="img" aria-label="Baseline and perturbed visual-change measurements by step"></canvas>
<div class="legend"><small>Blue: baseline</small><small>Amber: perturbed</small></div></section>
<section class="panel"><h2>Native audio-RMS evidence</h2>
<canvas id="audio" width="650" height="180" role="img" aria-label="Baseline and perturbed audio-RMS measurements by step"></canvas>
<div class="legend"><small>Blue: baseline</small><small>Amber: perturbed</small></div></section>
</div>
<section id="evidence" class="panel"></section>
<section class="panel"><h2>Promotion and epistemic gates</h2>
<p class="warning">Experiment record SHA integrity has been checked locally,
but independent execution attestation, source-rights verification, causal
mechanics discovery, held-out gameplay improvement and authorized model
weight promotion have not been established.</p></section>
<p><small>Exact study receipt <code id="root"></code> · verification <code id="verified"></code></small></p>
<script>
"use strict";
const report=__DATA__;
const $=id=>document.getElementById(id);
const txt=(name,value)=>{const el=document.createElement(name);el.textContent=String(value);return el};
const metric=(label,value)=>{const out=txt("div","");out.className="metric";
  out.append(txt("small",label),txt("strong",value));return out};
function draw(canvas,base,changed,key){
 const context=canvas.getContext("2d");if(!context)return;
 const tracks=[base,changed],colors=["#81c7eb","#eec187"];
 context.fillStyle="#0d1828";context.fillRect(0,0,650,180);
 const values=tracks.flatMap(arr=>arr.map(x=>Number(x[key])));
 const upper=Math.max(0.000001,...values.map(Math.abs));
 context.strokeStyle="#415772";context.lineWidth=1;
 for(let i=0;i<=4;i++){const y=16+i*37;context.beginPath();context.moveTo(20,y);context.lineTo(635,y);context.stroke()}
 tracks.forEach((rows,n)=>{
  context.strokeStyle=colors[n];context.lineWidth=2;context.beginPath();
  rows.forEach((point,i)=>{
   const x=22+i*600/Math.max(1,rows.length-1);
   const y=162-Math.min(1,Math.abs(Number(point[key]))/upper)*142;
   if(i===0)context.moveTo(x,y);else context.lineTo(x,y)
  });context.stroke()
 })
}
function render(){
 const id=$("game").value,game=report.games.find(x=>x.game_id===id);if(!game)return;
 const baseline=game.tracks.find(x=>x.arm==="baseline"&&x.repeat===1);
 const changed=game.tracks.find(x=>x.arm==="perturbed"&&x.repeat===1);
 const analysis=game.analysis,video=analysis.signal_comparison.video,audio=analysis.signal_comparison.audio;
 $("summary").replaceChildren(
  metric("Games",report.games.length),
  metric("Fresh core executions",report.verified_fresh_worker_runs),
  metric("Verified native steps",report.verified_native_actions),
  metric("Input step changed",game.perturbation_step),
  metric("Repeat-consistent",analysis.repeat_consistent_in_both_arms?"Yes":"No"),
  metric("Pre-input evidence matched",analysis.pre_intervention_controls_matched?"Yes":"No"),
  metric("Scientific evidence gate",analysis.scientific_evidence_status),
  metric("New AI weights",0)
 );
 const panel=$("trial");panel.replaceChildren(txt("h2",game.game_id+" · "+game.target_id+" · "+game.core_id));
 panel.append(txt("p","At native step "+game.perturbation_step+": "+game.baseline_action+" → "+game.alternative_action+
 " · other actions unchanged · source hash "+game.source_sha256));
 panel.append(txt("p","Video first difference: "+(video.first_observed_difference_step??"none")+
 " · PCM first difference: "+(audio.first_observed_difference_step??"none")+
 " · video stable within each arm: "+String(video.baseline_same_across_fresh_repeats&&video.perturbed_same_across_fresh_repeats)));
 const status=txt("p",
  analysis.pre_intervention_controls_matched
   ?"All recorded audio/video steps before changed input matched between paired arms."
   :"IMPORTANT: video/audio differed before input change; response is confounded and must not be treated as causal.","");
 status.className=analysis.post_intervention_observable_response_candidate?"good":"warning";
 panel.append(status);
 const diffs=txt("div","");diffs.className="metrics";
 Object.entries(analysis.measured_objective_changes).forEach(([name,value])=>diffs.append(metric(name,Number(value).toFixed(6))));
 panel.append(diffs);
 draw($("visual"),baseline.step_points,changed.step_points,"visual_change");
 draw($("audio"),baseline.step_points,changed.step_points,"audio_rms");
 const evidence=$("evidence");evidence.replaceChildren(txt("h2","Native controller/action and hash-chain evidence"));
 const details=document.createElement("details"),heading=txt("summary","Inspect each arm's actual step receipts");
 details.append(heading);
 const container=txt("div","");container.className="scroll";
 const table=document.createElement("table"),header=document.createElement("tr");
 ["Arm","Repeat","Step","Action","Frame SHA","PCM SHA","Step chain"].forEach(x=>header.append(txt("th",x)));
 table.append(header);
 game.tracks.forEach(track=>track.step_points.forEach(point=>{
  const row=document.createElement("tr");
  [track.arm,track.repeat,point.step,point.action,point.native_frame_sha256,
   point.native_pcm_sha256,point.receipt_chain_sha256].forEach(value=>{
    const td=txt("td",value);row.append(td)
  });
  table.append(row)
 }));
 container.append(table);details.append(container);evidence.append(details)
}
report.games.forEach(row=>{const option=txt("option",row.game_id);option.value=row.game_id;$("game").append(option)});
$("root").textContent=report.result_sha256;
$("verified").textContent=report.verified_receipt_sha256;
$("game").addEventListener("change",render);render();
</script></body></html>"""
    rendered=template.replace("__DATA__",embedded)
    if len(rendered.encode("utf-8"))>3*1024*1024:
        raise ValueError("Controlled native experiment dashboard exceeds 3 MiB")
    return rendered
