"""Verify, split, publish and reassemble five pinned developmental GLBs.
Use an authenticated trusted checkout. Never force push, merge or release.
"""
import argparse, hashlib, json, os, re, shutil, subprocess, tempfile, zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
MANIFEST="assets/emerald/evolution-v3/publication-manifest.json"
STAGES=("hatchling","scout","scholar","pathfinder","archivist")
LIMIT=32*1024**2
REMOTES={"https://github.com/Apeloff1/Skeleton","https://github.com/Apeloff1/Skeleton.git","git@github.com:Apeloff1/Skeleton.git","ssh://git@github.com/Apeloff1/Skeleton.git"}
def require(x,msg):
    if not x: raise ValueError(msg)
def digest(data): return hashlib.sha256(data).hexdigest()
def load():
    raw=(ROOT/MANIFEST).read_bytes()
    m=json.loads(raw)
    pin=json.loads((ROOT/"frontend/src/features/Jeeves/companion/atelier/evolutionPin.json").read_bytes())
    require(m["schema"]=="skeleton.emerald.evolution-publication.v3" and m["donor_sha256"]==pin["donorSha256"] and m["chunk_max_bytes"]==LIMIT,"manifest identity")
    require(tuple(f["stage"] for f in m["forms"])==STAGES,"stage set")
    for f in m["forms"]:
        s=f["stage"];p=pin["forms"][s]
        require((f["asset"],f["bytes"],f["sha256"])==(p["asset"],p["bytes"],p["sha256"]),"stage pin mismatch")
        offset=0
        for i,c in enumerate(f["chunks"]):
            require(c["offset"]==offset and c["bytes"]==min(LIMIT,f["bytes"]-offset)>0 and re.fullmatch("[a-f0-9]{64}",c["sha256"]) and c["path"]==f"assets/emerald/evolution-v3/{s}/{s}.glb.part{i+1:03}","invalid slice")
            offset+=c["bytes"]
        require(offset==f["bytes"],"incomplete stage")
    return m,raw
def chunks(stream,form):
    whole=hashlib.sha256()
    for c in form["chunks"]:
        data=stream.read(c["bytes"])
        require(len(data)==c["bytes"] and digest(data)==c["sha256"],"chunk mismatch "+c["path"])
        whole.update(data)
        yield c,data
    require(not stream.read(1) and whole.hexdigest()==form["sha256"],"whole stage mismatch")
def from_zip(bundle,form):
    with zipfile.ZipFile(bundle) as z:
        found=[i for i in z.infolist() if i.filename==form["asset"]]
        require(len(found)==1 and not found[0].is_dir() and found[0].file_size==form["bytes"],"wrong bundle member")
        with z.open(found[0]) as s:
            yield from chunks(s,form)
def git(repo,*args,data=None,env=None):
    return subprocess.run(["git","-C",str(repo),*args],input=data,stdout=subprocess.PIPE,check=True,env=env).stdout
def oid(data):
    s=data.decode("ascii").strip();require(re.fullmatch("[a-f0-9]{40}|[a-f0-9]{64}",s),"invalid Git object");return s
def check_remote(repo):
    for args in [("remote","get-url","origin"),("remote","get-url","--push","origin")]:
        require(git(repo,*args).decode().strip() in REMOTES,"unauthorized origin")
def head(repo,form,raw):
    ref="refs/heads/assets/emerald-weighted-v3-"+form["stage"]+"-20261117"
    git(repo,"fetch","--no-tags","origin",ref)
    h=oid(git(repo,"rev-parse","FETCH_HEAD"))
    require(git(repo,"show",h+":"+MANIFEST)==raw,"remote manifest differs")
    return ref,h
def publish(repo,form,bundle,raw):
    ref,h=head(repo,form,raw)
    with tempfile.TemporaryDirectory(prefix="emerald-index-") as d:
        env=dict(os.environ,GIT_INDEX_FILE=str(Path(d)/"index"))
        git(repo,"read-tree",h,env=env)
        for c,data in from_zip(bundle,form):
            path=c["path"];blob=oid(git(repo,"hash-object","-w","--no-filters","--stdin",data=data))
            old=git(repo,"ls-tree",h,"--",path).decode().strip()
            if old:
                require(old==f"100644 blob {blob}\t{path}","existing chunk differs")
                continue
            git(repo,"update-index","--add","--cacheinfo",f"100644,{blob},{path}",env=env)
        tree=oid(git(repo,"write-tree",env=env))
    if tree!=oid(git(repo,"rev-parse",h+"^{tree}")):
        h=oid(git(repo,"commit-tree",tree,"-p",h,"-m","assets(dragon): exact weighted "+form["stage"]))
        git(repo,"push","origin",h+":"+ref)
    require(git(repo,"ls-remote","--exit-code","origin",ref).decode().split()==[h,ref],"remote head changed")
    return h
def verify_tree(repo,form):
    whole=hashlib.sha256()
    for c in form["chunks"]:
        p=repo/c["path"];require(p.is_file() and not p.is_symlink() and p.stat().st_size==c["bytes"],"missing or invalid chunk "+c["path"])
        data=p.read_bytes();require(digest(data)==c["sha256"],"chunk hash mismatch")
        whole.update(data)
    require(whole.hexdigest()==form["sha256"],"whole model hash mismatch")
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("action",choices=["verify-bundles","publish","verify-tree"]);p.add_argument("--repo",type=Path,default=ROOT);p.add_argument("--bundles",type=Path);p.add_argument("--stage",choices=STAGES,action="append");a=p.parse_args()
    m,raw=load();forms=[f for f in m["forms"] if not a.stage or f["stage"] in a.stage]
    if a.action=="verify-tree":
        for f in forms:verify_tree(a.repo,f)
        print(json.dumps({"verified_checkout":[f["stage"] for f in forms],"release_qualified":False}));return
    require(a.bundles is not None,"bundle directory required")
    # Verify all selected bytes before any remote operation.
    for f in forms:
        for _ in from_zip(a.bundles/(f["stage"]+"-weighted-v3.zip"),f):pass
    if a.action=="publish":
        check_remote(a.repo)
        for f in forms:print(json.dumps({"stage":f["stage"],"remote_head":publish(a.repo,f,a.bundles/(f["stage"]+"-weighted-v3.zip"),raw)}),flush=True)
    else:print(json.dumps({"verified_bundles":[f["stage"] for f in forms],"published":False}))
if __name__=="__main__":main()
