"""Verify source-bound actual Three.js 0.186 original V7 joint traces.

When given only JSON this is a consistency check. With --model it ALSO
verifies original model byte custody, but only a genuine Three.js replay
proves actual mixer scheduling. No skinned-triangle clearance is inferred.
"""
from __future__ import annotations
import argparse,hashlib,json,math
from pathlib import Path

PINS={
 "pathfinder":(114696520,"27e1a6a22fad045d26edf4dc2813292829aab8dcaa129fac407f80ee83229ade"),
 "archivist":(114819168,"f224671cf6d0886365f081faa29f9dcf2509d52211677d2a83152a389389acaf"),
}
DONOR="c9807afdffd61640cb2d8e1ed6d17250d4a9613965269f0e0bf12c0c979a9a6a"
TRANSITIONS=(
 ("ground-idle-1","takeoff-1"),
 ("takeoff-1","orbit-01"),
 ("orbit-01","landing-1"),
 ("landing-1","ground-idle-1"),
 ("orbit-01","orbit-02"),
 ("orbit-02","landing-1"),
)
MAX_REPORT_BYTES=32*1024**2
MAX_ABS_MATRIX=1e7

def require(x,why):
 if not x:raise ValueError(why)

def sha(path):
 with Path(path).open("rb") as f:
  return hashlib.file_digest(f,"sha256").hexdigest()

def bounded(value,n,where):
 require(isinstance(value,list) and len(value)==n and
         all(type(x) in (int,float) and math.isfinite(x) and
             abs(x)<MAX_ABS_MATRIX for x in value),
         "nonfinite, oversized or missing Three joint "+where)
 return value

def verify(report,stage,model=None):
 require(stage in PINS,"unsupported source stage")
 expected_size,expected_sha=PINS[stage]
 require(report.get("schema")=="skeleton.emerald.v7.actual-three-mixer-joints.v1"
         and report.get("stage")==stage
         and report.get("model_bytes")==expected_size
         and report.get("model_sha256")==expected_sha
         and report.get("donor_sha256")==DONOR
         and report.get("three_revision")=="186"
         and report.get("mixer")=="THREE.AnimationMixer and AnimationAction.crossFadeFrom (warp=false)"
         and report.get("source_stage_fade_seconds")==.22
         and report.get("skin_joints")==108,
         "source donor, Three library or mixer policy differs")
 steps=report.get("samples_per_route")
 require(type(steps) is int and steps>=3 and steps<=33 and steps%2==1
         and report.get("total_sampled_poses")==steps*len(TRANSITIONS),
         "missing original Three sampled phases")
 require(all(report.get(flag) is False for flag in (
    "geometry_collision_scanned","physical_webgl_tested",
    "real_browser_playheads_qualified","continuous_collision_qualified",
    "all_anatomical_pairs_qualified","artist_approved",
    "physical_rtx_verified","release_qualified")),
    "joint trace falsely claims collision clearance, physical GPU or release")
 routes=report.get("routes")
 require(isinstance(routes,list) and len(routes)==len(TRANSITIONS),
         "missing original transition directions")
 pose_count=0
 min_weight=float("inf");max_weight=-float("inf")
 for ridx,route in enumerate(routes):
  outgoing,incoming=TRANSITIONS[ridx]
  require(route.get("from_clip")==outgoing and route.get("to_clip")==incoming,
          "wrong route ordering or source animation names")
  d0=route.get("outgoing_duration_s")
  d1=route.get("incoming_duration_s")
  require(all(type(x) in (float,int) and math.isfinite(x) and x>=.22
              for x in (d0,d1)),
          "invalid real Three motion duration")
  samples=route.get("samples")
  require(isinstance(samples,list) and len(samples)==steps,
          "incomplete actual mixer trace")
  for index,sample in enumerate(samples):
   alpha=index/(steps-1)
   require(sample.get("from_clip")==outgoing and
           sample.get("to_clip")==incoming and
           type(sample.get("alpha")) in (float,int) and
           abs(sample["alpha"]-alpha)<1e-12,
           "duplicated, swapped or fabricated actual mixer phase")
   for key in ("source_old_time_s","source_new_time_s"):
    t=sample.get(key)
    require(type(t) in (int,float) and math.isfinite(t) and t>=0 and
            t<=max(d0,d1)+.23,
            "untrusted original Three animation playhead")
   a=sample.get("outgoing_weight")
   b=sample.get("incoming_weight")
   require(all(type(x) in (int,float) and math.isfinite(x) and
               -1e-6<=x<=1+1e-6 for x in (a,b)),
           "invalid Three mixer action weight")
   min_weight=min(min_weight,a,b);max_weight=max(max_weight,a,b)
   require(abs(a+b-1)<5e-3,
           "original Three mixer crossfade weights not complementary")
   if index==0:require(a>=1-5e-3 and b<=5e-3,
                       "outgoing clip not active at start of source fade")
   if index==steps-1:require(a<=5e-3 and b>=1-5e-3,
                            "incoming clip not active at end of source fade")
   joints=sample.get("joints")
   require(isinstance(joints,list) and len(joints)==108,
           "missing actual full 108-joint Three sampled pose")
   for j,node in enumerate(joints):
    require(node.get("joint")==j,
            "reordered or missing original mixer joint")
    t=bounded(node.get("local_translation"),3,"translation")
    q=bounded(node.get("local_quaternion"),4,"quaternion")
    m=bounded(node.get("world_matrix"),16,"matrix")
    require(abs(math.sqrt(sum(x*x for x in q))-1)<3e-4,
            "unnormalized real Three bone quaternion")
    require(all(abs(m[i])<2e-5 for i in (3,7,11))
            and abs(m[15]-1)<2e-5,
            "invalid Three world matrix last row")
   pose_count+=1
 require(pose_count==steps*6,
         "unqualified or incomplete Three mixer sample inventory")
 source_rechecked=False
 if model is not None:
  path=Path(model)
  require(path.is_file() and not path.is_symlink() and
          (path.stat().st_size,sha(path))==(expected_size,expected_sha),
          "independent exact V7 model SHA recheck failed")
  source_rechecked=True
 return {
   "schema":"skeleton.emerald.v7.actual-three-joint-consistency.v1",
   "original_model_sha256":expected_sha,
   "source_stage":stage,"three_revision":"186",
   "sampled_poses":pose_count,
   "joints_per_pose":108,
   "max_effective_weight":max_weight,"min_effective_weight":min_weight,
   "full_model_sha_independently_rechecked":source_rechecked,
   "original_mixer_reexecuted_by_this_validator":False,
   "source_geometry_contacts_checked":False,
   "actual_webgl_device_verified":False,
   "continuous_collision_qualified":False,
   "artist_approved":False,"physical_rtx_verified":False,
   "release_qualified":False,
 }

def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument("--trace",required=True,type=Path)
 p.add_argument("--stage",required=True,choices=PINS)
 p.add_argument("--model",type=Path)
 a=p.parse_args()
 require(a.trace.is_file() and not a.trace.is_symlink() and
         a.trace.stat().st_size<=MAX_REPORT_BYTES,
         "missing or oversized source Three trace")
 trace=json.loads(a.trace.read_bytes())
 print(json.dumps(verify(trace,a.stage,a.model),indent=2,allow_nan=False))
if __name__=="__main__":main()
