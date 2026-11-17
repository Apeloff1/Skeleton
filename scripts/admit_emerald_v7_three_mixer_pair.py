"""Two-form original-byte gate for V7 actual Three.AnimationMixer contact evidence.

Only a complete, independently rehashed Pathfinder AND Archivist pair with
full 54 sampled poses each and zero new contacts in the three reviewed
anatomical pairs can receive a *sampled* acceptance receipt. The receipt
explicitly denies complete continuous, browser-device, RTX, art and release
qualification; original model adoption is never performed.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import stat

import check_emerald_v7_three_mixer_trace as traces
import emerald_v6_crossfade_screen as original

SCHEMA="skeleton.emerald.v7.actual-three-two-stage-sampled-admission.v1"
CONTACT_SCHEMA="skeleton.emerald.v7.actual-three-joints-contact-screen.v1"
STAGES=("pathfinder","archivist")
POSES=54
SHARED_KEYS=("all_anatomical_pairs_qualified","continuous_collision_qualified",
             "physical_webgl_tested","artist_approved","physical_rtx_verified",
             "release_qualified")
CONTACT_BUDGET=12*1024**2

def require(x,reason):
 if not x:raise ValueError(reason)

def sha(path):
 with Path(path).open("rb") as f:
  return hashlib.file_digest(f,"sha256").hexdigest()

def read_bounded(path,maximum):
 path=Path(path)
 require(path.is_file() and not path.is_symlink()
         and 0<path.stat().st_size<=maximum,
         "missing, linked or oversized source evidence")
 raw=path.read_bytes()
 require(len(raw)<=maximum,"bounded evidence changed while being read")
 return json.loads(raw),hashlib.sha256(raw).hexdigest()

def model_pin(root,stage):
 require(stage in STAGES,"unknown original donor stage")
 path=Path(root)/(stage+".glb")
 expected,digest=traces.PINS[stage]
 require(path.is_file() and not path.is_symlink()
         and (path.stat().st_size,sha(path))==(expected,digest),
         "missing exact 114MB V7 original donor model for "+stage)
 return {"stage":stage,"model_sha256":digest,"model_bytes":expected,
         "actual_original_model_sha_rechecked":True}

def verify_contact(report,stage,trace,trace_sha):
 expected_size,expected_sha=traces.PINS[stage]
 require(report.get("schema")==CONTACT_SCHEMA and
         report.get("stage")==stage and
         report.get("original_model_sha256")==expected_sha and
         report.get("actual_three_trace_sha256")==trace_sha and
         report.get("three_revision")=="186" and
         report.get("source_crossfade_seconds")==.22 and
         report.get("sampled_poses")==POSES and
         report.get("sampled_anatomical_pair_count")==len(original.PAIRS)==3 and
         report.get("reviewed_tool_sha256")==original.TOOLS and
         report.get("all_sampled_source_routes_processed") is True,
         "wrong source-mixer trace, original GLB, or reviewed contact tool identity")
 require(all(report.get(flag) is False for flag in (
    "all_anatomical_pairs_qualified","arbitrary_real_browser_playheads_qualified",
    "continuous_collision_qualified","physical_webgl_tested",
    "artist_approved","physical_rtx_verified","release_qualified")),
    "sampled Three evidence attempts full continuous, device or release approval")
 require(trace.get("samples_per_route")==9 and
         trace.get("total_sampled_poses")==POSES,
         "wrong original per-transition Three sample density")
 records=report.get("samples")
 require(isinstance(records,list) and len(records)==POSES,
         "missing or extra original Three triangle-contact samples")
 source=[pose for route in trace["routes"] for pose in route["samples"]]
 require(len(source)==POSES,"source mixer trace truncated")
 collision=weld=near=0
 worst_world_error=0.
 for index,(sample,pose) in enumerate(zip(records,source)):
  require(sample.get("sample_index")==index and
          sample.get("from_clip")==pose["from_clip"] and
          sample.get("to_clip")==pose["to_clip"] and
          sample.get("alpha")==pose["alpha"],
          "collision witness is not bound to its exact Three joint pose")
  matrix_error=sample.get("max_mixer_world_matrix_error")
  require(type(matrix_error) in (int,float) and math.isfinite(matrix_error)
          and 0<=matrix_error<=5e-5,
          "original Three and independently recomposed world matrices differ")
  worst_world_error=max(worst_world_error,matrix_error)
  pairs=sample.get("pairs")
  require(isinstance(pairs,list) and
          [p.get("pair") for p in pairs]==[a+"__"+b for a,b in original.PAIRS],
          "missing, duplicated or rearranged anatomical contact witness")
  for pair in pairs:
   require(all(type(pair.get(key)) is int and pair[key]>=0 for key in (
       "new_independent_contact_pairs","shared_index_bind_seam_candidates",
       "within_8mm_not_contact","candidate_pairs","broadphase_visits")),
       "negative or noninteger original-source anatomical witness count")
  counts={
    "new_independent_contact_pairs":sum(x["new_independent_contact_pairs"] for x in pairs),
    "shared_index_bind_seam_candidates":sum(x["shared_index_bind_seam_candidates"] for x in pairs),
    "within_8mm_not_contact":sum(x["within_8mm_not_contact"] for x in pairs),
  }
  require(all(sample.get(key)==v for key,v in counts.items()),
          "per-pair collision contacts do not reconcile to sampled Three pose")
  collision+=counts["new_independent_contact_pairs"]
  weld+=counts["shared_index_bind_seam_candidates"]
  near+=counts["within_8mm_not_contact"]
 require(report.get("new_independent_contact_occurrences")==collision and
         report.get("preexisting_bind_seam_occurrences")==weld and
         report.get("near_margin_pair_occurrences")==near,
         "sampled contact totals suppress source witnesses")
 return {
  "stage":stage,
  "source_glb_sha256":expected_sha,
  "original_three_poses_checked":POSES,
  "reviewed_anatomical_pair_types":3,
  "new_independent_contact_occurrences":collision,
  "unqualified_8mm_near_margin_occurrences":near,
  "unqualified_inherited_attachment_seam_occurrences":weld,
  "worst_independent_world_matrix_error":worst_world_error,
  "source_triangle_contacts_reexecuted_by_this_gate":False,
  "sampled_three_mixer_contacts_clear":collision==0,
  "full_continuous_collision_qualified":False,
  "real_browser_device_verified":False,
  "artist_approved":False,"physical_rtx_verified":False,
  "release_qualified":False,
 }

def admit(originals,trace_dir,contact_dir,output):
 output=Path(output)
 require(output.parent.is_dir() and not output.parent.is_symlink()
         and not os.path.lexists(output),
         "trusted unused two-form original sampled acceptance receipt required")
 results=[]
 for stage in STAGES:
  model=model_pin(originals,stage)
  source_path=Path(trace_dir)/(stage+"-three-mixer.json")
  contact_path=Path(contact_dir)/(stage+"-actual-three-contacts.json")
  trace,trace_sha=read_bounded(source_path,traces.MAX_REPORT_BYTES)
  trace_check=traces.verify(trace,stage,Path(originals)/(stage+".glb"))
  require(trace_check["full_model_sha_independently_rechecked"] is True
          and trace_check["sampled_poses"]==POSES,
          "incomplete original Three or missing actual model SHA proof")
  contact,contact_sha=read_bounded(contact_path,CONTACT_BUDGET)
  result=verify_contact(contact,stage,trace,trace_sha)
  result.update({
    "original_model_bytes":model["model_bytes"],
    "actual_original_model_sha_rechecked":True,
    "source_three_trace_sha256":trace_sha,
    "reviewed_contact_report_sha256":contact_sha,
  })
  results.append(result)
 require(len(results)==2 and
         sum(x["original_three_poses_checked"] for x in results)==108,
         "missing original evolution stage's complete source-mixer evidence")
 total_contacts=sum(x["new_independent_contact_occurrences"] for x in results)
 # A positive triangle intersection is a blocking witness. In particular,
 # do not silently convert a failure into a qualifying two-model receipt.
 require(total_contacts==0,
         "real Three crossfade introduces source-supported anatomy contacts; review V7 before adoption")
 receipt={
  "schema":SCHEMA,
  "original_donor_sha256":traces.DONOR,
  "model_stages":list(STAGES),
  "exact_original_glb_count":2,
  "actual_three_library_revision":"186",
  "source_crossfade_seconds":.22,
  "sampled_three_pose_count":108,
  "reviewed_anatomical_pair_types":3,
  "sampled_evolution_family_admitted":True,
  "actual_three_mixer_collisions_reexecuted_by_this_gate":False,
  "source_original_models_sha_rechecked":True,
  "measured_unqualified_near_margin_occurrences":
       sum(x["unqualified_8mm_near_margin_occurrences"] for x in results),
  "measured_unqualified_attachment_seam_occurrences":
       sum(x["unqualified_inherited_attachment_seam_occurrences"] for x in results),
  "source_results":results,
  "all_anatomical_pairs_qualified":False,
  "arbitrary_browser_loop_playheads_qualified":False,
  "continuous_collision_qualified":False,
  "real_browser_gpu_tested":False,
  "artist_approved":False,
  "physical_rtx_verified":False,
  "remote_original_git_publication_verified":False,
  "release_qualified":False,
 }
 with output.open("x",encoding="utf-8") as dest:
  json.dump(receipt,dest,indent=2,allow_nan=False)
  dest.write("\n");dest.flush();os.fsync(dest.fileno())
 return receipt

def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument("--original-models",type=Path,required=True)
 p.add_argument("--three-traces",type=Path,required=True)
 p.add_argument("--contact-reports",type=Path,required=True)
 p.add_argument("--output",type=Path,required=True)
 args=p.parse_args()
 summary=admit(args.original_models,args.three_traces,
               args.contact_reports,args.output)
 print(json.dumps({k:v for k,v in summary.items() if k!="source_results"},indent=2))
if __name__=="__main__":
 main()
