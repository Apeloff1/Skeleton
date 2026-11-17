"""Fail-closed custody and authenticated fast-forward transport for V4 dragons.

No release, merge, repin, force push, lifecycle scripts or network scraping.
Requires original local ZIPs plus an independently authenticated Git checkout.
"""
import argparse, hashlib, json, os, re, shutil, subprocess, tempfile, zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
MANIFEST=ROOT/"assets/emerald/evolution-v4/publication-manifest.json"
PIN=ROOT/"frontend/src/features/Jeeves/companion/atelier/evolutionPin.json"
STAGES=("hatchling","scout","scholar","pathfinder","archivist")
REMOTES={"https://github.com/Apeloff1/Skeleton","https://github.com/Apeloff1/Skeleton.git",
         "git@github.com:Apeloff1/Skeleton.git","ssh://git@github.com/Apeloff1/Skeleton.git"}
PART=32*1024**2
HEX=re.compile(r"[0-9a-f]{64}\Z")
OID=re.compile(r"[0-9a-f]{40}(?:[0-9a-f]{24})?\Z")


def require(ok,why):
    if not ok:raise ValueError(why)

def digest(raw):return hashlib.sha256(raw).hexdigest()

def load():
    raw=MANIFEST.read_bytes();m=json.loads(raw);pin=json.loads(PIN.read_bytes())
    require(m["schema"]=="skeleton.emerald.evolution-publication.v4"
            and pin["schema"]=="skeleton.emerald.evolution-local-preview.v4"
            and m["donor_sha256"]==pin["donorSha256"]
            and m["chunk_max_bytes"]==PART,"source and donor pin mismatch")
    require(tuple(f["stage"] for f in m["forms"])==STAGES,"unknown or missing stage")
    for f in m["forms"]:
        stage=f["stage"];p=pin["forms"][stage]
        require((f["asset"],f["bytes"],f["sha256"])==(p["asset"],p["bytes"],p["sha256"]) and
                HEX.fullmatch(f["sha256"]) and p["equipmentEnabled"] is False,"model pin mismatch or equipment enabled")
        offset=0
        for k,c in enumerate(f["chunks"]):
            n=min(PART,f["bytes"]-offset)
            require(n>0 and c["offset"]==offset and c["bytes"]==n and HEX.fullmatch(c["sha256"])
                    and c["path"]==f"assets/emerald/evolution-v4/{stage}/{stage}.glb.part{k+1:03}",
                    "invalid per-stage binary chunk")
            offset+=n
        require(offset==f["bytes"],"incomplete stage")
    return m,raw

def verified_zip(bundle,form):
    """Stream exact raw GLB member, independently verify every 32 MiB chunk."""
    require(bundle.is_file() and not bundle.is_symlink(),"missing or unsafe local bundle")
    with zipfile.ZipFile(bundle) as z:
        members=z.infolist()
        require(len(members)<=48 and sum(x.file_size for x in members)<=512*1024**2,
                "ZIP member or total quota")
        names=set()
        for item in members:
            require(not item.flag_bits&1 and not item.is_dir() and
                    not item.filename.startswith("/") and
                    all(x not in ("",".","..") for x in item.filename.split("/")) and
                    "\\" not in item.filename and item.filename.casefold() not in names,
                    "unsafe or duplicate ZIP member")
            names.add(item.filename.casefold())
        info=z.getinfo(form["asset"])
        require(info.file_size==form["bytes"],"binary member size differs from pin")
        # The V4 adoption contract must be inside the same bundle and match its model.
        admission=json.loads(z.read("admission.json"))
        require(admission["stage"]==form["stage"] and admission["bytes"]==form["bytes"]
                and admission["sha256"]==form["sha256"] and admission["source_sha256"]==load()[0]["donor_sha256"]
                and admission["growth"]=="growth-"+form["stage"]+"-to-"+(
                    STAGES[STAGES.index(form["stage"])+1] if form["stage"]!=STAGES[-1] else "hoarder"),
                "admission mismatch")
        sha=hashlib.sha256()
        with z.open(info) as stream:
            for row in form["chunks"]:
                block=stream.read(row["bytes"])
                require(len(block)==row["bytes"] and digest(block)==row["sha256"],
                        "chunk hash mismatch: "+row["path"])
                sha.update(block)
                yield row,block
            require(not stream.read(1),"excess model bytes")
        require(sha.hexdigest()==form["sha256"],"complete model hash mismatch")

def git(repo,*args,data=None,env=None):
    return subprocess.run(["git","-C",str(repo),*args],input=data,
                          stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True,env=env).stdout

def oid(raw):
    value=raw.decode("ascii").strip()
    require(OID.fullmatch(value),"invalid returned Git object ID")
    return value

def remote(repo):
    for args in (("remote","get-url","origin"),("remote","get-url","--push","origin")):
        require(git(repo,*args).decode().strip() in REMOTES,"origin not authorized")

def branch(stage):return "refs/heads/assets/emerald-poster-v4-"+stage+"-20261117"

def checkout_head(repo,form,raw):
    ref=branch(form["stage"])
    git(repo,"fetch","--no-tags","origin",ref)
    head=oid(git(repo,"rev-parse","FETCH_HEAD"))
    require(git(repo,"show",head+":"+str(MANIFEST.relative_to(ROOT)))==raw,"manifest differs at remote draft")
    return ref,head

def publish(repo,form,bundle,raw):
    ref,head=checkout_head(repo,form,raw)
    with tempfile.TemporaryDirectory(prefix="emerald-v4-index-") as tmp:
        env=dict(os.environ,GIT_INDEX_FILE=str(Path(tmp)/"index"))
        git(repo,"read-tree",head,env=env)
        for row,data in verified_zip(bundle,form):
            b=oid(git(repo,"hash-object","-w","--no-filters","--stdin",data=data))
            old=git(repo,"ls-tree",head,"--",row["path"]).decode().strip()
            if old:
                require(old==f"100644 blob {b}\t{row['path']}","existing binary differs")
            else:git(repo,"update-index","--add","--cacheinfo",f"100644,{b},{row['path']}",env=env)
        tree=oid(git(repo,"write-tree",env=env))
    if tree!=oid(git(repo,"rev-parse",head+"^{tree}")):
        head=oid(git(repo,"commit-tree",tree,"-p",head,"-m","assets(dragon): original-donor V4 "+form["stage"]))
        git(repo,"push","origin",head+":"+ref)
    require(git(repo,"ls-remote","--exit-code","origin",ref).decode().split()==[head,ref],
            "remote updated concurrently")
    return head

def check_tree(repo,form):
    sha=hashlib.sha256()
    for row in form["chunks"]:
        path=repo/row["path"]
        require(path.is_file() and not path.is_symlink() and path.stat().st_size==row["bytes"],
                "required raw Git payload absent: "+row["path"])
        with path.open("rb") as stream:
            block=stream.read()
        require(digest(block)==row["sha256"],"remote payload hash mismatch")
        sha.update(block)
    require(sha.hexdigest()==form["sha256"],"complete remote asset digest mismatch")

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("action",choices=("verify-archives","verify-tree","publish"))
    p.add_argument("--bundles",type=Path)
    p.add_argument("--repo",type=Path,default=ROOT)
    p.add_argument("--stage",choices=STAGES,action="append")
    args=p.parse_args()
    m,raw=load();selected=[f for f in m["forms"] if not args.stage or f["stage"] in args.stage]
    if args.action=="verify-tree":
        for f in selected:check_tree(args.repo,f)
        print(json.dumps({"verified_checkout_stages":[f["stage"] for f in selected],
                          "artist_approved":False,"device_qualified":False,"release_qualified":False}));return
    require(args.bundles is not None,"--bundles required")
    for f in selected:
        for _ in verified_zip(args.bundles/(f["stage"]+"-weighted-v4.zip"),f):pass
    if args.action=="publish":
        remote(args.repo)
        for f in selected:
            head=publish(args.repo,f,args.bundles/(f["stage"]+"-weighted-v4.zip"),raw)
            print(json.dumps({"stage":f["stage"],"verified_pushed_head":head}),flush=True)
    else:print(json.dumps({"verified_local_archive_stages":[f["stage"] for f in selected],
                            "remote_binary_publication":False}))
if __name__=="__main__":main()
