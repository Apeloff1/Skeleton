"""Exact SHA-pinned raw Git delivery for both V6 full-density Dragon models.

No force pushes, model repins, credential handling, deployment, merges or releases.
Operator must use existing authenticated Apeloff1/Skeleton Git checkout.
"""
from __future__ import annotations
import argparse,hashlib,json,os,re,shutil,subprocess,tempfile,zipfile
from pathlib import Path
from emerald_v6_tail_clearance import PINNED,OUTPUTS,DONOR,CLIPS,require

ROOT=Path(__file__).resolve().parents[1]
MANIFEST=ROOT/"assets/emerald/evolution-v6/publication-manifest.json"
STAGES=("pathfinder","archivist")
MAX_PART=32*1024**2
REMOTE={
 "https://github.com/Apeloff1/Skeleton",
 "https://github.com/Apeloff1/Skeleton.git",
 "git@github.com:Apeloff1/Skeleton.git",
 "ssh://git@github.com/Apeloff1/Skeleton.git",
}
OID=re.compile(r"[a-f0-9]{40}(?:[a-f0-9]{24})?\Z")
SHA=re.compile(r"[a-f0-9]{64}\Z")

def digest(data):
 return hashlib.sha256(data).hexdigest()

def load():
 raw=MANIFEST.read_bytes()
 require(len(raw)<65536,"unexpectedly large publication manifest")
 m=json.loads(raw)
 require(m.get("schema")=="skeleton.emerald.v6.tail-clearance-publication.v1"
         and m.get("donor_sha256")==DONOR
         and m.get("maximum_chunk_bytes")==MAX_PART
         and m.get("remote_binary_published") is False
         and m.get("review_only") is True
         and all(m.get(flag) is False for flag in (
           "artist_approved","cross_clip_transition_qualified",
           "continuous_collision_qualified","physical_rtx_verified",
           "release_qualified")),"untrusted publication identity or false approval")
 forms=m.get("forms",[])
 require(isinstance(forms,list) and tuple(x.get("stage") for x in forms)==STAGES,
         "missing or duplicated original evolution stage")
 for form in forms:
  stage=form["stage"];size,sha=OUTPUTS[stage]
  require(form.get("asset")==stage+".glb" and
          (form.get("bytes"),form.get("sha256"))==(size,sha) and
          form.get("source_v5_sha256")==PINNED[stage][1] and
          form.get("corrected_motion_clips")==list(CLIPS) and
          form.get("modified_tracks")==2 and form.get("modified_keyframes")==278 and
          all(form.get(flag) is False for flag in (
            "automatic_adoption","cross_clip_transition_qualified",
            "continuous_collision_qualified","artist_approved",
            "physical_rtx_verified","release_qualified")),
          "unapproved V6 byte identity or qualification claim")
  parts=form.get("parts",[])
  require(isinstance(parts,list) and len(parts)==4,
          "exactly four per-form binary parts required")
  offset=0
  for i,row in enumerate(parts):
   expected=min(MAX_PART,size-offset)
   expected_path=f"assets/emerald/evolution-v6/{stage}/{stage}.glb.part{i+1:03d}"
   require(expected>0 and row.get("path")==expected_path and
           row.get("offset")==offset and row.get("bytes")==expected and
           SHA.fullmatch(row.get("sha256","")),
           "wrong or reordered original binary part")
   offset+=expected
  require(offset==size,"truncated original binary file")
 return forms,raw

def verified_archive(bundle,form):
 """Do not extract ZIP members; stream exactly the model declared by the pin."""
 bundle=Path(bundle)
 require(bundle.is_file() and not bundle.is_symlink(),"missing or linked ZIP")
 with zipfile.ZipFile(bundle) as z:
  infos=z.infolist()
  require(len(infos)<=64 and sum(x.file_size for x in infos)<=512*1024**2,
          "ZIP quota exceeded")
  names=set()
  for info in infos:
   name=info.filename
   require(not info.is_dir() and not info.flag_bits&1
           and not name.startswith("/") and "\\" not in name
           and all(x not in ("",".","..") for x in name.split("/"))
           and name.casefold() not in names and
           ((info.external_attr>>16)&0o170000)!=0o120000,
           "unsafe ZIP member")
   names.add(name.casefold())
  info=z.getinfo(form["asset"])
  require(info.file_size==form["bytes"],"ZIP original model length mismatch")
  whole=hashlib.sha256()
  with z.open(info) as stream:
   for row in form["parts"]:
    data=stream.read(row["bytes"])
    require(len(data)==row["bytes"] and digest(data)==row["sha256"],
            "original file chunk hash mismatch: "+row["path"])
    whole.update(data)
    yield row,data
   require(not stream.read(1) and whole.hexdigest()==form["sha256"],
           "complete original model digest mismatch")

def verify_tree(repo,form):
 sha=hashlib.sha256()
 for row in form["parts"]:
  source=Path(repo)/row["path"]
  require(source.is_file() and not source.is_symlink() and
          source.stat().st_size==row["bytes"],"missing Git original: "+row["path"])
  with source.open("rb") as inp:
   data=inp.read()
  require(digest(data)==row["sha256"],"raw Git chunk changed: "+row["path"])
  sha.update(data)
 require(sha.hexdigest()==form["sha256"],"whole Git model differs from original")
 return {"stage":form["stage"],"verified_glb_sha256":form["sha256"],
         "verified_bytes":form["bytes"],"actual_checkout_bytes_verified":True,
         "device_qualified":False,"release_qualified":False}

def git(repo,*args,data=None,env=None):
 return subprocess.run(["git","-C",str(repo),*args],input=data,
                       stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                       check=True,env=env).stdout

def oid(data):
 result=data.decode("ascii").strip()
 require(OID.fullmatch(result),"invalid Git object identity")
 return result

def check_remote(repo):
 for args in (("remote","get-url","origin"),("remote","get-url","--push","origin")):
  require(git(repo,*args).decode().strip() in REMOTE,
          "fetch/push origin is not exact authorized Skeleton")

def branch(stage):
 require(stage in STAGES,"unsupported raw binary stage")
 return "refs/heads/assets/emerald-v6-"+stage+"-tail-clearance-20261117"

def fetch_group(repo,form,raw):
 ref=branch(form["stage"])
 git(repo,"fetch","--no-tags","origin",ref)
 head=oid(git(repo,"rev-parse","FETCH_HEAD"))
 require(git(repo,"show",head+":"+MANIFEST.relative_to(ROOT).as_posix())==raw,
         "remote draft manifest differs from exact expected data")
 return ref,head

def publish_group(repo,form,bundle,raw):
 ref,head=fetch_group(repo,form,raw)
 with tempfile.TemporaryDirectory(prefix="emerald-v6-index-") as work:
  env=dict(os.environ,GIT_INDEX_FILE=str(Path(work)/"index"))
  git(repo,"read-tree",head,env=env)
  for row,data in verified_archive(bundle,form):
   blob=oid(git(repo,"hash-object","-w","--no-filters","--stdin",data=data))
   existing=git(repo,"ls-tree",head,"--",row["path"]).decode().strip()
   if existing:
    require(existing==f"100644 blob {blob}\t{row['path']}",
            "refuse to overwrite original Git chunk")
   else:
    git(repo,"update-index","--add","--cacheinfo",
        f"100644,{blob},{row['path']}",env=env)
  tree=oid(git(repo,"write-tree",env=env))
 if tree!=oid(git(repo,"rev-parse",head+"^{tree}")):
  head=oid(git(repo,"commit-tree",tree,"-p",head,
              "-m","assets(dragon): exact V6 "+form["stage"]+" original bytes"))
  git(repo,"push","origin",head+":"+ref)
 require(git(repo,"ls-remote","--exit-code","origin",ref).decode().split()==[head,ref],
         "remote draft advanced concurrently; verify again")
 return head

def reconstruct(repo,forms,raw,destination):
 dest=Path(destination).absolute()
 require(dest.parent.is_dir() and not dest.parent.is_symlink()
         and not os.path.lexists(dest),"trusted unused destination directory required")
 required=sum(f["bytes"] for f in forms)
 require(shutil.disk_usage(dest.parent).free>=required+MAX_PART,
         "insufficient scratch storage")
 heads={f["stage"]:fetch_group(repo,f,raw)[1] for f in forms}
 with tempfile.TemporaryDirectory(dir=dest.parent,prefix=".emerald-v6-reassembly-") as temp:
  temp=Path(temp)
  for form in forms:
   whole=hashlib.sha256();size=0
   with (temp/form["asset"]).open("xb") as out:
    for row in form["parts"]:
     path=heads[form["stage"]]+":"+row["path"]
     require(int(git(repo,"cat-file","-s",path))==row["bytes"],
             "remote original chunk size differs")
     data=git(repo,"cat-file","blob",path)
     require(len(data)==row["bytes"] and digest(data)==row["sha256"],
             "remote original chunk digest differs")
     out.write(data);whole.update(data);size+=len(data)
    out.flush();os.fsync(out.fileno())
   require(size==form["bytes"] and whole.hexdigest()==form["sha256"],
           "remote complete original model differs")
  require(not os.path.lexists(dest),"destination concurrently appeared")
  os.rename(temp,dest)
 return {"verified_remote_heads":heads,
         "verified_model_bytes":required,"release_qualified":False}

def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument("mode",choices=("verify-bundles","publish","verify-tree","reconstruct"))
 p.add_argument("--repo",type=Path,default=ROOT)
 p.add_argument("--bundles",type=Path)
 p.add_argument("--destination",type=Path)
 p.add_argument("--stage",choices=STAGES,action="append")
 args=p.parse_args()
 forms,raw=load()
 chosen=[f for f in forms if not args.stage or f["stage"] in args.stage]
 if args.mode=="verify-tree":
  print(json.dumps({"verified":[verify_tree(args.repo,x) for x in chosen]},indent=2));return
 if args.mode=="reconstruct":
  require(args.stage is None and args.destination is not None,
          "must reassemble all forms into a new destination")
  check_remote(args.repo)
  print(json.dumps(reconstruct(args.repo,forms,raw,args.destination),indent=2));return
 require(args.bundles is not None,"--bundles original directory required")
 for form in chosen:
  for _ in verified_archive(args.bundles/(form["stage"]+"-v6-tail-clearance.zip"),form):
   pass
 if args.mode=="publish":
  check_remote(args.repo)
  for form in chosen:
   head=publish_group(args.repo,form,args.bundles/(form["stage"]+"-v6-tail-clearance.zip"),raw)
   print(json.dumps({"stage":form["stage"],"published_head":head,
                     "release_qualified":False}),flush=True)
 else:
  print(json.dumps({"local_original_bundles_verified":[f["stage"] for f in chosen],
                    "remote_binary_published":False,"release_qualified":False},indent=2))

if __name__=="__main__":
 main()
