"""Exact V7 original-byte pose parity: actual Three 0.186 vs older SLERP approximation.

Measures *disagreement*, not mesh contact. Each Three frame is checked against
a fresh, independent evaluation of the exact original GLB's original animation
accessors, including unchanged bind tracks, through the reviewed Python source
interpolator. This does not approve source-level, browser or full CCD results.
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
import check_emerald_v7_three_mixer_trace as verified
import emerald_v6_crossfade_screen as reference

SCHEMA="skeleton.emerald.v7.actual-three-versus-source-slerp.v1"
MAX_REPORT_BYTES=verified.MAX_REPORT_BYTES
MAX_ANGLE_RAD=math.radians(.5)
MAX_TRANSLATION_M=.005
SAMPLES=54
REVIEWED_JOINTS=108

def require(ok,reason):
 if not ok:raise ValueError(reason)

def sha(path):
 with Path(path).open("rb") as source:
  return hashlib.file_digest(source,"sha256").hexdigest()

def source_pose_delta(t,q,real):
 """Measure translational and sign-invariant angular errors for 108 joints.

 Quaternions use the glTF/Three [x,y,z,w] convention; q and -q represent
 identical rotations. Angular errors are on [0,pi] in radians.
 """
 require(isinstance(t,np.ndarray) and isinstance(q,np.ndarray)
         and t.shape==(REVIEWED_JOINTS,3) and
         q.shape==(REVIEWED_JOINTS,4) and
         np.isfinite(t).all() and np.isfinite(q).all()
         and isinstance(real,list) and len(real)==REVIEWED_JOINTS,
         "invalid original 108-joint pose comparison")
 observed_t=np.asarray([j.get("local_translation") for j in real],dtype=np.float64)
 observed_q=np.asarray([j.get("local_quaternion") for j in real],dtype=np.float64)
 require(observed_t.shape==t.shape and observed_q.shape==q.shape
         and np.isfinite(observed_t).all() and np.isfinite(observed_q).all()
         and all(j.get("joint")==i for i,j in enumerate(real)),
         "Three joint order, translation or quaternion differs")
 lengths0=np.linalg.norm(q,axis=1)
 lengths1=np.linalg.norm(observed_q,axis=1)
 require(np.all(abs(lengths0-1)<3e-4) and
         np.all(abs(lengths1-1)<3e-4),
         "source or Three quaternion is not normalized")
 dot=np.abs(np.sum(q*observed_q,axis=1)/(lengths0*lengths1))
 dot=np.clip(dot,-1.,1.)
 radians=2*np.arccos(dot)
 distance=np.linalg.norm(t-observed_t,axis=1)
 require(np.isfinite(radians).all() and np.isfinite(distance).all(),
         "nonfinite observed V7 pose disagreement")
 return radians,distance

def phase_reference(original,geometry,route,sample):
 left,right=route
 left_t=float(sample["source_old_time_s"])
 right_t=float(sample["source_new_time_s"])
 left_d,translation_a,rotation_a=reference.local_pose(original,geometry,left,left_t)
 right_d,translation_b,rotation_b=reference.local_pose(original,geometry,right,right_t)
 require(left_d>=.22 and right_d>=.22,
         "reviewed original crossfade clip shortened")
 alpha=float(sample["alpha"])
 require(math.isfinite(alpha) and 0<=alpha<=1,
         "invalid original Three fade alpha")
 translation=(1-alpha)*translation_a+alpha*translation_b
 rotation=reference.slerp_rows(rotation_a,rotation_b,alpha)
 return translation,rotation

def analyze(stage,model,trace,source_tools):
 require(stage in verified.PINS,"unsupported V7 original evolution level")
 model=Path(model);trace=Path(trace)
 length,pin=verified.PINS[stage]
 require(model.is_file() and not model.is_symlink() and
         (model.stat().st_size,sha(model))==(length,pin),
         "exact original V7 model bytes differ")
 require(trace.is_file() and not trace.is_symlink()
         and 0<trace.stat().st_size<=MAX_REPORT_BYTES,
         "original Three full 54-pose trace missing")
 recorded=json.loads(trace.read_bytes())
 checked=verified.verify(recorded,stage,model)
 require(checked["sampled_poses"]==SAMPLES and
         checked["full_model_sha_independently_rechecked"] is True,
         "incomplete exact original 54-pose source mixer report")
 auditor,_seams=reference.vetted_tools(source_tools)
 original=auditor.GLB(model,length,pin,stage)
 try:
  geometry=original.geometry()
  rows=[]
  total_mean_angle=total_mean_distance=0.
  worst_angle=worst_distance=0.
  for index,(route_meta) in enumerate(recorded["routes"]):
   route=(route_meta["from_clip"],route_meta["to_clip"])
   require(route==reference.TRANSITIONS[index],
           "source-bound transition route changed")
   for pose in route_meta["samples"]:
    translation,rotation=phase_reference(original,geometry,route,pose)
    radians,meters=source_pose_delta(translation,rotation,pose["joints"])
    worst_a=int(np.argmax(radians));worst_d=int(np.argmax(meters))
    deviation={
      "from_clip":route[0],"to_clip":route[1],
      "alpha":pose["alpha"],
      "max_quaternion_angle_rad":float(radians[worst_a]),
      "max_quaternion_joint":worst_a,
      "max_translation_m":float(meters[worst_d]),
      "max_translation_joint":worst_d,
      "mean_quaternion_angle_rad":float(np.mean(radians)),
      "mean_translation_m":float(np.mean(meters)),
      "tail_root_joint34_angle_rad":float(radians[34]),
      "tail_root_joint34_translation_m":float(meters[34]),
      "joint_angle_mismatch_count":int(np.count_nonzero(radians>MAX_ANGLE_RAD)),
      "joint_translation_mismatch_count":int(np.count_nonzero(meters>MAX_TRANSLATION_M)),
      "approximation_tolerance_matched":bool(
        np.max(radians)<=MAX_ANGLE_RAD and
        np.max(meters)<=MAX_TRANSLATION_M),
    }
    rows.append(deviation)
    worst_angle=max(worst_angle,deviation["max_quaternion_angle_rad"])
    worst_distance=max(worst_distance,deviation["max_translation_m"])
    total_mean_angle+=deviation["mean_quaternion_angle_rad"]
    total_mean_distance+=deviation["mean_translation_m"]
  require(len(rows)==SAMPLES,"incomplete source-versus-actual Three comparison")
  return {
    "schema":SCHEMA,
    "stage":stage,
    "source_model_sha256":pin,
    "source_model_bytes":length,
    "actual_three_trace_sha256":sha(trace),
    "real_mixer_version":"186",
    "source_approximation":"original glTF linear/slerp at ACTUAL Three source action playheads",
    "sampled_pose_count":len(rows),
    "joint_count":REVIEWED_JOINTS,
    "angle_limit_radians":MAX_ANGLE_RAD,
    "position_limit_m":MAX_TRANSLATION_M,
    "worst_angle_radians":worst_angle,
    "worst_position_error_m":worst_distance,
    "mean_pose_angle_radians":total_mean_angle/len(rows),
    "mean_pose_translation_error_m":total_mean_distance/len(rows),
    "samples_outside_approximation_tolerance":sum(not x["approximation_tolerance_matched"] for x in rows),
    "original_three_vs_approximation_matched_all_sampled_joints":
      all(x["approximation_tolerance_matched"] for x in rows),
    "real_three_original_trace_reexecuted_by_this_comparator":False,
    "geometry_collision_qualified":False,
    "all_anatomical_pairs_qualified":False,
    "arbitrary_browser_playheads_qualified":False,
    "continuous_collision_qualified":False,
    "physical_rtx_verified":False,
    "artist_approved":False,
    "release_qualified":False,
    "samples":rows,
  }
 finally:
  try:original.close()
  except BufferError:pass

def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument("--stage",required=True,choices=verified.PINS)
 p.add_argument("--model",type=Path,required=True)
 p.add_argument("--trace",type=Path,required=True)
 p.add_argument("--source-tools",type=Path,required=True)
 p.add_argument("--output",type=Path,required=True)
 a=p.parse_args()
 require(a.output.parent.is_dir() and not a.output.parent.is_symlink()
         and not os.path.lexists(a.output),"trusted unused parity report path required")
 result=analyze(a.stage,a.model,a.trace,a.source_tools)
 with a.output.open("x",encoding="utf-8") as target:
  json.dump(result,target,indent=2,allow_nan=False)
  target.write("\n");target.flush();os.fsync(target.fileno())
 print(json.dumps({k:v for k,v in result.items() if k!="samples"},indent=2))
 if result["samples_outside_approximation_tolerance"]:
  raise SystemExit(2)
if __name__=="__main__":main()
