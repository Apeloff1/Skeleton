"""Fail-closed exact V7 original binary publication and Git SHA reassembly.

No LFS-pointer substitution, model repinning, force-push, merge or release.
Requires a trusted authenticated local Apeloff1/Skeleton checkout.
"""
from __future__ import annotations
import argparse,hashlib,json,os,re,shutil,subprocess,tempfile,zipfile
from pathlib import Path
from emerald_v7_orbit02 import SOURCES,OUTPUTS,DONOR,ROOT_JOINT,ANGLE,TARGET_CLIP,require

ROOT=Path(__file__).resolve().parents[1]
MANIFEST=ROOT/"assets/emerald/evolution-v7/publication-manifest.json"
STAGES=("pathfinder","archivist")
PART=32*1024**2
REMOTES={
 "https://github.com/Apeloff1/Skeleton",
 "https://github.com/Apeloff1/Skeleton.git",
 "git@github.com:Apeloff1/Skeleton.git",
 "ssh://git@github.com/Apeloff1/Skeleton.git",
}
OID=re.compile(r"[a-f0-9]{40}(?:[a-f0-9]{24})?\Z")
HEX=re.compile(r"[a-f0-9]{64}\Z")

def digest(data):return hashlib.sha256(data).hexdigest()
def sha(path):
 with Path(path).open("rb") as source:return hashlib.file_digest(source,"sha256").hexdigest()

def load():
 raw=MANIFEST.read_bytes()
 require(len(raw)<65536,"manifest quota exceeded")
 doc=json.loads(raw)
 require(doc.get("schema")=="skeleton.emerald.orbit02-v7-publication.v1"
         and doc.get("donor_sha256")==DONOR and doc.get("max_chunk_bytes")==PART
         and doc.get("remote_binary_published") is False
         and doc.get("release_qualified") is False,
         "wrong source of truth or falsely published model")
 forms=doc.get("forms",[])
 require(isinstance(forms,list) and tuple(f.get("stage") for f in forms)==STAGES,
         "wrong stage count or order")
 for form in forms:
  stage=form["stage"];bytes_expected,hash_expected=OUTPUTS[stage]
  require(form.get("asset")==stage+".glb" and
          (form.get("bytes"),form.get("sha256"))==(bytes_expected,hash_expected)
          and form.get("source_v6_sha256")==SOURCES[stage][1]
          and form.get("zip_filename")==stage+"-v7-orbit02-clearance.zip"
          and HEX.fullmatch(form.get("zip_sha256",""))
          and form.get("modified_clip")==TARGET_CLIP
          and form.get("tail_root_joint_index")==ROOT_JOINT
          and form.get("local_y_radians")==ANGLE
          and form.get("modified_sampler_streams")==1
          and form.get("modified_keyframes")==160
          and all(form.get(k) is False for k in (
              "automatic_adoption","continuous_collision_qualified",
              "real_three_mixer_qualified","artistic_approved",
              "physical_rtx_verified","release_qualified")),
          "incorrect binary source or false qualification")
  parts=form.get("parts",[])
  require(isinstance(parts,list) and len(parts)==4,"expected four raw chunks")
  offset=0
  for index,item in enumerate(parts):
   size=min(PART,bytes_expected-offset)
   path=f"assets/emerald/evolution-v7/{stage}/{stage}.glb.part{index+1:03}"
   require(size>0 and item.get("path")==path
           and item.get("offset")==offset and item.get("bytes")==size
           and HEX.fullmatch(item.get("sha256","")),
           "missing, corrupted or out-of-order raw slice")
   offset+=size
  require(offset==bytes_expected,"model byte extent is incomplete")
 return forms,raw

def verified_zip(path,form):
 path=Path(path)
 require(path.is_file() and not path.is_symlink()
         and sha(path)==form["zip_sha256"],"unverified original ZIP container")
 with zipfile.ZipFile(path) as bundle:
  entries=bundle.infolist()
  require(len(entries)<=64 and
          sum(e.file_size for e in entries)<=512*1024**2,
          "unsafe number or size of original ZIP members")
  names=set()
  for e in entries:
   name=e.filename
   require(not e.is_dir() and not (e.flag_bits&1)
           and not name.startswith("/") and "\\" not in name
           and all(part not in ("",".","..") for part in name.split("/"))
           and name.casefold() not in names
           and ((e.external_attr>>16)&0o170000)!=0o120000,
           "linked, encrypted, duplicate or traversing ZIP member")
   names.add(name.casefold())
  glb=bundle.getinfo(form["asset"])
  require(glb.file_size==form["bytes"],"original GLB size differs")
  complete=hashlib.sha256()
  with bundle.open(glb) as stream:
   for part in form["parts"]:
    data=stream.read(part["bytes"])
    require(len(data)==part["bytes"] and digest(data)==part["sha256"],
            "original GLB chunk SHA mismatch: "+part["path"])
    complete.update(data)
    yield part,data
   require(not stream.read(1) and complete.hexdigest()==form["sha256"],
           "complete original model SHA mismatch")

def verify_tree(root,form):
 complete=hashlib.sha256()
 for part in form["parts"]:
  path=Path(root)/part["path"]
  require(path.is_file() and not path.is_symlink()
          and path.stat().st_size==part["bytes"],
          "original raw Git binary missing: "+part["path"])
  data=path.read_bytes()
  require(digest(data)==part["sha256"],"raw Git blob altered: "+part["path"])
  complete.update(data)
 require(complete.hexdigest()==form["sha256"],"whole raw Git model changed")
 return {"stage":form["stage"],"verified_source_bytes":form["bytes"],
         "verified_original_sha256":form["sha256"],
         "actual_git_bytes_verified":True,"release_qualified":False}

def git(repo,*args,data=None,env=None):
 return subprocess.run(["git","-C",str(repo),*args],input=data,stdout=subprocess.PIPE,
                       stderr=subprocess.PIPE,check=True,env=env).stdout

def oid(raw):
 value=raw.decode("ascii").strip()
 require(OID.fullmatch(value),"untrusted Git object id")
 return value

def authorized(repo):
 for arguments in (("remote","get-url","origin"),
                   ("remote","get-url","--push","origin")):
  require(git(repo,*arguments).decode().strip() in REMOTES,
          "unauthorized original binary remote")

def target_ref(stage):
 require(stage in STAGES,"unsupported published stage")
 return "refs/heads/assets/emerald-v7-"+stage+"-orbit02-20261117"

def head(repo,form,raw):
 ref=target_ref(form["stage"])
 git(repo,"fetch","--no-tags","origin",ref)
 base=oid(git(repo,"rev-parse","FETCH_HEAD"))
 require(git(repo,"show",base+":"+MANIFEST.relative_to(ROOT).as_posix())==raw,
         "remote publication manifest differs from pinned bytes")
 return ref,base

def publish(repo,form,bundle,raw):
 ref,base=head(repo,form,raw)
 with tempfile.TemporaryDirectory(prefix="emerald-v7-index-") as temp:
  env=dict(os.environ,GIT_INDEX_FILE=str(Path(temp)/"index"))
  git(repo,"read-tree",base,env=env)
  for row,data in verified_zip(bundle,form):
   blob=oid(git(repo,"hash-object","-w","--no-filters","--stdin",data=data))
   existing=git(repo,"ls-tree",base,"--",row["path"]).decode().strip()
   if existing:
    require(existing==f"100644 blob {blob}\t{row['path']}",
            "existing original Git blob differs")
   else:git(repo,"update-index","--add","--cacheinfo",
            f"100644,{blob},{row['path']}",env=env)
  tree=oid(git(repo,"write-tree",env=env))
 if tree!=oid(git(repo,"rev-parse",base+"^{tree}")):
  base=oid(git(repo,"commit-tree",tree,"-p",base,
               "-m","assets(dragon): exact V7 original "+form["stage"]))
  git(repo,"push","origin",base+":"+ref)
 require(git(repo,"ls-remote","--exit-code","origin",ref).decode().split()==[base,ref],
         "remote branch advanced or publication failed")
 return base

def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument("mode",choices=("verify-zip","publish","verify-tree"))
 p.add_argument("--stage",choices=STAGES,action="append")
 p.add_argument("--repo",type=Path,default=ROOT)
 p.add_argument("--bundles",type=Path)
 a=p.parse_args()
 forms,raw=load()
 chosen=[f for f in forms if not a.stage or f["stage"] in a.stage]
 if a.mode=="verify-tree":
  print(json.dumps({"verified":[verify_tree(a.repo,f) for f in chosen]},indent=2));return
 require(a.bundles is not None,"existing --bundles directory required")
 for f in chosen:
  for _ in verified_zip(a.bundles/f["zip_filename"],f):pass
 if a.mode=="publish":
  authorized(a.repo)
  for f in chosen:
   commit=publish(a.repo,f,a.bundles/f["zip_filename"],raw)
   print(json.dumps({"stage":f["stage"],"remote_head":commit,
                     "release_qualified":False}),flush=True)
 else:
  print(json.dumps({"verified_original_local_zips":[f["stage"] for f in chosen],
                    "remote_publication_verified":False,"release_qualified":False}))

if __name__=="__main__":main()
