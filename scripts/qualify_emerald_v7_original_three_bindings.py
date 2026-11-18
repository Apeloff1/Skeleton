"""Fail-closed original V7 glTF palette/animation census before running Three.

Reads only the JSON chunk plus a bounded streamed SHA-256 of each original
114–115 MB GLB. No vertex extraction, model replacement or runtime adoption.
"""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import stat
import struct

from emerald_v7_model_pins import SOURCES,OUTPUTS,DONOR,ROOT_JOINT,require

ROOT=Path(__file__).resolve().parents[1]
MANIFEST=ROOT/"assets/emerald/evolution-v7/original-three-binding-census.json"
SCHEMA="skeleton.emerald.v7.original-real-three-binding-census.v1"
STAGES=("pathfinder","archivist")
CLIPS=("ground-idle-1","takeoff-1","orbit-01","orbit-02","landing-1")
MAX_JSON=32*1024**2
MAX_MANIFEST=64*1024
EXACT_PALETTE_SHA="75cb827128980e9253aea694efcb74636429ebc98310ab1c416f6ed378d8d647"

def canonical(value):
 return json.dumps(value,separators=(",",":"),ensure_ascii=False).encode("utf-8")

def sha(value):
 return hashlib.sha256(value).hexdigest()

def manifest(path=MANIFEST):
 path=Path(path)
 require(path.is_file() and not path.is_symlink() and
         0<path.stat().st_size<=MAX_MANIFEST,
         "missing or untrusted original V7 binding census")
 value=json.loads(path.read_bytes())
 require(value.get("schema")==SCHEMA and
         value.get("donor_sha256")==DONOR and
         value.get("three_package_version")=="0.186.1" and
         value.get("node_count")==109 and
         value.get("skin_joint_count")==108 and
         value.get("mesh_node_index")==92 and
         value.get("corrective_last_joint_node_index")==108 and
         value.get("skin_palette_json_sha256")==EXACT_PALETTE_SHA and
         [x.get("name") for x in value.get("clips",[])]==list(CLIPS) and
         [x.get("stage") for x in value.get("models",[])]==list(STAGES),
         "original source model/clip identity missing or altered")
 for row in value["models"]:
  expected_bytes,pinned_sha=OUTPUTS[row["stage"]]
  require((row.get("model_bytes"),row.get("model_sha256"))==
          (expected_bytes,pinned_sha)
          and row.get("clip_catalogue_count")==381
          and row.get("skin_palette_exact") is True,
          "wrong original V7 model pin or original motion catalogue")
 for key in ("joint_or_clip_retarget_approved","simulated_source_mixer_qualified",
             "real_mixer_original_run_completed","full_continuous_collision_qualified",
             "remote_original_git_published","artist_approved",
             "physical_rtx_verified","release_qualified"):
  require(value.get(key) is False,
          "source model census falsely elevated to renderer/device/release approval")
 return value

def describe(document,stage):
 require(stage in STAGES and document.get("asset",{}).get("version")=="2.0"
         and document.get("extras",{}).get("donorSha256")==DONOR
         and document["extras"].get("stage")==stage,
         "wrong source V7 stage or donor glTF identity")
 nodes=document.get("nodes")
 skins=document.get("skins")
 animations=document.get("animations")
 require(isinstance(nodes,list) and len(nodes)==109 and
         isinstance(skins,list) and len(skins)==1 and
         isinstance(animations,list) and len(animations)==381,
         "wrong source V7 node, original skin or clip count")
 palette=skins[0].get("joints")
 require(isinstance(palette,list) and len(palette)==108 and
         all(type(n) is int and 0<=n<len(nodes) for n in palette) and
         len(set(palette))==108 and
         92 not in palette and 108 in palette and
         palette[ROOT_JOINT]==34 and
         nodes[92].get("mesh")==0 and nodes[92].get("skin")==0,
         "original skin palette, mesh omission or tail root changed")
 palette_sha=sha(canonical(palette))
 require(palette_sha==EXACT_PALETTE_SHA,
         "source original skin palette order changed")
 existing=[a.get("name") for a in animations]
 require(len(set(existing))==381,
         "duplicate or missing original motion clip")
 clips=[]
 for name in CLIPS:
  animation=next((a for a in animations if a.get("name")==name),None)
  require(animation is not None,"original mixer clip missing")
  samplers=animation.get("samplers")
  channels=animation.get("channels")
  require(isinstance(samplers,list) and isinstance(channels,list) and
          len(samplers)==len(channels) and 0<len(channels)<=256,
          "source original clip channel/sampler census changed")
  targets=[]
  durations=[]
  for channel in channels:
   target=channel.get("target",{})
   node=target.get("node")
   channel_path=target.get("path")
   idx=channel.get("sampler")
   require(type(node) is int and node in palette and
           channel_path in ("translation","rotation") and
           type(idx) is int and 0<=idx<len(samplers) and
           samplers[idx].get("interpolation")=="LINEAR",
           "source original glTF channel incorrectly targets a mesh or interpolation")
   sampler=samplers[idx]
   accessor_id=sampler.get("input")
   accessors=document.get("accessors",[])
   require(type(accessor_id) is int and 0<=accessor_id<len(accessors),
           "source animation time accessor missing")
   source=accessors[accessor_id]
   require(source.get("type")=="SCALAR"
           and source.get("componentType")==5126
           and isinstance(source.get("max"),list) and len(source["max"])==1
           and isinstance(source.get("min"),list) and len(source["min"])==1
           and source["min"][0]==0 and
           type(source["max"][0]) in (int,float) and
           source["max"][0]>.22 and source["max"][0]<240,
           "original source motion timebase changed")
   durations.append(source["max"][0])
   targets.append([node,channel_path])
  require(len(targets)==len(set((x[0],x[1]) for x in targets))
          and len(set(durations))==1,
          "duplicate source joint property or differing source clip duration")
  counts=Counter(x[1] for x in targets)
  clips.append({
   "name":name,"channels":len(channels),
   "rotation":counts.get("rotation",0),
   "translation":counts.get("translation",0),
   "duration_seconds":durations[0],
   "targets_sha256":sha(canonical(targets)),
  })
 return {"stage":stage,
         "node_count":len(nodes),
         "skin_joint_count":len(palette),
         "mesh_node_index":92,
         "last_corrective_joint_node_index":palette[-1],
         "skin_palette_json_sha256":palette_sha,
         "clips":clips}

def compare_descriptor(descriptor,source_manifest):
 require(descriptor.get("stage") in STAGES,"source stage not recognized")
 require(descriptor.get("node_count")==109
         and descriptor.get("skin_joint_count")==108
         and descriptor.get("mesh_node_index")==92
         and descriptor.get("last_corrective_joint_node_index")==108
         and descriptor.get("skin_palette_json_sha256")==EXACT_PALETTE_SHA,
         "original source Three skin palette differs")
 for i,expected in enumerate(source_manifest["clips"]):
  row=descriptor.get("clips",[])
  require(len(row)==5 and row[i]==expected,
          "source original clip target SHA, duration or track census differs")
 return {"stage":descriptor["stage"],
         "original_skin_joint_count":108,
         "original_glTF_node_count":109,
         "actual_mixer_clip_bindings_exact":True,
         "source_original_model_rechecked":False,
         "continuous_collision_qualified":False,
         "release_qualified":False}

def inspect_model(path,stage,source_manifest=None):
 path=Path(path)
 expected_size,expected_sha=OUTPUTS[stage]
 require(path.is_file() and not path.is_symlink()
         and path.stat().st_size==expected_size,
         "missing or wrong-length V7 original donor GLB")
 file_flags=os.O_RDONLY|getattr(os,"O_NOFOLLOW",0)|getattr(os,"O_BINARY",0)
 with os.fdopen(os.open(path,file_flags),"rb") as reader:
  before=os.fstat(reader.fileno())
  require(stat.S_ISREG(before.st_mode) and before.st_size==expected_size,
          "original source model changed on open")
  header=reader.read(20)
  require(len(header)==20,"truncated source GLB header")
  magic,version,total,jsonlen,tag=struct.unpack("<4sIIII",header)
  require((magic,version,total,tag)==(b"glTF",2,expected_size,0x4e4f534a)
          and jsonlen>=4 and jsonlen<=MAX_JSON and jsonlen%4==0,
          "source original GLB JSON chunk invalid")
  document=json.loads(reader.read(jsonlen))
  descriptor=describe(document,stage)
  binary_header=reader.read(8)
  require(len(binary_header)==8 and
          struct.unpack_from("<I",binary_header,4)[0]==0x004e4942
          and struct.unpack_from("<I",binary_header,0)[0]+28+jsonlen==expected_size,
          "source original GLB binary extent differs")
  reader.seek(0)
  complete=hashlib.file_digest(reader,"sha256").hexdigest()
  after=os.fstat(reader.fileno())
  identity=lambda s:(s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
  require(complete==expected_sha and identity(before)==identity(after),
          "original V7 source SHA-256 or inode identity changed")
 result=compare_descriptor(descriptor,
                           manifest() if source_manifest is None else source_manifest)
 result["source_original_model_rechecked"]=True
 result["source_original_model_sha256"]=complete
 result["source_original_model_bytes"]=expected_size
 result["physical_webgl_verified"]=False
 result["artist_approved"]=False
 result["physical_rtx_verified"]=False
 return result

def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument("--models",required=True,type=Path)
 p.add_argument("--stage",choices=STAGES,action="append")
 a=p.parse_args()
 source=manifest()
 stages=a.stage or STAGES
 results=[inspect_model(a.models/(stage+".glb"),stage,source)
          for stage in stages]
 print(json.dumps({"schema":"skeleton.emerald.v7.bindings-preflight-result.v1",
                   "results":results,"release_qualified":False},indent=2))

if __name__=="__main__":main()
