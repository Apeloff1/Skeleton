"""Review-only exact byte custody and fast-forward transport for two V5 stages."""
from __future__ import annotations
import argparse,hashlib,json,os,re,shutil,subprocess,tempfile
from pathlib import Path
from emerald_v5_proximal_wingfold import SOURCES,OUTPUTS,DONOR,require,sha

ROOT=Path(__file__).resolve().parents[1]
MANIFEST=ROOT/"assets/emerald/evolution-v5/proximal-wingfold-publication.json"
MAX=32*1024**2
STAGES=("pathfinder","archivist")
REMOTES={"https://github.com/Apeloff1/Skeleton","https://github.com/Apeloff1/Skeleton.git","git@github.com:Apeloff1/Skeleton.git","ssh://git@github.com/Apeloff1/Skeleton.git"}
OID=re.compile("[a-f0-9]{40}(?:[a-f0-9]{24})?\\Z")
SHA=re.compile("[a-f0-9]{64}\\Z")

def load():
 raw=MANIFEST.read_bytes()
 m=json.loads(raw)
 require(m.get("schema")=="skeleton.emerald.proximal-wingfold-publication.v1"
         and m.get("donor_sha256")==DONOR
         and m.get("stage_order")==list(STAGES)
         and m.get("max_chunk_bytes")==MAX
         and m.get("remote_binary_published") is False
         and m.get("equipment_enabled") is False
         and m.get("release_qualified") is False,"manifest admission mismatch")
 forms=m.get("forms",[])
 require(len(forms)==2 and tuple(x["stage"] for x in forms)==STAGES,"unexpected stage count")
 for f in forms:
  stage=f["stage"];src_bytes,src_sha,_=SOURCES[stage];output_bytes,output_sha=OUTPUTS[stage]
  require(f.get("model")==stage+".glb" and
          f.get("bytes")==output_bytes and f.get("sha256")==output_sha
          and f.get("source_sha256")==src_sha and
          f.get("bundle")==stage+"-wingfold-v5.zip"
          and SHA.fullmatch(f.get("bundle_sha256","")) and
          all(f.get(flag) is False for flag in ("automatic_adoption",
              "full_continuous_collision_qualified","artist_approved",
              "physical_rtx_verified","release_qualified")),
          "unexpected model identity or false qualification")
  require(len(f.get("parts",[]))==4,"four exact raw parts required")
  start=0
  for i,row in enumerate(f["parts"]):
   size=min(MAX,output_bytes-start)
   path=f"assets/emerald/evolution-v5/{stage}/{stage}.glb.part{i+1:03d}"
   require(size>0 and row.get("path")==path and row.get("offset")==start
           and row.get("bytes")==size and SHA.fullmatch(row.get("sha256","")),
           "missing or repinned binary part")
   start+=size
  require(start==output_bytes,"incomplete binary model")
 return forms,raw

def verified_parts(directory,form):
 root=Path(directory)
 require(root.is_dir() and not root.is_symlink(),"trusted local parts directory required")
 for part in form["parts"]:
  path=root/Path(part["path"]).name
  require(path.is_file() and not path.is_symlink() and
          path.stat().st_size==part["bytes"] and sha(path)==part["sha256"],
          "missing or incorrect original slice: "+part["path"])
  yield path,part

def verify_tree(repo,form):
 root=Path(repo)
 digest=hashlib.sha256()
 for row in form["parts"]:
  path=root/row["path"]
  require(path.is_file() and not path.is_symlink() and
          path.stat().st_size==row["bytes"] and sha(path)==row["sha256"],
          "remote Git blob not present or invalid: "+row["path"])
  with path.open("rb") as f:
   while block:=f.read(1024**2):digest.update(block)
 require(digest.hexdigest()==form["sha256"],"whole stage SHA differs")
 return {"stage":form["stage"],"sha256":form["sha256"],"verified_bytes":form["bytes"],
         "release_qualified":False,"hardware_qualified":False}

def assemble(directory,output,form):
 output=Path(output)
 require(output.name==form["model"] and output.parent.is_dir() and
         not output.parent.is_symlink() and not os.path.lexists(output),
         "trusted new model output required")
 require(shutil.disk_usage(output.parent).free>=form["bytes"]+MAX,
         "insufficient disk space")
 rows=list(verified_parts(directory,form))
 with tempfile.TemporaryDirectory(prefix=".emerald-v5-",dir=output.parent) as tmp:
  transient=Path(tmp)/form["model"];hasher=hashlib.sha256();length=0
  with transient.open("xb") as dst:
   for src,part in rows:
    with src.open("rb") as stream:
     while block:=stream.read(1024**2):
      hasher.update(block);dst.write(block);length+=len(block)
   dst.flush();os.fsync(dst.fileno())
  require(length==form["bytes"] and hasher.hexdigest()==form["sha256"],
          "assembled output does not match original candidate")
  require(not os.path.lexists(output),"output appeared before publication")
  os.rename(transient,output)
 return {"stage":form["stage"],"sha256":form["sha256"],"assembled":True,
         "release_qualified":False}

def git(repo,*args,data=None,env=None):
 return subprocess.run(["git","-C",str(repo),*args],input=data,
                       stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True,env=env).stdout

def obj(data):
 code=data.decode("ascii").strip()
 require(OID.fullmatch(code),"untrusted Git object identifier")
 return code

def publish(repo,form,parts,manifest_raw):
 for args in (("remote","get-url","origin"),("remote","get-url","--push","origin")):
  require(git(repo,*args).decode().strip() in REMOTES,"origin not exact authorized repository")
 branch="refs/heads/assets/emerald-v5-"+form["stage"]+"-proximal-20261117"
 git(repo,"fetch","--no-tags","origin",branch)
 head=obj(git(repo,"rev-parse","FETCH_HEAD"))
 require(git(repo,"show",head+":"+MANIFEST.relative_to(ROOT).as_posix())==manifest_raw,
         "remote candidate manifest changed")
 with tempfile.TemporaryDirectory(prefix="emerald-v5-index-") as tmp:
  env=dict(os.environ,GIT_INDEX_FILE=str(Path(tmp)/"index"))
  git(repo,"read-tree",head,env=env)
  for src,row in verified_parts(parts,form):
   blob=obj(git(repo,"hash-object","-w","--no-filters","--stdin",data=src.read_bytes()))
   old=git(repo,"ls-tree",head,"--",row["path"]).decode().strip()
   if old:
    require(old==f"100644 blob {blob}\\t{row['path']}","refusing altered source blob")
   else:git(repo,"update-index","--add","--cacheinfo",f"100644,{blob},{row['path']}",env=env)
  tree=obj(git(repo,"write-tree",env=env))
 if tree!=obj(git(repo,"rev-parse",head+"^{tree}")):
  commit=obj(git(repo,"commit-tree",tree,"-p",head,"-m","assets(dragon): exact original-donor V5 "+form["stage"]))
  git(repo,"push","origin",commit+":"+branch)
  head=commit
 require(git(repo,"ls-remote","--exit-code","origin",branch).decode().split()==[head,branch],
         "remote was concurrently modified")
 return head

def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument("mode",choices=("verify-tree","assemble","publish"))
 p.add_argument("--stage",choices=STAGES,required=True)
 p.add_argument("--repo",type=Path,default=ROOT)
 p.add_argument("--parts",type=Path)
 p.add_argument("--output",type=Path)
 args=p.parse_args()
 forms,raw=load();f=next(x for x in forms if x["stage"]==args.stage)
 if args.mode=="verify-tree":result=verify_tree(args.repo,f)
 elif args.mode=="assemble":
  require(args.parts is not None and args.output is not None,"--parts and --output required")
  result=assemble(args.parts,args.output,f)
 else:
  require(args.parts is not None,"--parts required")
  # Check all source slices first; no release or secret handling by this program.
  list(verified_parts(args.parts,f))
  result={"stage":f["stage"],"head":publish(args.repo,f,args.parts,raw),
          "release_qualified":False,"continuous_collision_qualified":False}
 print(json.dumps(result,indent=2))

if __name__=="__main__":main()
