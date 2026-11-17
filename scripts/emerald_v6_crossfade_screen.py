"""Qualify *sampled* live-mixer crossfades on original-donor V6 skinned triangles.

Offline operator-only test: source-pinned geometry tools, exact model SHA and a
0.22s two-action rotation/translation blend. Sampled poses and local joints are
only an approximation of the live Three.js mixer. Does not prove continuous
collision, actual device behavior, equipment clearance or art approval.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib
import json
import math
import mmap
import os
from pathlib import Path
import sys
import time

import numpy as np
from scipy.spatial.transform import Rotation

DONOR = "c9807afdffd61640cb2d8e1ed6d17250d4a9613965269f0e0bf12c0c979a9a6a"
MODELS = {
 "pathfinder":(114693124,"20d6a6a62b3ff232572e1b25d799f1461d4e343ce3b7d30a328faed8837c4063"),
 "archivist":(114815776,"8d72d43773a98444133ab628db552bddad06ea0f101cfe223897bf8ba0944973"),
}
TOOLS = {
 "contact_audit.py":"0333ec4e01f701554e6f62b443fc5b2283bb68e8a62aaf324760068cc7107d4f",
 "contact_geometry.py":"ab08763903de7d222881e69cd1f8dc14e0c2f67be8c0ff22a15164f55bb132f5",
 "contact_geometry_accel.py":"fd5bd4c28ff528e3be7e0500476c27e52f054a0ef9ff34fa9ec9294d4800e431",
 "fast_wing_witness.py":"e170a70ec2522ef4a162ef53c8d3aabcf2a3ce110dc7fbeadca8852480845187",
 "analyze_seams.py":"482391dd5a68ad36411a315aab7abcb0b70febbca3dc780fb217f6f4fd32dc1a",
}
REGIONS = (
 ("torso",0,8),("head",8,14),("forelegs",14,24),
 ("hindlegs",24,34),("tail",34,44),
 ("wing_primary_near",44,56),("wing_primary_far",56,67),
 ("wing_mounted_detail",67,68),("wing_flight_near",68,80),
 ("wing_flight_far",80,92),("rig_correctives",92,108),
)
PAIRS = (("wing_primary_far","torso"),
         ("wing_mounted_detail","torso"),("tail","hindlegs"))
TRANSITIONS = (
 ("ground-idle-1","takeoff-1"),
 ("takeoff-1","orbit-01"),
 ("orbit-01","landing-1"),
 ("landing-1","ground-idle-1"),
 ("orbit-01","orbit-02"),
 ("orbit-02","landing-1"),
)
CROSSFADE_SECONDS = .22
MARGIN = .008
MAX_CANDIDATES = 150000

def require(value,why):
 if not value:raise ValueError(why)

def sha(path):
 with Path(path).open("rb") as stream:
  return hashlib.file_digest(stream,"sha256").hexdigest()

def vetted_tools(folder):
 folder=Path(folder)
 require(folder.is_dir() and not folder.is_symlink(),"trusted source directory required")
 for name,digest in TOOLS.items():
  candidate=folder/name
  require(candidate.is_file() and not candidate.is_symlink() and
          sha(candidate)==digest,"reviewed contact implementation missing or changed: "+name)
 # Import only after verifying *every* transitive file; no user-overridden modules.
 sys.path.insert(0,str(folder))
 try:
  contact=importlib.import_module("contact_audit")
  seam=importlib.import_module("analyze_seams")
  require(contact.SHA_DONOR==DONOR and
          tuple(seam.PAIRS)==PAIRS and len(seam.REGIONS)==len(REGIONS),
          "wrong geometric review implementation")
  # A sys.modules cache entry from another path must never defeat SHA custody.
  for name in ("contact_audit","analyze_seams","fast_wing_witness",
               "contact_geometry","contact_geometry_accel"):
   module=sys.modules.get(name)
   require(module is not None and
           Path(module.__file__).resolve()==(folder/(name+".py")).resolve(),
           "imported source escapes the verified contact-tool directory")
  return contact,seam
 finally:
  sys.path.pop(0)

def slerp_rows(q0,q1,t):
 """Shortest-path normalized quaternion SLERP, including antipodal tracks."""
 require(isinstance(q0,np.ndarray) and isinstance(q1,np.ndarray)
         and q0.shape==q1.shape and q0.ndim==2 and q0.shape[1]==4
         and q0.shape[0]>0 and np.isfinite(q0).all() and np.isfinite(q1).all()
         and math.isfinite(t) and 0<=t<=1,"unsafe quaternion blend")
 require(np.max(abs(np.linalg.norm(q0,axis=1)-1))<2e-5 and
         np.max(abs(np.linalg.norm(q1,axis=1)-1))<2e-5,"unqualified non-unit input")
 left=q0.astype(np.float64)
 right=q1.astype(np.float64).copy()
 dot=np.sum(left*right,axis=1)
 sign=dot<0
 right[sign]*=-1
 dot=np.clip(abs(dot),0,1)
 angle=np.arccos(dot)
 sin=np.sin(angle)
 linear=sin<1e-6
 wa=np.empty(len(angle));wb=np.empty(len(angle))
 wa[linear]=1-t;wb[linear]=t
 wa[~linear]=np.sin((1-t)*angle[~linear])/sin[~linear]
 wb[~linear]=np.sin(t*angle[~linear])/sin[~linear]
 mixed=wa[:,None]*left+wb[:,None]*right
 mixed/=np.linalg.norm(mixed,axis=1)[:,None]
 require(np.isfinite(mixed).all(),"nonfinite blended quaternion")
 return mixed

def local_pose(model,g,name,seconds):
 """Sample only original, source-bound LINEAR/spherical animated joint tracks."""
 require(name in model.animations and name!=list(model.animations)[-1],"unknown or growth clip")
 document=model.doc
 nodes=g["joint_nodes"]
 t=np.array([document["nodes"][int(n)].get("translation",[0,0,0])
             for n in nodes],dtype=np.float64)
 q=np.array([document["nodes"][int(n)].get("rotation",[0,0,0,1])
             for n in nodes],dtype=np.float64)
 clip=model.animations[name]
 duration=max(float(model.accessor(s["input"])[-1,0])
              for s in clip["samplers"])
 require(math.isfinite(duration) and duration>0 and
         math.isfinite(seconds) and 0<=seconds<=duration+1e-8,
         "invalid clip time or duration")
 now=min(duration,seconds)
 touched=set()
 for channel in clip["channels"]:
  sampler=clip["samplers"][channel["sampler"]]
  require(sampler["interpolation"]=="LINEAR","unqualified animation interpolation")
  times=model.accessor(sampler["input"]).ravel()
  values=model.accessor(sampler["output"])
  require(len(times)==len(values) and len(times)>=2 and
          np.all(np.diff(times)>0) and np.isfinite(values).all(),
          "bad source animation keys")
  idx=int(np.clip(np.searchsorted(times,now)-1,0,len(times)-2))
  a=float((now-times[idx])/(times[idx+1]-times[idx]))
  a=max(0.,min(a,1.))
  node=g["node_lookup"][channel["target"]["node"]]
  prop=channel["target"]["path"]
  require(prop in ("rotation","translation") and
          (node,prop) not in touched,"unsupported or duplicate track")
  touched.add((node,prop))
  if prop=="translation":
   t[node]=values[idx]*(1-a)+values[idx+1]*a
  else:
   q[node]=slerp_rows(values[idx:idx+1],values[idx+1:idx+2],a)[0]
 require(np.isfinite(t).all() and np.isfinite(q).all(),"invalid original joint pose")
 return duration,t,q

def skin(g,t,q):
 """Source-compatible LBS; returns actual 365,997 posed world-space vertices."""
 require(t.shape==(108,3) and q.shape==(108,4) and
         np.isfinite(t).all() and np.isfinite(q).all(),"wrong mixed skin input")
 m=np.broadcast_to(np.eye(4),(108,4,4)).copy()
 m[:,:3,:3]=Rotation.from_quat(q).as_matrix()
 m[:,:3,3]=t
 for i in range(1,108):
  m[i]=m[g["parents"][i]] @ m[i]
 m[:,:3,3]-=np.einsum("nij,nj->ni",m[:,:3,:3],g["rest"])
 transform=m[g["joints"]]
 positions=g["positions"].astype(np.float64)
 result=np.einsum("nk,nkj->nj",g["weights"],
                  np.einsum("nkij,nj->nki",
                            transform[:,:,:3,:3],positions)
                  +transform[:,:,:3,3])
 require(result.shape==(365997,3) and np.isfinite(result).all(),
         "invalid deformed mesh")
 return result

def anatomy(g):
 weights,joints,faces=g["weights"],g["joints"],g["faces"]
 categories=np.full(108,-1,dtype=np.int16)
 for i,(_name,start,end) in enumerate(REGIONS):
  require(np.all(categories[start:end]==-1),"overlapping anatomical cohorts")
  categories[start:end]=i
 require(np.all(categories!=-1),"unclassified source joint")
 strongest=joints[np.arange(len(joints)),weights.argmax(axis=1)]
 votes=categories[strongest[faces]]
 group=np.where((votes[:,0]==votes[:,1])|(votes[:,0]==votes[:,2]),
                votes[:,0],np.where(votes[:,1]==votes[:,2],votes[:,1],-1))
 result={name:np.flatnonzero(group==i)
         for i,(name,_start,_end) in enumerate(REGIONS)}
 require(len(faces)==719312 and int((group==-1).sum())==84 and
         sum(map(len,result.values()))==719228,
         "exact original anatomical census changed")
 return result

def contact_check(positions,g,groups,auditor,seam,deadline):
 """Unambiguous contact = intersects but not same indexed bind-pose face pair."""
 contacts=welds=near=0
 breakdown=[]
 faces=g["faces"]
 bind=g["positions"].astype(np.float64)
 for a,b in PAIRS:
  require(time.monotonic()<deadline,"crossfade geometry budget expired")
  ta=faces[groups[a]];tb=faces[groups[b]]
  candidates,visits=auditor.broadphase_pairs(
      positions[ta].astype(np.float64),
      positions[tb].astype(np.float64),MARGIN,MAX_CANDIDATES)
  pairs=np.asarray(candidates,dtype=np.int32).reshape(-1,2)
  if len(pairs):
   dp,db=seam.distances_at_pose_and_bind(
      positions[ta].astype(np.float64),positions[tb].astype(np.float64),
      bind[ta],bind[tb],pairs)
   hits=dp<=1e-16
   near_count=int(((dp>1e-16)&(dp<=MARGIN*MARGIN)).sum())
   h=pairs[hits]
   shared=(ta[h[:,0],:,None]==tb[h[:,1],None,:]).any(axis=(1,2))
   fresh=(~shared)|(db[hits]>1e-16)
   fresh_count=int(fresh.sum())
   weld_count=len(h)-fresh_count
  else:
   fresh_count=weld_count=near_count=0
  contacts+=fresh_count;welds+=weld_count;near+=near_count
  breakdown.append({"pair":a+"__"+b,"candidate_pairs":len(candidates),
                    "new_independent_contact_pairs":fresh_count,
                    "shared_index_bind_seam_candidates":weld_count,
                    "within_8mm_not_contact":near_count,
                    "broadphase_visits":int(visits)})
 require(time.monotonic()<deadline,"crossfade contact budget expired")
 return {"new_independent_contact_pairs":contacts,
         "shared_index_bind_seam_candidates":welds,
         "within_8mm_not_contact":near,
         "pairs":breakdown}

def verify_journal(snapshot, stage, model_sha, steps):
    """Accept only an exact prefix of the known pose matrix; never certify it."""
    require(snapshot.get("schema") == "skeleton.emerald.v6.crossfade-checkpoint.v1"
            and snapshot.get("stage") == stage
            and snapshot.get("model_sha256") == model_sha
            and snapshot.get("steps_per_transition") == steps
            and snapshot.get("crossfade_seconds") == CROSSFADE_SECONDS
            and snapshot.get("margin_m") == MARGIN
            and snapshot.get("reviewed_tool_digests") == TOOLS
            and snapshot.get("completed") is False
            and snapshot.get("continuous_collision_qualified") is False
            and snapshot.get("release_qualified") is False,
            "wrong source, policy or falsely qualified checkpoint")
    rows = snapshot.get("samples")
    require(isinstance(rows, list) and len(rows) <= len(TRANSITIONS)*steps,
            "corrupt checkpoint length")
    for i, row in enumerate(rows):
        outgoing, incoming = TRANSITIONS[i//steps]
        require(row.get("from_clip") == outgoing and
                row.get("to_clip") == incoming and
                row.get("alpha") == (i % steps)/(steps-1) and
                isinstance(row.get("pairs"), list) and
                [p.get("pair") for p in row["pairs"]] ==
                [a+"__"+b for a,b in PAIRS] and
                type(row.get("new_independent_contact_pairs")) is int and
                row["new_independent_contact_pairs"] >= 0,
                "missing, duplicate or altered checkpoint sample")
    return rows


def store_journal(path, stage, model_sha, steps, rows):
    """Atomic progress receipt; always incomplete, even on the final sample."""
    path = Path(path)
    temp = path.parent / ("." + path.name + ".partial")
    require(not os.path.lexists(temp), "staging checkpoint already exists")
    value = {
        "schema": "skeleton.emerald.v6.crossfade-checkpoint.v1",
        "stage": stage, "model_sha256": model_sha,
        "steps_per_transition": steps,
        "crossfade_seconds": CROSSFADE_SECONDS, "margin_m": MARGIN,
        "reviewed_tool_digests": TOOLS, "completed": False,
        "remaining_sample_count": len(TRANSITIONS)*steps-len(rows),
        "continuous_collision_qualified": False,
        "release_qualified": False, "samples": rows,
    }
    try:
        with temp.open("x", encoding="utf-8") as stream:
            json.dump(value, stream, indent=2, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if temp.exists():
            temp.unlink()


def run(stage,model_path,tool_dir,steps=5,limit_seconds=600,journal=None,resume=False,pins=None):
 pins=MODELS if pins is None else pins
 require(stage in pins and 3<=steps<=17
         and isinstance(steps,int) and 60<=limit_seconds<=3600,
         "unsupported model, time or sample quota")
 source=Path(model_path)
 required_bytes,required_sha=pins[stage]
 auditor,seam=vetted_tools(tool_dir)
 require(source.is_file() and not source.is_symlink() and
         source.stat().st_size==required_bytes and
         sha(source)==required_sha,"V6 source pin mismatch")
 if journal is None:
  require(not resume,"resume requires a journal")
  saved=[]
 else:
  journal=Path(journal)
  require(journal.parent.is_dir() and not journal.parent.is_symlink()
          and journal.exists()==resume and not journal.is_symlink(),
          "trusted unused journal required, or exact existing journal for resume")
  saved=verify_journal(json.loads(journal.read_bytes()),stage,required_sha,steps) if resume else []
 start=time.monotonic();deadline=start+limit_seconds
 model=auditor.GLB(source,required_bytes,required_sha,stage)
 try:
  g=model.geometry();groups=anatomy(g)
  results=[]
  for transition_index,(preceding,following) in enumerate(TRANSITIONS):
   dur_old,_,_=local_pose(model,g,preceding,0.)
   dur_new,_,_=local_pose(model,g,following,0.)
   require(dur_old>=CROSSFADE_SECONDS and dur_new>=CROSSFADE_SECONDS,
           "actual clip shorter than original .22s crossfade")
   for index in range(steps):
    sample_index=transition_index*steps+index
    if sample_index<len(saved):
     results.append(saved[sample_index])
     continue
    require(time.monotonic()<deadline,"incomplete transition time budget")
    alpha=index/(steps-1)
    # Source-compatible fade: hold outgoing clip at its final .22s
    # and incoming at the first .22s; arbitrary loop phase stays untested.
    old_time=dur_old-CROSSFADE_SECONDS*(1-alpha)
    new_time=CROSSFADE_SECONDS*alpha
    _,ta,qa=local_pose(model,g,preceding,old_time)
    _,tb,qb=local_pose(model,g,following,new_time)
    mixed_t=ta*(1-alpha)+tb*alpha
    mixed_q=slerp_rows(qa,qb,alpha)
    posed=skin(g,mixed_t,mixed_q)
    detail=contact_check(posed,g,groups,auditor,seam,deadline)
    results.append({
        "from_clip":preceding,"to_clip":following,
        "alpha":alpha,"source_old_time_s":old_time,
        "source_new_time_s":new_time,
        **detail,
    })
    if journal is not None:
     store_journal(journal,stage,required_sha,steps,results)
  unresolved=sum(row["new_independent_contact_pairs"]>0 for row in results)
  return {
   "schema":"skeleton.emerald.v6.crossfade-mesh-screen.v1",
   "stage":stage,"model_bytes":required_bytes,"model_sha256":required_sha,
   "donor_sha256":DONOR,
   "reviewed_tool_digests":TOOLS,
   "simulation":"joint-wise local quaternion slerp and translation lerp; approximate, not actual Three mixer",
   "source_crossfade_seconds":CROSSFADE_SECONDS,
   "clip_transitions":[list(x) for x in TRANSITIONS],
   "steps_per_transition":steps,
   "total_sampled_blends":len(results),
   "observed_new_contact_instances":sum(x["new_independent_contact_pairs"] for x in results),
   "sampled_blends_with_new_contacts":unresolved,
   "all_transition_intervals_qualified":False,
   "tested_in_real_browser_mixer":False,
   "continuous_collision_qualified":False,
   "unexamined_rig_seams_qualified":False,
   "optional_equipment_enabled":False,
   "artist_approved":False,
   "physical_rtx_verified":False,
   "release_qualified":False,
   "samples":results,
  }
 finally:
  # NumPy accessor views may retain backing mmap; close is best effort.
  try:model.close()
  except BufferError:pass

def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument("--stage",required=True,choices=MODELS)
 p.add_argument("--model",required=True,type=Path)
 p.add_argument("--source-tools",required=True,type=Path)
 p.add_argument("--output",required=True,type=Path)
 p.add_argument("--steps",type=int,default=5)
 p.add_argument("--time-budget-seconds",type=float,default=600)
 p.add_argument("--checkpoint",type=Path)
 p.add_argument("--resume",action="store_true")
 a=p.parse_args()
 require(a.output.parent.is_dir() and not a.output.parent.is_symlink()
         and not os.path.lexists(a.output),"trusted new report path required")
 report=run(a.stage,a.model,a.source_tools,a.steps,a.time_budget_seconds,
            journal=a.checkpoint,resume=a.resume)
 with a.output.open("x",encoding="utf-8") as target:
  json.dump(report,target,indent=2,allow_nan=False)
  target.write("\n")
 print(json.dumps({k:v for k,v in report.items() if k!="samples"},indent=2))
 # Contacts are not hidden behind exit code zero.
 if report["observed_new_contact_instances"]>0:
  raise SystemExit(2)

if __name__=="__main__":
 main()
