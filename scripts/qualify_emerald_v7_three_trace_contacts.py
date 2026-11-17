"""Run reviewed triangle contacts on actual Three 0.186 V7 mixer joint traces.

Unlike the previous approximated local-slerp path, the input joint arrays are
sampled by the genuine Three.AnimationMixer and AnimationAction.crossFadeFrom
over the pinned .22s envelope. This CPU oracle still screens only three
anatomical region pair types at sampled times, not full CCD, browser rendering,
human art, Unreal or physical RTX. Original model/tool SHA is mandatory.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import time

import numpy as np
from scipy.spatial.transform import Rotation
import emerald_v6_crossfade_screen as geometry
import check_emerald_v7_three_mixer_trace as tracecheck

SCHEMA="skeleton.emerald.v7.actual-three-joints-contact-screen.v1"
PROGRESS="skeleton.emerald.v7.actual-three-contact-progress.v1"
MAX_TRACE_BYTES=tracecheck.MAX_REPORT_BYTES
STAGES=("pathfinder","archivist")
MAX_SAMPLE_SECONDS=7200

def require(value,why):
 if not value:raise ValueError(why)

def digest(path):
 with Path(path).open("rb") as stream:
  return hashlib.file_digest(stream,"sha256").hexdigest()

def independent_world_matrices(g,t,q):
 """Rebuild source skeleton world transforms from local Three trace data."""
 require(t.shape==(108,3) and q.shape==(108,4) and
         np.isfinite(t).all() and np.isfinite(q).all(),
         "missing or invalid 108-joint source transform")
 m=np.broadcast_to(np.eye(4),(108,4,4)).copy()
 m[:,:3,:3]=Rotation.from_quat(q).as_matrix()
 m[:,:3,3]=t
 parents=g["parents"]
 require(len(parents)==108 and int(parents[0])<0 and
         all(0<=int(parents[i])<i for i in range(1,108)),
         "original source rig cannot be independently reconstructed")
 for i in range(1,108):
  m[i]=m[int(parents[i])] @ m[i]
 return m

def posed_vertices_from_trace(g,joints):
 require(len(joints)==108,"missing actual Three joints")
 t=np.array([entry["local_translation"] for entry in joints],dtype=np.float64)
 q=np.array([entry["local_quaternion"] for entry in joints],dtype=np.float64)
 matrices=np.array([entry["world_matrix"] for entry in joints],dtype=np.float64)
 require(matrices.shape==(108,16) and np.isfinite(matrices).all(),
         "nonfinite or wrong-size actual Three world matrices")
 actual=matrices.reshape((108,4,4)).transpose((0,2,1))
 independently=independent_world_matrices(g,t,q)
 error=float(np.max(np.abs(actual-independently)))
 require(math.isfinite(error) and error<=5e-5,
         "actual Three matrix hierarchy and independent source skin diverge")
 vertices=geometry.skin(g,t,q)
 require(vertices.shape==(365997,3) and np.isfinite(vertices).all(),
         "original V7 skinned mesh is truncated or nonfinite")
 return vertices,error

def flattened(trace):
 for route in trace["routes"]:
  for pose in route["samples"]:
   yield pose

def reviewed_input(trace_path,model,tools,stage):
 require(stage in STAGES,"unsupported original V7 evolution stage")
 trace_path=Path(trace_path)
 require(trace_path.is_file() and not trace_path.is_symlink() and
         0<trace_path.stat().st_size<=MAX_TRACE_BYTES,
         "missing or oversized actual Three trace")
 model=Path(model)
 expected,sha=tracecheck.PINS[stage]
 require(model.is_file() and not model.is_symlink() and
         model.stat().st_size==expected and digest(model)==sha,
         "original V7 model GLB SHA or byte count differs")
 report=json.loads(trace_path.read_bytes())
 inspected=tracecheck.verify(report,stage,model)
 require(inspected["full_model_sha_independently_rechecked"] is True,
         "exact original V7 GLB SHA not independently confirmed")
 auditor,seam=geometry.vetted_tools(tools)
 return report,auditor,seam

def journal_contract(data,model_sha,trace_sha,samples):
 require(data.get("schema")==PROGRESS and
         data.get("original_model_sha256")==model_sha and
         data.get("actual_three_trace_sha256")==trace_sha and
         data.get("reviewed_tool_sha256")==geometry.TOOLS and
         data.get("sampled_collision_clearance")==False and
         data.get("continuous_collision_qualified")==False and
         data.get("real_browser_device_qualified")==False and
         data.get("release_qualified")==False,
         "resume checkpoint has wrong exact sources or forged approval")
 rows=data.get("samples")
 require(isinstance(rows,list) and len(rows)<=len(samples),
         "unqualified number of saved collision frames")
 for i,row in enumerate(rows):
  source=samples[i]
  require(row.get("from_clip")==source["from_clip"] and
          row.get("to_clip")==source["to_clip"] and
          row.get("alpha")==source["alpha"] and
          row.get("sample_index")==i and
          type(row.get("new_independent_contact_pairs")) is int and
          row["new_independent_contact_pairs"]>=0 and
          type(row.get("within_8mm_not_contact")) is int and
          row["within_8mm_not_contact"]>=0 and
          type(row.get("max_mixer_world_matrix_error")) in (int,float) and
          math.isfinite(row["max_mixer_world_matrix_error"]) and
          row["max_mixer_world_matrix_error"]<=5e-5 and
          isinstance(row.get("pairs"),list) and
          [x.get("pair") for x in row["pairs"]]==
             [a+"__"+b for a,b in geometry.PAIRS],
          "reordered, missing or malformed resumed actual Three contact witness")
 return rows

def save_journal(path,model_sha,trace_sha,rows,total):
 path=Path(path)
 temp=path.parent/("."+path.name+".pending")
 require(not os.path.lexists(temp),"concurrent checkpoint writer")
 document={
  "schema":PROGRESS,
  "original_model_sha256":model_sha,
  "actual_three_trace_sha256":trace_sha,
  "reviewed_tool_sha256":geometry.TOOLS,
  "complete_source_pose_count":len(rows),
  "remaining_source_pose_count":total-len(rows),
  "sampled_collision_clearance":False,
  "continuous_collision_qualified":False,
  "real_browser_device_qualified":False,
  "release_qualified":False,
  "samples":rows,
 }
 try:
  with temp.open("x",encoding="utf-8") as stream:
   json.dump(document,stream,indent=2,allow_nan=False)
   stream.write("\n")
   stream.flush();os.fsync(stream.fileno())
  os.replace(temp,path)
 finally:
  if temp.exists():temp.unlink()

def evaluate(stage,model,tools,trace_path,time_budget=1200,checkpoint=None,resume=False):
 require(stage in STAGES and type(time_budget) in (int,float) and
         math.isfinite(time_budget) and 60<=time_budget<=MAX_SAMPLE_SECONDS,
         "unsupported stage or unbounded geometry budget")
 report,auditor,seam=reviewed_input(trace_path,model,tools,stage)
 source_poses=list(flattened(report))
 expected,sha=tracecheck.PINS[stage]
 require(len(source_poses)==report["total_sampled_poses"],
         "original Three trace sample inventory differs")
 trace_sha=digest(trace_path)
 if checkpoint is None:
  require(not resume,"resume requires a previously saved source checkpoint")
  saved=[]
 else:
  checkpoint=Path(checkpoint)
  require(checkpoint.parent.is_dir() and not checkpoint.parent.is_symlink()
          and checkpoint.exists()==resume and not checkpoint.is_symlink(),
          "trusted new checkpoint or exact previous checkpoint required")
  saved=journal_contract(json.loads(checkpoint.read_bytes()),sha,trace_sha,source_poses) if resume else []
 started=time.monotonic()
 deadline=started+time_budget
 original=auditor.GLB(Path(model),expected,sha,stage)
 try:
  g=original.geometry()
  groups=geometry.anatomy(g)
  rows=list(saved)
  for index,pose in enumerate(source_poses):
   if index<len(saved):continue
   require(time.monotonic()<deadline,"actual Three pose budget expired; work remains unqualified")
   vertices,error=posed_vertices_from_trace(g,pose["joints"])
   contacts=geometry.contact_check(vertices,g,groups,auditor,seam,deadline)
   row={
     "sample_index":index,"from_clip":pose["from_clip"],
     "to_clip":pose["to_clip"],"alpha":pose["alpha"],
     "max_mixer_world_matrix_error":error,
     **contacts,
   }
   rows.append(row)
   if checkpoint is not None:
    save_journal(checkpoint,sha,trace_sha,rows,len(source_poses))
  total_contacts=sum(row["new_independent_contact_pairs"] for row in rows)
  total_near=sum(row["within_8mm_not_contact"] for row in rows)
  total_weld=sum(row["shared_index_bind_seam_candidates"] for row in rows)
  require(len(rows)==len(source_poses),"incomplete actual Three contact evidence")
  return {
   "schema":SCHEMA,
   "stage":stage,
   "original_model_sha256":sha,
   "actual_three_trace_sha256":trace_sha,
   "three_revision":report["three_revision"],
   "source_crossfade_seconds":.22,
   "sampled_poses":len(rows),
   "sampled_anatomical_pair_count":len(geometry.PAIRS),
   "reviewed_tool_sha256":geometry.TOOLS,
   "new_independent_contact_occurrences":total_contacts,
   "near_margin_pair_occurrences":total_near,
   "preexisting_bind_seam_occurrences":total_weld,
   "all_sampled_source_routes_processed":True,
   "all_anatomical_pairs_qualified":False,
   "arbitrary_real_browser_playheads_qualified":False,
   "continuous_collision_qualified":False,
   "physical_webgl_tested":False,
   "artist_approved":False,
   "physical_rtx_verified":False,
   "release_qualified":False,
   "samples":rows,
  }
 finally:
  try:original.close()
  except BufferError:pass

def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument("--stage",choices=STAGES,required=True)
 p.add_argument("--model",type=Path,required=True)
 p.add_argument("--tools",type=Path,required=True)
 p.add_argument("--trace",type=Path,required=True)
 p.add_argument("--output",type=Path,required=True)
 p.add_argument("--time-budget-seconds",type=float,default=1200)
 p.add_argument("--checkpoint",type=Path)
 p.add_argument("--resume",action="store_true")
 a=p.parse_args()
 require(a.output.parent.is_dir() and not a.output.parent.is_symlink()
         and not os.path.lexists(a.output),
         "trusted unused completed contact report path required")
 report=evaluate(a.stage,a.model,a.tools,a.trace,
                 a.time_budget_seconds,a.checkpoint,a.resume)
 with a.output.open("x",encoding="utf-8") as stream:
  json.dump(report,stream,indent=2,allow_nan=False)
  stream.write("\n");stream.flush();os.fsync(stream.fileno())
 print(json.dumps({key:value for key,value in report.items() if key!="samples"},indent=2))
 if report["new_independent_contact_occurrences"]>0:
  raise SystemExit(2)
if __name__=="__main__":main()
