"""Independent stdlib-only exact V6→V7 GLB/ZIP structural and rotation audit.

Compares the actual complete original files from separately pinned ZIPs.
No substituted LFS pointer, source mock, device qualification or release.
"""
from __future__ import annotations
import argparse,hashlib,json,math,mmap,os,struct,tempfile,zipfile
from pathlib import Path

DONOR="c9807afdffd61640cb2d8e1ed6d17250d4a9613965269f0e0bf12c0c979a9a6a"
JOINT=34
CLIP="orbit-02"
ANGLE=.18
STAGES=("pathfinder","archivist")
FILES={
 "pathfinder":{
  "v6":(114693124,"20d6a6a62b3ff232572e1b25d799f1461d4e343ce3b7d30a328faed8837c4063",114764553,"7fb92f1fe2b5e14c7fbae2a631a190ead4087f8f0888eb83dd2b2a505a7d0773"),
  "v7":(114696520,"27e1a6a22fad045d26edf4dc2813292829aab8dcaa129fac407f80ee83229ade",114705092,"1149a6991004954735a1aeab633aa604d7453cee5856349fc24d1ad8b614ec30"),
 },
 "archivist":{
  "v6":(114815776,"8d72d43773a98444133ab628db552bddad06ea0f101cfe223897bf8ba0944973",114887203,"9ae320e098860ada63b827c5f94478fe8daef0c499034ec3e926808d2ddebb1f"),
  "v7":(114819168,"f224671cf6d0886365f081faa29f9dcf2509d52211677d2a83152a389389acaf",114827704,"ae76924a439bc78368640680563e42ff3903fb2ae16c394347cc1cd697ffd1d6"),
 },
}
MEMBER_QUOTA=64
ZIP_DECLARED_QUOTA=512*1024**2

def require(value,why):
 if not value:raise ValueError(why)

def digest(path):
 with Path(path).open("rb") as src:return hashlib.file_digest(src,"sha256").hexdigest()

def archive_to_scratch(path,stage,generation,target):
 size,sha,zip_size,zip_sha=FILES[stage][generation]
 source=Path(path)
 require(source.is_file() and not source.is_symlink()
         and source.stat().st_size==zip_size and digest(source)==zip_sha,
         "original "+generation+" archive byte custody failed for "+stage)
 require(target.parent.is_dir() and not target.exists(),
         "fresh original model scratch file required")
 with zipfile.ZipFile(source) as z:
  members=z.infolist()
  require(len(members)<=MEMBER_QUOTA and
          sum(x.file_size for x in members)<=ZIP_DECLARED_QUOTA,
          "untrusted original archive quota")
  names=set()
  for item in members:
   path_name=item.filename
   require(not item.is_dir() and not item.flag_bits&1 and
           not path_name.startswith("/") and "\\" not in path_name and
           all(p not in ("",".","..") for p in path_name.split("/")) and
           path_name.casefold() not in names and
           ((item.external_attr>>16)&0o170000)!=0o120000,
           "untrusted original member entry")
   names.add(path_name.casefold())
  info=z.getinfo(stage+".glb")
  require(info.file_size==size,"original model size or member name differs")
  written=0;h=hashlib.sha256()
  try:
   with z.open(info) as stream,target.open("xb") as out:
    while block:=stream.read(4*1024**2):
     written+=len(block)
     require(written<=size,"original GLB exceeds pinned size")
     out.write(block);h.update(block)
    out.flush();os.fsync(out.fileno())
   require(written==size and h.hexdigest()==sha,
           "complete original embedded model digest mismatch")
  except BaseException:
   if target.exists():target.unlink()
   raise
 return {"bytes":size,"sha256":sha,"zip_bytes":zip_size,"zip_sha256":zip_sha}

def glb(raw):
 require(len(raw)>=32,"truncated original model")
 magic,version,total,jsonlen,tag=struct.unpack_from("<4sIIII",raw)
 require((magic,version,total,tag)==(b"glTF",2,len(raw),0x4e4f534a)
         and 0<jsonlen<=32*1024**2 and jsonlen%4==0,
         "untrusted original model header")
 binlen,btag=struct.unpack_from("<II",raw,20+jsonlen)
 offset=28+jsonlen
 require(btag==0x004e4942 and offset+binlen==total,
         "incorrect original GLB BIN extent")
 doc=json.loads(raw[20:20+jsonlen])
 require(len(doc.get("buffers",[]))==1
         and "uri" not in doc["buffers"][0]
         and doc["buffers"][0]["byteLength"]<=binlen,
         "external or untrusted original model")
 return doc,offset,binlen

def read_rotations(raw,doc,base,index):
 acc=doc["accessors"][index]
 view=doc["bufferViews"][acc["bufferView"]]
 require(acc["type"]=="VEC4" and acc["componentType"]==5126
         and acc["count"]==160 and "sparse" not in acc
         and "byteStride" not in view,
         "unreviewed tail rotation accessor")
 local=acc.get("byteOffset",0);offset=view.get("byteOffset",0)+local
 require(local>=0 and local+2560<=view["byteLength"]
         and offset+2560<=doc["buffers"][0]["byteLength"],
         "tail quaternion track out of bounds")
 return [struct.unpack_from("<4f",raw,base+offset+16*i) for i in range(160)]

def correction_error(before,after):
 require(len(before)==len(after)==160,"expected exactly 160 original tail rotations")
 s=math.sin(ANGLE/2);c=math.cos(ANGLE/2)
 worst=0.
 for src,dst in zip(before,after):
  require(all(math.isfinite(x) for x in (*src,*dst)),
          "nonfinite original quaternion")
  require(abs(sum(x*x for x in src)-1)<4e-5,
          "unqualified nonunit source quaternion")
  x,y,z,w=src
  expected=(c*x-s*z,c*y+s*w,c*z+s*x,c*w-s*y)
  norm=math.sqrt(sum(x*x for x in expected))
  expected=tuple(x/norm for x in expected)
  err=max(abs(a-b) for a,b in zip(expected,dst))
  require(err<=4e-7,"actual V7 correction not the reviewed +0.18 rad local-Y rotation")
  worst=max(worst,err)
 return worst

def compare_old_new(old_raw,new_raw,stage):
 old,obase,obin=glb(old_raw)
 new,nbase,nbin=glb(new_raw)
 require(old["asset"]["version"]==new["asset"]["version"]=="2.0"
         and old["extras"]["stage"]==new["extras"]["stage"]==stage
         and old["extras"]["donorSha256"]==new["extras"]["donorSha256"]==DONOR,
         "wrong original Hoarder and V6/V7 lineage")
 require(len(old["skins"])==len(new["skins"])==1
         and len(old["skins"][0]["joints"])==108
         and len(new["skins"][0]["joints"])==108
         and len(old["animations"])==len(new["animations"])==381,
         "source rig or animation catalogue changed")
 keys=set(old)-{"asset","extras","animations","buffers","accessors","bufferViews"}
 require(all(old[k]==new[k] for k in keys),
         "original mesh, skin, material or nodes differ")
 require(old["bufferViews"]==new["bufferViews"][:len(old["bufferViews"])]
         and old["accessors"]==new["accessors"][:len(old["accessors"])]
         and len(new["bufferViews"])==len(old["bufferViews"])+1
         and len(new["accessors"])==len(old["accessors"])+1,
         "original binary accessor was modified or new track count differs")
 require(old["animations"][-1]==new["animations"][-1]
         and old["animations"][-1]["name"].startswith("growth-"+stage+"-to-"),
         "original next-stage growth modified")
 identity=new["extras"].get("orbit02ClearanceCorrection",{})
 require(identity.get("schema")=="skeleton.emerald.orbit02-tail-clearance.v1"
         and identity.get("source_v6_sha256")==FILES[stage]["v6"][1]
         and identity.get("donor_sha256")==DONOR
         and identity.get("joint_index")==JOINT
         and identity.get("clip")==CLIP
         and identity.get("local_y_radians")==ANGLE
         and identity.get("modified_keyframes")==160
         and all(identity.get(flag) is False for flag in (
             "equipment_enabled","continuous_collision_qualified",
             "real_mixer_qualified","crossfade_transition_qualified",
             "artist_approved","physical_rtx_verified","release_qualified")),
         "wrong V7 tail correction or false GPU/art/release claim")
 # Compare hash of actual complete source embedded BIN, not a sampled prefix.
 a=memoryview(old_raw)[obase:obase+obin]
 b=memoryview(new_raw)[nbase:nbase+obin]
 try:
  ha=hashlib.sha256(a).hexdigest()
  hb=hashlib.sha256(b).hexdigest()
  require(ha==hb,"original full embedded BIN bytes changed")
 finally:
  a.release();b.release()

 changed=0
 for a,b in zip(old["animations"],new["animations"]):
  require(a["name"]==b["name"] and a["channels"]==b["channels"]
          and len(a["samplers"])==len(b["samplers"]),
          "source animation declarations differ")
  if a["name"]!=CLIP:
   require(a==b,"unreviewed original animation changed")
   continue
  node=old["skins"][0]["joints"][JOINT]
  for channel in a["channels"]:
   before=a["samplers"][channel["sampler"]]
   after=b["samplers"][channel["sampler"]]
   if channel["target"]=={"node":node,"path":"rotation"}:
    require(before["input"]==after["input"]
            and before["interpolation"]==after["interpolation"]=="LINEAR",
            "original tail timebase changed")
    error=correction_error(read_rotations(old_raw,old,obase,before["output"]),
                           read_rotations(new_raw,new,nbase,after["output"]))
    changed+=1
   else:require(before==after,"untargeted original sampler changed")
 require(changed==1,"wrong corrected stream count")
 return {"original_binary_prefix_sha256":ha,
         "original_binary_prefix_identical":True,
         "source_mesh_skin_material_nodes_exact":True,
         "growth_animation_exact":True,
         "rig_joints":108,"total_animation_clips":381,
         "new_animation_accessors":1,
         "new_animation_views":1,
         "modified_clip":CLIP,"modified_keyframes":160,
         "max_corrected_quaternion_error":error,
         "release_qualified":False}

def audit(v6_directory,v7_directory,output):
 target=Path(output)
 require(target.parent.is_dir() and not target.parent.is_symlink()
         and not os.path.lexists(target),"trusted unused receipt path required")
 result={"schema":"skeleton.emerald.v7.original-binary-custody-independent.v1",
         "original_donor_sha256":DONOR,"models":[],"exact_original_models_checked":0,
         "source_bytes_not_modified":True,
         "full_continuous_collision_qualified":False,
         "real_three_mixer_qualified":False,
         "artist_approved":False,"physical_rtx_verified":False,
         "remote_git_binary_verified":False,"release_qualified":False}
 with tempfile.TemporaryDirectory(prefix="emerald-original-binary-") as root:
  for stage in STAGES:
   paths={}
   metadata={}
   for generation,directory in (("v6",v6_directory),("v7",v7_directory)):
    filename=(stage+"-v6-tail-clearance.zip" if generation=="v6"
              else stage+"-v7-orbit02-clearance.zip")
    original=Path(directory)/filename
    temp=Path(root)/(stage+"-"+generation+".glb")
    metadata[generation]=archive_to_scratch(original,stage,generation,temp)
    paths[generation]=temp
   with paths["v6"].open("rb") as fa,paths["v7"].open("rb") as fb:
    a=mmap.mmap(fa.fileno(),0,access=mmap.ACCESS_READ)
    b=mmap.mmap(fb.fileno(),0,access=mmap.ACCESS_READ)
    try:structural=compare_old_new(a,b,stage)
    finally:a.close();b.close()
   result["models"].append({"stage":stage,**metadata,**structural})
  result["exact_original_models_checked"]=len(result["models"])
 require(result["exact_original_models_checked"]==2,"missing exact stage")
 with target.open("x",encoding="utf-8") as stream:
  json.dump(result,stream,indent=2)
  stream.write("\n");stream.flush();os.fsync(stream.fileno())
 return result

if __name__=="__main__":
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument("--v6-zips",required=True,type=Path)
 p.add_argument("--v7-zips",required=True,type=Path)
 p.add_argument("--out",required=True,type=Path)
 a=p.parse_args()
 print(json.dumps(audit(a.v6_zips,a.v7_zips,a.out),indent=2))
