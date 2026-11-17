"""Stage the five reviewed original V7 contact tools from two exact-source ZIPs.

This is OFFLINE original-byte custody. It neither executes ZIP content nor
grants collision/device/art/release approval. Only exact SHA-bound Python files
are copied, no native executable or full model GLB is extracted.
"""
from __future__ import annotations
import argparse,hashlib,json,os,shutil,stat,tempfile,zipfile
from pathlib import Path

ARCHIVES={
 "contact":{
   "name":"source-and-contact-evidence.zip",
   "bytes":60591,
   "sha256":"fc5b15192353c28af7af1d7a8af7762c3c1207d46d3cb14df01e5809c9004cda",
 },
 "seams":{
   "name":"pathfinder-v6-tail-clearance.zip",
   "bytes":114764553,
   "sha256":"7fb92f1fe2b5e14c7fbae2a631a190ead4087f8f0888eb83dd2b2a505a7d0773",
 },
}
FILES={
 "contact_audit.py":("contact",23471,"0333ec4e01f701554e6f62b443fc5b2283bb68e8a62aaf324760068cc7107d4f"),
 "contact_geometry.py":("contact",4921,"ab08763903de7d222881e69cd1f8dc14e0c2f67be8c0ff22a15164f55bb132f5"),
 "contact_geometry_accel.py":("contact",4946,"fd5bd4c28ff528e3be7e0500476c27e52f054a0ef9ff34fa9ec9294d4800e431"),
 "fast_wing_witness.py":("contact",2399,"e170a70ec2522ef4a162ef53c8d3aabcf2a3ce110dc7fbeadca8852480845187"),
 "analyze_seams.py":("seams",6638,"482391dd5a68ad36411a315aab7abcb0b70febbca3dc780fb217f6f4fd32dc1a"),
}
LIMIT_ENTRIES=128
LIMIT_DECLARED_BYTES=512*1024**2
MAX_TOOL_BYTES=256*1024
MODEL_SHA="c9807afdffd61640cb2d8e1ed6d17250d4a9613965269f0e0bf12c0c979a9a6a"

def require(ok,message):
 if not ok:raise ValueError(message)

def digest(path):
 with Path(path).open("rb") as stream:
  return hashlib.file_digest(stream,"sha256").hexdigest()

def authorize_archive(path,kind):
 spec=ARCHIVES[kind]
 path=Path(path)
 require(path.is_file() and not path.is_symlink()
         and path.stat().st_size==spec["bytes"] and digest(path)==spec["sha256"],
         "archive source SHA, length or filesystem custody differs: "+kind)
 return path

def safe_index(z):
 index={}
 members=z.infolist()
 require(len(members)<=LIMIT_ENTRIES
         and sum(i.file_size for i in members)<=LIMIT_DECLARED_BYTES,
         "unsafe archive quota")
 for item in members:
  name=item.filename
  parts=name.split("/")
  mode=(item.external_attr>>16)&0o170000
  require(isinstance(name,str) and
          name and not item.is_dir() and
          not name.startswith("/") and "\\" not in name and
          all(s not in ("",".","..") for s in parts) and
          name.casefold() not in index and
          not item.flag_bits&1 and mode!=0o120000,
          "unsafe, linked or duplicate archive member")
  index[name.casefold()]=item
 return index

def checked_source(z,index,name,source_kind):
 member_name="Tools/"+name
 info=index.get(member_name.casefold())
 require(info is not None and info.filename==member_name,
         "original reviewed tool member missing: "+name)
 kind,expected_size,expected_sha=FILES[name]
 require(kind==source_kind and info.file_size==expected_size and
         expected_size<=MAX_TOOL_BYTES,
         "source tool length or source archive mismatch: "+name)
 with z.open(info) as source:
  content=source.read(MAX_TOOL_BYTES+1)
 require(len(content)==expected_size and
         hashlib.sha256(content).hexdigest()==expected_sha,
         "reviewed tool bytes modified: "+name)
 # Must remain valid text source and cannot include a byte-order marker.
 require(not content.startswith(b"\xef\xbb\xbf")
         and b"\0" not in content
         and content.decode("utf-8").encode("utf-8")==content,
         "untrusted or non-UTF-8 source tool")
 return content

def stage(contacts_zip,seams_zip,out_dir):
 destination=Path(out_dir).absolute()
 parent=destination.parent
 require(parent.is_dir() and not parent.is_symlink()
         and not os.path.lexists(destination),
         "trusted unused original review tools directory required")
 paths={
  "contact":authorize_archive(contacts_zip,"contact"),
  "seams":authorize_archive(seams_zip,"seams"),
 }
 payload={}
 for kind,path in paths.items():
  with zipfile.ZipFile(path) as archive:
   index=safe_index(archive)
   for filename,(source_kind,*_) in FILES.items():
    if source_kind==kind:
     payload[filename]=checked_source(archive,index,filename,kind)
 require(set(payload)==set(FILES),"one or more reviewed source dependencies missing")
 receipt={
  "schema":"skeleton.emerald.reviewed-tools-custody.v1",
  "donor_sha256":MODEL_SHA,
  "archives":{kind:{"sha256":ARCHIVES[kind]["sha256"],
                    "bytes":ARCHIVES[kind]["bytes"]}
              for kind in ARCHIVES},
  "staged_files":{
   name:{"bytes":FILES[name][1],"sha256":FILES[name][2],
         "original_archive":FILES[name][0]}
   for name in sorted(payload)},
  "staged_file_count":len(payload),
  "original_model_bytes_copied":False,
  "source_executed_by_this_command":False,
  "measured_contact_clearance":False,
  "continuous_collision_qualified":False,
  "real_three_mixer_qualified":False,
  "artist_approved":False,
  "physical_rtx_verified":False,
  "release_qualified":False,
 }
 lock=parent/("."+destination.name+".qualification.lock")
 require(not os.path.lexists(lock),"independent qualification already publishing")
 lock.mkdir(mode=0o700)
 try:
  require(not os.path.lexists(destination),"destination appeared during qualification")
  with tempfile.TemporaryDirectory(dir=parent,prefix=".emerald-review-tools-") as temporary:
   work=Path(temporary)
   for name,data in sorted(payload.items()):
    file=work/name
    with file.open("xb") as stream:
     stream.write(data)
     stream.flush()
     os.fsync(stream.fileno())
    file.chmod(0o444)
   with (work/"source-custody.json").open("x",encoding="utf-8") as stream:
    json.dump(receipt,stream,indent=2,sort_keys=True)
    stream.write("\n")
    stream.flush();os.fsync(stream.fileno())
   require(all(digest(work/name)==FILES[name][2] for name in payload),
           "staged original source mutated")
   require(not os.path.lexists(destination),"destination appeared during staging")
   # Non-cooperating writers require independent filesystem policy enforcement.
   os.rename(work,destination)
   return receipt
 finally:
  lock.rmdir()

def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument("--contact-archive",type=Path,required=True)
 p.add_argument("--v6-archive",type=Path,required=True)
 p.add_argument("--output",type=Path,required=True)
 a=p.parse_args()
 print(json.dumps(stage(a.contact_archive,a.v6_archive,a.output),indent=2))

if __name__=="__main__":
 main()
