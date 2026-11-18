"""Independent stdlib audit of exact V7 109-node / 108-joint donor scene.

Usage without --archives validates the checked-in evidence ledger only. Using
--archives requires both original full ZIPs and recomputes ZIP/GLB SHA-256,
scene bindings, all selected motion clip censuses and orbit02 tail accessor.
No browser/Three execution, CCD, GPU, artistic or release claim is implied.
"""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import struct
import zipfile

from emerald_v7_model_pins import OUTPUTS, DONOR

ROOT=Path(__file__).resolve().parents[1]
RECEIPT=ROOT/"assets/emerald/evolution-v7/original-skin-palette-rechecked-20261118.json"
SCHEMA="skeleton.emerald.v7.original-scene-census.v1"
STAGES=("pathfinder","archivist")
SCENE_ROOT=0
MESH_NODE=92
MESH_NAME="Emerald continuous reconstructed character"
SKIN_PALETTE=tuple(list(range(92))+list(range(93,109)))
TRACKS={
 "ground-idle-1":{"rotation":97,"translation":17},
 "takeoff-1":{"rotation":106,"translation":18},
 "orbit-01":{"rotation":71,"translation":17},
 "orbit-02":{"rotation":71,"translation":17},
 "landing-1":{"rotation":105,"translation":18},
}
ZIP_PINS={
 "pathfinder":(114705092,"1149a6991004954735a1aeab633aa604d7453cee5856349fc24d1ad8b614ec30"),
 "archivist":(114827704,"ae76924a439bc78368640680563e42ff3903fb2ae16c394347cc1cd697ffd1d6"),
}
MAX_JSON=32*1024**2
MAX_MEMBERS=64
MAX_UNCOMPRESSED=512*1024**2

def require(ok,why):
 if not ok:raise ValueError(why)

def sha256(path):
 with Path(path).open("rb") as stream:
  return hashlib.file_digest(stream,"sha256").hexdigest()

def census(document,stage):
 """Pure original glTF structural audit; accepts no physical-risk assertions."""
 require(stage in STAGES and
         isinstance(document,dict) and document.get("asset",{}).get("version")=="2.0",
         "wrong original glTF asset")
 nodes=document.get("nodes");skins=document.get("skins")
 scene=document.get("scenes");mesh=document.get("meshes")
 require(isinstance(nodes,list) and len(nodes)==109 and
         isinstance(skins,list) and len(skins)==1 and
         isinstance(scene,list) and len(scene)==1 and
         document.get("scene")==0 and scene[0].get("nodes")==[0,92] and
         isinstance(mesh,list) and len(mesh)==1,
         "wrong original 109-node, scene-root or skinned mesh count")
 skin=skins[0]
 palette=skin.get("joints")
 require(palette==list(SKIN_PALETTE) and
         skin.get("skeleton")==0 and skin.get("inverseBindMatrices")==0,
         "wrong original noncontiguous 108-joint skin palette")
 require(nodes[0].get("name")=="root" and
         nodes[0].get("children")==[1] and
         nodes[MESH_NODE]=={"name":MESH_NAME,"mesh":0,"skin":0} and
         all("mesh" not in nodes[i] and "matrix" not in nodes[i] for i in SKIN_PALETTE),
         "wrong original root or detached mesh node 92")
 require(all("scale" not in nodes[i] for i in SKIN_PALETTE),
         "unexpected original joint scaling changes skin transforms")
 extras=document.get("extras",{})
 correction=extras.get("orbit02ClearanceCorrection",{})
 require(extras.get("stage")==stage and extras.get("donorSha256")==DONOR and
         correction.get("schema")=="skeleton.emerald.orbit02-tail-clearance.v1"
         and correction.get("joint_index")==34
         and correction.get("clip")=="orbit-02"
         and correction.get("local_y_radians")==.18
         and correction.get("modified_keyframes")==160
         and all(correction.get(key) is False for key in (
             "continuous_collision_qualified","real_mixer_qualified",
             "artist_approved","physical_rtx_verified","release_qualified")),
         "wrong original donor correction or false acceptance")
 animations=document.get("animations")
 require(isinstance(animations,list) and len(animations)==381 and
         animations[-1].get("name")=="growth-"+stage+"-to-"+(
             "archivist" if stage=="pathfinder" else "hoarder"),
         "wrong original 381-clip library or next-form transition")
 by_name={a.get("name"):a for a in animations}
 require(len(by_name)==381 and set(TRACKS).issubset(by_name),
         "missing or duplicated original flight clips")
 counts={}
 for name,expected in TRACKS.items():
  clip=by_name[name]
  channels=clip.get("channels");samplers=clip.get("samplers")
  require(isinstance(channels,list) and isinstance(samplers,list)
          and len(channels)==len(samplers)==sum(expected.values()),
          "altered original stage-specific animation track count")
  tally=Counter();seen=set()
  for channel in channels:
   target=channel.get("target",{})
   node=target.get("node");prop=target.get("path")
   sampler_id=channel.get("sampler")
   require(node in SKIN_PALETTE and prop in ("rotation","translation") and
           type(sampler_id) is int and 0<=sampler_id<len(samplers),
           "non-skin animation channel, mesh override or bad sampler")
   require((node,prop) not in seen,
           "duplicate original joint/property animation channel")
   seen.add((node,prop));tally[prop]+=1
   require(samplers[sampler_id].get("interpolation")=="LINEAR",
           "unreviewed original quaternion interpolation")
  require(dict(tally)==expected,
          "rotation/translation channel census differs from original donor")
  counts[name]=dict(tally)
 target=[channel for channel in by_name["orbit-02"]["channels"]
         if channel["target"]=={"node":SKIN_PALETTE[34],"path":"rotation"}]
 require(len(target)==1,"missing reviewed orbit02 tail-root animation")
 sampler=by_name["orbit-02"]["samplers"][target[0]["sampler"]]
 accessors=document.get("accessors",[])
 out=sampler.get("output")
 require(type(out) is int and 0<=out<len(accessors) and
         all(accessors[out].get(k)==v for k,v in {
          "componentType":5126,"type":"VEC4","count":160}.items()) and
         "sparse" not in accessors[out],
         "wrong original 160-key corrected tail quaternion accessor")
 return {
  "stage":stage,"node_count":109,"skin_joint_count":108,
  "scene_nodes":[0,92],"mesh_node_index":MESH_NODE,
  "mesh_node_name":MESH_NAME,"root_joint_name":"root",
  "joint_palette_after_mesh":list(SKIN_PALETTE[88:96]),
  "explicit_joint_scale_nodes":0,
  "animation_clip_count":381,
  "motion_track_census":counts,
  "orbit02_tail_joint":34,"orbit02_corrected_rotation_keys":160,
  "artist_approved":False,"real_three_mixer_qualified":False,
  "continuous_collision_qualified":False,
  "physical_rtx_verified":False,"release_qualified":False,
 }

def exact_archive(folder,stage):
 require(stage in STAGES,"unknown original V7 stage")
 archive=Path(folder)/(stage+"-v7-orbit02-clearance.zip")
 zipbytes,zipsha=ZIP_PINS[stage]
 modelbytes,modelsha=OUTPUTS[stage]
 require(archive.is_file() and not archive.is_symlink() and
         (archive.stat().st_size,sha256(archive))==(zipbytes,zipsha),
         "source original V7 archive SHA or byte length differs")
 with zipfile.ZipFile(archive) as z:
  info=z.infolist()
  require(len(info)<=MAX_MEMBERS and
          sum(member.file_size for member in info)<=MAX_UNCOMPRESSED,
          "unsafe original ZIP member quota")
  seen=set()
  for member in info:
   name=member.filename
   require(not member.is_dir() and not member.flag_bits&1 and
           not name.startswith("/") and "\\" not in name and
           all(part not in ("",".","..") for part in name.split("/")) and
           name.casefold() not in seen and
           ((member.external_attr>>16)&0o170000)!=0o120000,
           "unsafe linked, duplicate, encrypted or traversal ZIP member")
   seen.add(name.casefold())
  member=z.getinfo(stage+".glb")
  require(member.file_size==modelbytes,"wrong source embedded GLB byte length")
  with z.open(member) as stream:
   header=stream.read(20)
   require(len(header)==20,"truncated source GLB header")
   magic,version,total,jsonbytes,tag=struct.unpack("<4sIIII",header)
   require((magic,version,total,tag)==(b"glTF",2,modelbytes,0x4e4f534a)
           and 0<jsonbytes<=MAX_JSON and jsonbytes%4==0,
           "unreviewed original glTF chunk header")
   data=stream.read(jsonbytes)
   require(len(data)==jsonbytes,"source original GLB JSON truncated")
   model_doc=json.loads(data)
   binheader=stream.read(8)
   require(len(binheader)==8,"original GLB binary chunk missing")
   binsize,bintag=struct.unpack("<II",binheader)
   require(bintag==0x004e4942 and 28+jsonbytes+binsize==total,
           "wrong complete original BIN length")
   original_hash=hashlib.sha256()
   original_hash.update(header);original_hash.update(data)
   original_hash.update(binheader)
   done=28+jsonbytes
   while chunk:=stream.read(4*1024**2):
    done+=len(chunk);original_hash.update(chunk)
    require(done<=modelbytes,"unbounded original model source length")
   require(done==modelbytes and original_hash.hexdigest()==modelsha,
           "complete original V7 source SHA mismatch")
  record=census(model_doc,stage)
  record.update({
   "zip_sha256":zipsha,"zip_bytes":zipbytes,
   "glb_sha256":modelsha,"glb_bytes":modelbytes,
  })
  return record

def check_record(record):
 require(record.get("schema")==SCHEMA and
         record.get("donor_sha256")==DONOR and
         record.get("original_zip_and_glb_bytes_verified_offline") is True and
         record.get("source_only_ci_replays_original_bytes") is False,
         "wrong V7 original scene evidence or CI approval policy")
 forms=record.get("forms")
 require(isinstance(forms,list) and
         [x.get("stage") for x in forms]==list(STAGES),
         "missing or duplicated exact original V7 model")
 for f in forms:
  stage=f["stage"]
  zipbytes,zipsha=ZIP_PINS[stage]
  modelbytes,modelsha=OUTPUTS[stage]
  require((f.get("zip_bytes"),f.get("zip_sha256"),
           f.get("glb_bytes"),f.get("glb_sha256"))==
          (zipbytes,zipsha,modelbytes,modelsha),
          "original ZIP/GLB source digest altered")
  expected_counts=TRACKS
  require(f.get("node_count")==109 and f.get("skin_joint_count")==108 and
          f.get("scene_nodes")==[0,92] and f.get("mesh_node_index")==92 and
          f.get("mesh_node_name")==MESH_NAME and f.get("root_joint_name")=="root" and
          f.get("joint_palette_after_mesh")==list(SKIN_PALETTE[88:96]) and
          f.get("explicit_joint_scale_nodes")==0 and
          f.get("animation_clip_count")==381 and
          f.get("motion_track_census")==expected_counts and
          f.get("orbit02_tail_joint")==34 and
          f.get("orbit02_corrected_rotation_keys")==160 and
          all(f.get(k) is False for k in (
              "artist_approved","real_three_mixer_qualified",
              "continuous_collision_qualified","physical_rtx_verified",
              "release_qualified")),
          "source donor root, rig or motion census altered")
 require(all(record.get(k) is False for k in (
       "original_git_remote_published","live_browser_mixer_qualified",
       "continuous_collision_qualified","artistic_approved",
       "physical_rtx_verified","release_qualified")),
       "source record falsely claims Git publication or physical qualification")
 return {"schema":"skeleton.emerald.v7.scene-ledger-consistency.v1",
         "checked_in_original_model_pins":2,
         "recorded_source_scene_census_valid":True,
         "actual_zip_bytes_replayed_in_this_source_only_step":False,
         "real_three_mixer_qualified":False,
         "continuous_collision_qualified":False,
         "physical_rtx_verified":False,"release_qualified":False}

def main():
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument("--archives",type=Path)
 parser.add_argument("--receipt",type=Path,default=RECEIPT)
 args=parser.parse_args()
 require(args.receipt.is_file() and not args.receipt.is_symlink()
         and args.receipt.stat().st_size<=128*1024,
         "missing source-bound original scene receipt")
 record=json.loads(args.receipt.read_bytes())
 check=check_record(record)
 if args.archives is not None:
  actual=[exact_archive(args.archives,stage) for stage in STAGES]
  require(actual==record["forms"],
          "actual original ZIP/GLB donor census differs from review ledger")
  check["actual_zip_bytes_replayed_in_this_source_only_step"]=True
 print(json.dumps(check,indent=2,allow_nan=False))
if __name__=="__main__":main()
